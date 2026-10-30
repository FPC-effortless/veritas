"""Native receipt/engine integration; not proof of G-03 adapter completeness."""

from __future__ import annotations

import json
import shutil
import sqlite3

import pytest
from openpyxl import load_workbook
from pydantic import ValidationError

from investigation_world.foundry.models import stable_hash
from investigation_world.operational import (
    EpisodeSubmission,
    NativeOperationalRuntime,
    OperationalDistributionConfig,
    WorldDomain,
    compile_operational_distribution,
)
from investigation_world.operational.artifacts import NativeArtifactWorkspace
from investigation_world.operational.parameterized_artifacts import (
    ParameterizedNativeArtifactWorkspace,
)
from investigation_world.operational.substrate import PersistentOperationalSubstrate
from investigation_world.portable_contract import compile_operational_episode
from investigation_world.trajectory import (
    ArtifactIdentity,
    EvaluationRecord,
    ModelIdentity,
    StateDigest,
    TaskIdentity,
    TrajectoryEvent,
    TrajectoryV2,
    UsageTotals,
    VerifierIdentity,
    VisibilityClass,
    WorldIdentity,
    canonical_hash,
)
from investigation_world.trajectory.reverify import (
    REPLAY_EVIDENCE_PRIVATE_KEY,
    AuthorizedVerifierRegistry,
    OperationalReplayEvidence,
    ReverificationStatus,
    current_operational_verifier_binding,
    reverify_trajectory,
)


@pytest.fixture(scope="module")
def episodes():
    config = OperationalDistributionConfig(
        seed=73,
        train_per_domain=1,
        iid_per_domain=1,
        ood_per_domain=1,
        adversarial_per_domain=1,
    )
    return {
        case.episode.task.domain: case.episode
        for case in compile_operational_distribution(config)
        if case.split.value == "train"
    }


def _execute(runtime):
    oracle = runtime.episode.oracle
    for action in oracle.required_action_order:
        effects = [effect for effect in oracle.action_effects if effect.action_name == action]
        for ordinal in range(oracle.required_action_counts.get(action, 1)):
            runtime.act(action, **effects[min(ordinal, len(effects) - 1)].required_parameters)
    return EpisodeSubmission(
        conclusion="Native artifact checked", evidence_ids=oracle.required_evidence_ids
    )


def test_native_submission_retains_immutable_private_receipt(episodes, tmp_path):
    runtime = NativeOperationalRuntime(
        episodes[WorldDomain.DEVOPS_INCIDENT_RESPONSE].model_copy(deep=True),
        artifact_root=tmp_path,
    )
    assert runtime.last_native_submission is None
    runtime.submit(_execute(runtime))
    assert runtime.last_native_submission is not None


def _corrupt(runtime):
    path = runtime.materialize_artifact()
    domain = runtime.episode.task.domain
    if domain is WorldDomain.FINANCIAL_SPREADSHEET:
        workbook = load_workbook(path)
        target = next(a for a in runtime.episode.oracle.target_state if a.field_name == "formula")
        sheet, cell = target.object_id.split("!")
        workbook[sheet][cell] = "=0"
        workbook.save(path)
    elif domain is WorldDomain.ENTERPRISE_OPERATIONS:
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE erp_orders SET control_bypassed=1")
    else:
        filename, key, value = {
            WorldDomain.DEVOPS_INCIDENT_RESPONSE: ("cluster_state.json", "health", "unhealthy"),
            WorldDomain.INVESTIGATION_OSINT: ("casefile.json", "false_merge", True),
            WorldDomain.GIS_OPERATIONS: ("workspace_state.json", "invalid_geometries", 9),
        }[domain]
        target = path / filename
        data = json.loads(target.read_text())
        data[key] = value
        target.write_text(json.dumps(data))


def _run(episode, root, *, persistent=False, corrupt=False, blocked=False):
    runtime = NativeOperationalRuntime(
        episode.model_copy(deep=True),
        artifact_root=root,
        substrate=PersistentOperationalSubstrate() if persistent else None,
    )
    contract = compile_operational_episode(runtime.episode.model_copy(deep=True))
    initial = runtime.state_snapshot()
    if blocked:
        action = runtime.episode.oracle.required_action_order[0]
        spec = next(a for a in runtime.episode.task.available_actions if a.name == action)
        runtime.act(action, **{name: "invalid-parameter" for name in spec.parameter_names})
        assert runtime.events[-1].blocked
        assert not runtime.events[-1].effect_applied
    submission = _execute(runtime)
    if corrupt:
        _corrupt(runtime)
    before = runtime.trace()
    budget = runtime.budget_snapshot()
    result = runtime.submit(submission)
    assert runtime.trace() == before
    assert runtime.budget_snapshot() == budget
    return runtime, contract, initial, submission, result


def _trajectory(
    run,
    *,
    receipt=None,
    transform_events=None,
    final_state=None,
    include_receipt=True,
):
    runtime, contract, initial, submission, result = run
    receipt = runtime.last_native_submission if receipt is None else receipt
    final = runtime.state_snapshot() if final_state is None else final_state
    events = [
        TrajectoryEvent(
            step=index,
            event_type="act",
            cost=float(event.cost),
            payload={
                "method": "act",
                "args": [event.action_name],
                "kwargs": event.parameters,
                "success": not event.blocked,
            },
        )
        for index, event in enumerate(runtime.events)
    ]
    events.append(
        TrajectoryEvent(
            step=len(events),
            event_type="native_submission",
            cost=0,
            payload={"method": "verify_native_artifact", "receipt_id": receipt.receipt_id},
            state_before=StateDigest(digest=stable_hash(json.loads(receipt.pre_state_json))),
            state_after=StateDigest(digest=stable_hash(final)),
            visibility=VisibilityClass.EVALUATOR_PRIVATE,
        )
    )
    events.append(
        TrajectoryEvent(
            step=len(events),
            event_type="submit",
            cost=0,
            payload={
                "method": "submit",
                "args": [submission.model_dump(mode="json")],
                "kwargs": {},
                "success": True,
            },
        )
    )
    if transform_events:
        events = transform_events(events)
        events = [event.model_copy(update={"step": i}) for i, event in enumerate(events)]
    evidence = OperationalReplayEvidence(
        portable_contract=contract,
        trajectory_events_digest=canonical_hash(events),
        initial_state=initial,
        initial_state_digest=stable_hash(initial),
        final_state=final,
        final_state_digest=stable_hash(final),
        action_events=tuple(runtime.events),
        submission=submission,
        tool_calls=runtime.budget.calls,
        cost_spent=runtime.budget.spent,
        native_submission=receipt if include_receipt else None,
    )
    verifier = VerifierIdentity(verifier_id="original-native", version="1")
    trajectory = TrajectoryV2(
        world=WorldIdentity(
            environment_id="operational",
            environment_version="test",
            world_id=runtime.episode.world_id,
            portable_operational_contract=ArtifactIdentity(
                artifact_id=contract.contract_id,
                contract="veritas.portable-operational-contract",
                version=contract.schema_version,
            ),
        ),
        task=TaskIdentity(
            task_id=runtime.episode.task.task_id, taskset_version="tests", split="train"
        ),
        model=ModelIdentity(provider="offline-test", model_id="constructed-reference"),
        verifier=verifier,
        initial_state=StateDigest(digest=stable_hash(initial)),
        final_state=StateDigest(digest=stable_hash(final)),
        events=tuple(events),
        evidence_references=(evidence.reference(),),
        usage=UsageTotals(environment_cost=float(runtime.budget.spent)),
        original_evaluation=EvaluationRecord(
            verifier=verifier,
            reward=result.overall_reward,
            component_scores={
                name: float(getattr(result, name))
                for name in (
                    "outcome",
                    "state",
                    "constraints",
                    "side_effects",
                    "process",
                    "efficiency",
                    "evidence",
                )
            },
        ),
    )
    return trajectory.model_copy(
        update={
            "private_metadata": {
                REPLAY_EVIDENCE_PRIVATE_KEY: evidence.for_trajectory(trajectory).model_dump(
                    mode="json"
                ),
            }
        }
    )


def _reverify(trajectory):
    binding = current_operational_verifier_binding()
    return reverify_trajectory(
        trajectory,
        verifier=binding.identity,
        registry=AuthorizedVerifierRegistry((binding,)),
    )


@pytest.mark.parametrize("domain", list(WorldDomain))
@pytest.mark.parametrize("corrupt", [False, True], ids=["valid-artifact", "corrupt-artifact"])
def test_all_domains_reproduce_native_scores_and_attribution(
    episodes, tmp_path, domain, corrupt, monkeypatch
):
    runs = [
        _run(episodes[domain], tmp_path / str(persistent), persistent=persistent, corrupt=corrupt)
        for persistent in (False, True)
    ]
    assert runs[0][-1] == runs[1][-1]
    assert runs[0][0].last_artifact_verification.valid is not corrupt

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "offline replay must never materialize or regenerate retained artifacts"
        )

    monkeypatch.setattr(NativeArtifactWorkspace, "materialize", forbidden)
    monkeypatch.setattr(ParameterizedNativeArtifactWorkspace, "materialize", forbidden)
    for run in runs:
        trajectory = _trajectory(run)
        outcome = _reverify(trajectory)
        assert outcome.status is ReverificationStatus.REVERIFIED, outcome.reason_code
        actual = outcome.record.private_metadata["verification_breakdown"]
        assert actual == run[-1].model_dump(mode="json")
        native_failures = [
            item for item in actual["process_violations"] if item.startswith("native_artifact:")
        ]
        assert bool(native_failures) is corrupt
        repeated = _reverify(outcome.trajectory_with_reverification)
        assert repeated.status is ReverificationStatus.ALREADY_RECORDED
        assert repeated.record.record_id == outcome.record.record_id


def test_blocked_attempt_is_replayed_and_charged(episodes, tmp_path):
    run = _run(episodes[WorldDomain.FINANCIAL_SPREADSHEET], tmp_path, blocked=True)
    assert run[0].events[0].blocked
    outcome = _reverify(_trajectory(run))
    assert outcome.status is ReverificationStatus.REVERIFIED, outcome.reason_code
    assert outcome.record.private_metadata["verification_breakdown"] == run[-1].model_dump(
        mode="json"
    )
    assert run[0].budget.calls == len(run[0].events)
    assert run[0].budget.spent == sum(event.cost for event in run[0].events)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "after-submit", "before-action"])
def test_evaluator_transition_must_be_unique_and_ordered(episodes, tmp_path, mutation):
    run = _run(episodes[WorldDomain.DEVOPS_INCIDENT_RESPONSE], tmp_path)

    def transform(events):
        evaluator = events[-2]
        if mutation == "missing":
            return events[:-2] + events[-1:]
        if mutation == "duplicate":
            return events[:-1] + [evaluator] + events[-1:]
        if mutation == "after-submit":
            return events[:-2] + [events[-1], evaluator]
        return [evaluator] + events[:-2] + events[-1:]

    outcome = _reverify(_trajectory(run, transform_events=transform))
    assert outcome.status not in {
        ReverificationStatus.REVERIFIED,
        ReverificationStatus.ALREADY_RECORDED,
    }
    assert outcome.record is None


@pytest.mark.parametrize("change", ["artifact", "missing-artifact", "receipt", "missing-receipt"])
def test_changed_or_missing_retained_evidence_fails_closed(episodes, tmp_path, change):
    run = _run(episodes[WorldDomain.DEVOPS_INCIDENT_RESPONSE], tmp_path)
    trajectory = _trajectory(run)
    payload = trajectory.private_metadata[REPLAY_EVIDENCE_PRIVATE_KEY]
    if change == "artifact":
        _corrupt(run[0])
    elif change == "missing-artifact":
        shutil.rmtree(run[0].artifact_workspace.path)
    elif change == "receipt":
        payload["native_submission"]["cost_spent"] += 1
    else:
        trajectory = _trajectory(run, include_receipt=False)
    outcome = _reverify(trajectory)
    assert outcome.status not in {
        ReverificationStatus.REVERIFIED,
        ReverificationStatus.ALREADY_RECORDED,
    }
    assert outcome.record is None


def test_public_serialization_excludes_native_private_material(episodes, tmp_path):
    run = _run(episodes[WorldDomain.DEVOPS_INCIDENT_RESPONSE], tmp_path)
    trajectory = _trajectory(run)
    receipt = run[0].last_native_submission
    public = json.dumps(trajectory.public_payload())
    assert receipt.receipt_id not in public
    assert receipt.artifact_path not in public
    assert "verification_json" not in public
    assert "episode_json" not in public
    assert "verify_native_artifact" not in public
    assert "last_native_submission" not in json.dumps(run[0].public_payload())


def _replace_receipt(receipt, **changes):
    from investigation_world.operational.native_submission import NativeSubmissionReceipt

    payload = receipt.model_dump(mode="json")
    payload.update(changes, receipt_id="", receipt_digest="")
    return NativeSubmissionReceipt.model_validate(payload)


@pytest.mark.parametrize("change", ["verifier", "source", "descriptor", "measurement", "checks"])
def test_rehashed_forgery_cannot_substitute_for_independent_inspection(episodes, tmp_path, change):
    from investigation_world.operational.native_submission import canonical_native_json

    run = _run(episodes[WorldDomain.DEVOPS_INCIDENT_RESPONSE], tmp_path)
    receipt = run[0].last_native_submission
    final_state = None
    if change == "verifier":
        forged = _replace_receipt(receipt, verifier_version="unauthorized-v999")
    elif change == "source":
        forged = _replace_receipt(receipt, artifact_sources=(("artifacts.py", "0" * 40),))
    elif change == "descriptor":
        descriptor = json.loads(receipt.descriptor_json)
        descriptor["engine"] = "unauthorized-engine"
        forged = _replace_receipt(receipt, descriptor_json=canonical_native_json(descriptor))
    else:
        verification = json.loads(receipt.verification_json)
        if change == "measurement":
            verification["measurements"]["target_error_rate"] = 999
            changes = {}
        else:
            # Forge an entirely consistent false check/state receipt and recompute
            # all outer identities: only inspecting the retained bytes can reject it.
            verification["checks"]["service_healthy"] = False
            verification["valid"] = False
            final_state = json.loads(receipt.final_state_json)
            final_state["native_artifact.service_healthy"] = False
            changes = {"final_state_json": canonical_native_json(final_state)}
        forged = _replace_receipt(
            receipt,
            verification_json=canonical_native_json(verification),
            **changes,
        )
    outcome = _reverify(_trajectory(run, receipt=forged, final_state=final_state))
    assert outcome.status is ReverificationStatus.UNKNOWN
    assert outcome.reason_code == "AUTHORIZED_VERIFIER_FAILED"
    assert outcome.record is None


def test_receipt_is_immutable_and_detached_from_live_runtime(episodes, tmp_path):
    run = _run(episodes[WorldDomain.DEVOPS_INCIDENT_RESPONSE], tmp_path)
    runtime = run[0]
    receipt = runtime.last_native_submission
    snapshot = receipt.model_dump_json()
    with pytest.raises(ValidationError, match="frozen"):
        receipt.cost_spent = 0
    runtime.events[0].parameters["mutable"] = "changed"
    runtime.state["native_artifact.service_healthy"] = "changed"
    runtime.episode.oracle.target_state.clear()
    runtime.last_artifact_verification.checks.clear()
    assert receipt.model_dump_json() == snapshot


def test_stale_receipt_from_another_submission_is_rejected(episodes, tmp_path):
    first = _run(episodes[WorldDomain.DEVOPS_INCIDENT_RESPONSE], tmp_path / "first")
    other = _run(episodes[WorldDomain.DEVOPS_INCIDENT_RESPONSE], tmp_path / "other", corrupt=True)
    outcome = _reverify(_trajectory(other, receipt=first[0].last_native_submission))
    assert outcome.status is ReverificationStatus.NOT_REVERIFIABLE
    assert outcome.record is None


def test_rehashed_forged_action_effect_is_independently_replayed(episodes, tmp_path):
    from investigation_world.operational.native_submission import canonical_native_json

    run = _run(episodes[WorldDomain.DEVOPS_INCIDENT_RESPONSE], tmp_path)
    runtime = run[0]
    receipt = runtime.last_native_submission
    runtime.events[0].state_changes["forged.state"] = True
    pre_state = json.loads(receipt.pre_state_json)
    pre_state["forged.state"] = True
    final_state = json.loads(receipt.final_state_json)
    final_state["forged.state"] = True
    forged = _replace_receipt(
        receipt,
        action_events_json=canonical_native_json(runtime.trace()),
        pre_state_json=canonical_native_json(pre_state),
        final_state_json=canonical_native_json(final_state),
    )
    outcome = _reverify(_trajectory(run, receipt=forged, final_state=final_state))
    assert outcome.status is ReverificationStatus.NOT_REVERIFIABLE
    assert outcome.reason_code == "NATIVE_SUBMISSION_EVIDENCE_INVALID"
    assert outcome.record is None


def test_native_inspector_requires_explicit_registry_authorization(episodes, tmp_path):
    from dataclasses import replace

    run = _run(episodes[WorldDomain.DEVOPS_INCIDENT_RESPONSE], tmp_path)
    binding = replace(current_operational_verifier_binding(), authorize_native_artifacts=False)
    outcome = reverify_trajectory(
        _trajectory(run),
        verifier=binding.identity,
        registry=AuthorizedVerifierRegistry((binding,)),
    )
    assert outcome.status is ReverificationStatus.UNKNOWN
    assert outcome.reason_code == "AUTHORIZED_VERIFIER_FAILED"
    assert outcome.record is None


@pytest.mark.parametrize("directory", [False, True])
def test_retained_snapshot_isolated_from_later_producer_writes(tmp_path, directory):
    """Benign sequential isolation: inspection reads the captured copy, not live bytes."""
    from investigation_world.trajectory.reverify.native import _retained_snapshot

    retained = tmp_path / "artifact"
    if directory:
        retained.mkdir()
        original = retained / "data.json"
    else:
        original = retained
    original.write_bytes(b'{"version":1}')
    with _retained_snapshot(retained) as snapshot:
        copied = snapshot / "data.json" if directory else snapshot
        assert snapshot != retained
        original.write_bytes(b'{"version":2}')
        assert copied.read_bytes() == b'{"version":1}'
        assert original.read_bytes() == b'{"version":2}'
    assert not snapshot.exists()


def test_retained_snapshot_enforces_aggregate_limits(tmp_path, monkeypatch):
    import investigation_world.trajectory.reverify.native as native

    root = tmp_path / "artifact"
    root.mkdir()
    (root / "one").write_bytes(b"1234")
    (root / "two").write_bytes(b"5678")
    monkeypatch.setattr(native, "_MAX_SNAPSHOT_BYTES", 7)
    with pytest.raises(ValueError, match="SNAPSHOT_LIMIT"):
        with native._retained_snapshot(root):
            pytest.fail("oversized snapshot accepted")
    monkeypatch.setattr(native, "_MAX_SNAPSHOT_BYTES", 64)
    monkeypatch.setattr(native, "_MAX_SNAPSHOT_ENTRIES", 1)
    with pytest.raises(ValueError, match="SNAPSHOT_LIMIT"):
        with native._retained_snapshot(root):
            pytest.fail("excess entries accepted")


def test_native_inspector_receives_private_snapshot(episodes, tmp_path, monkeypatch):
    run = _run(episodes[WorldDomain.DEVOPS_INCIDENT_RESPONSE], tmp_path / "retained")
    retained = run[0].artifact_workspace.path
    original = ParameterizedNativeArtifactWorkspace._verify_devops
    inspected = []

    def inspect(workspace):
        assert workspace.path != retained
        assert workspace.path.name == retained.name
        inspected.append(workspace.path)
        return original(workspace)

    monkeypatch.setattr(ParameterizedNativeArtifactWorkspace, "_verify_devops", inspect)
    assert _reverify(_trajectory(run)).status is ReverificationStatus.REVERIFIED
    assert len(inspected) == 1
    assert not inspected[0].exists()
