"""Constructed public runtime evidence only; no model/training or protected panel."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from investigation_world.experience_foundry.external_receipt import (
    ExternalRunReceipt,
    validate_external_receipt,
)
from investigation_world.experience_foundry.paired_evaluation import (
    FrozenPanel,
    PanelAttempt,
    PanelCase,
    compare_frozen_panel,
)
from investigation_world.foundry.models import CapabilityContract, DistributionSplit, stable_hash
from investigation_world.foundry.training_product import (
    TrainerKind,
    TrainingBundle,
    TrainingExample,
    TrainingRecipe,
    TrainingRunManifest,
    TrainingRunResult,
)
from investigation_world.operational import runtime as runtime_module
from investigation_world.operational.catalog import build_devops_incident_world
from investigation_world.operational.models import EpisodeSubmission
from investigation_world.operational.runtime import OperationalRuntime
from investigation_world.portable_contract import compile_operational_episode
from investigation_world.trajectory import (
    ArtifactIdentity,
    ModelIdentity,
    OperationalRuntimeAdapterContext,
    canonical_hash,
    trajectory_v2_from_operational_runtime,
)
from investigation_world.trajectory.reverify import (
    REPLAY_EVIDENCE_PRIVATE_KEY,
    AuthorizedVerifierRegistry,
    OperationalReplayEvidence,
    attach_operational_replay_evidence,
    current_operational_verifier_binding,
)

BASE_REVISION = "constructed-base-revision"
CHECKPOINT_BYTES = b"constructed checkpoint; not a real model"
CHECKPOINT_DIGEST = hashlib.sha256(CHECKPOINT_BYTES).hexdigest()


def _trajectory(snapshot, *, solve):
    # Public catalog world; the test harness owns this synthetic held-out fixture.
    episode = build_devops_incident_world(seed=391)
    contract = compile_operational_episode(episode)
    runtime = OperationalRuntime(episode)
    initial = runtime.state_snapshot()
    if solve:
        for action in episode.oracle.required_actions:
            effect = next(e for e in episode.oracle.action_effects if e.action_name == action)
            runtime.act(action, **effect.required_parameters)
    submission = EpisodeSubmission(evidence_ids=episode.oracle.required_evidence_ids)
    breakdown = runtime.submit(submission)
    context = OperationalRuntimeAdapterContext(
        breakdown=breakdown,
        submission=submission,
        initial_state_digest=stable_hash(initial),
        world_version="public-catalog-fixture-1",
        model=ModelIdentity(provider="constructed", model_id="fixture-model", snapshot=snapshot),
        portable_operational_contract=ArtifactIdentity(
            artifact_id=contract.contract_id,
            version=contract.schema_version,
        ),
    )
    trajectory = trajectory_v2_from_operational_runtime(runtime, context=context)
    evidence = OperationalReplayEvidence(
        portable_contract=contract,
        trajectory_events_digest=canonical_hash(trajectory.events),
        initial_state=initial,
        initial_state_digest=stable_hash(initial),
        final_state=runtime.state_snapshot(),
        final_state_digest=stable_hash(runtime.state_snapshot()),
        action_events=tuple(runtime.events),
        submission=submission,
        tool_calls=runtime.budget.calls,
        cost_spent=runtime.budget.spent,
    )
    context = context.model_copy(update={"evidence_references": (evidence.reference(),)})
    trajectory = trajectory_v2_from_operational_runtime(runtime, context=context)
    return attach_operational_replay_evidence(trajectory, evidence), contract


@pytest.fixture
def comparison(tmp_path):
    before, contract = _trajectory(BASE_REVISION, solve=True)
    after, _ = _trajectory(CHECKPOINT_DIGEST, solve=False)
    source = before.provenance[0]
    runtime_digest = hashlib.sha256(Path(runtime_module.__file__).read_bytes()).hexdigest()
    case = PanelCase(
        case_id="public-fixture",
        task=before.task,
        world=before.world,
        runtime=before.runtime,
        verifier=before.verifier,
        split=DistributionSplit.IID_TEST,
        source_id=source.source_id,
        source_digest=source.source_digest,
        runtime_source_digest=runtime_digest,
        contract_digest=canonical_hash(contract),
    )
    panel = FrozenPanel(
        cases=(case,),
        evaluation_config={"decoding": "constructed"},
        run_id="run",
        model_provider="constructed",
    )
    cap = CapabilityContract(capability_id="fixture", objective="constructed plumbing")
    bundle = TrainingBundle(
        bundle_id="fixture-bundle",
        capability_contract=cap,
        train_examples=[
            TrainingExample(
                example_id="training-example",
                trajectory_id="verified-training-trajectory",
                task_id="different-training-task",
                split=DistributionSplit.TRAIN,
                trainer=TrainerKind.SFT,
                trace_ref="training-trace",
                verifier_score=1.0,
            )
        ],
        metadata={
            "verified_learning_lineage": [
                {
                    "verified_trajectory_id": "verified-training-trajectory",
                    "task_id": "different-training-task",
                    "source_id": "different-training-source",
                    "source_digest": "a" * 64,
                    "experience_id": "training-experience",
                    "trajectory_id": "canonical-training-trajectory",
                }
            ]
        },
        recipe=TrainingRecipe(
            recipe_id="fixture", trainer=TrainerKind.SFT, capability_contract_id=cap.capability_id
        ),
    )
    manifest = TrainingRunManifest(
        run_id="run",
        bundle_id=bundle.bundle_id,
        trainer=TrainerKind.SFT,
        base_model="fixture-model",
        trainer_version="constructed-v1",
        seed=4,
        parameters={"frozen_panel_id": panel.panel_id},
    )
    input_path, checkpoint_path = tmp_path / "inputs", tmp_path / "checkpoint"
    inputs = b"constructed training input"
    input_path.write_bytes(inputs)
    checkpoint_path.write_bytes(CHECKPOINT_BYTES)
    receipt = ExternalRunReceipt(
        result=TrainingRunResult(manifest=manifest, artifact_ref=str(checkpoint_path)),
        status="completed",
        base_model_revision=BASE_REVISION,
        bundle_digest=canonical_hash(bundle),
        input_digest=hashlib.sha256(inputs).hexdigest(),
        checkpoint_digest=CHECKPOINT_DIGEST,
    )
    validated = validate_external_receipt(
        receipt,
        bundle=bundle,
        expected_manifest=manifest,
        expected_base_model_revision=BASE_REVISION,
        expected_input_bytes=inputs,
        input_path=input_path,
        checkpoint_path=checkpoint_path,
    )

    def attempt(trajectory, checkpoint):
        return PanelAttempt(
            case_id=case.case_id,
            trajectory=trajectory,
            source_id=case.source_id,
            source_digest=case.source_digest,
            runtime_source_digest=runtime_digest,
            evaluation_config_digest=canonical_hash(panel.evaluation_config),
            run_id="run",
            checkpoint_identity=checkpoint,
        )

    return (
        panel,
        (attempt(before, BASE_REVISION),),
        (attempt(after, CHECKPOINT_DIGEST),),
        dict(
            receipt=validated,
            expected_manifest=manifest.model_copy(deep=True),
            training_bundle=bundle,
            registry=AuthorizedVerifierRegistry((current_operational_verifier_binding(),)),
        ),
    )


def test_empty_panel_rejected():
    with pytest.raises(ValueError, match="panel"):
        FrozenPanel(
            cases=(), evaluation_config={}, run_id="constructed-run", model_provider="constructed"
        )


def test_real_verifier_preserves_regression_and_no_attestation(comparison):
    panel, before, after, kwargs = comparison
    unchanged = (panel.model_dump(), before[0].model_dump(), after[0].model_dump())
    result = compare_frozen_panel(panel, before, after, **kwargs)
    assert result["status"] == "paired_outcomes_checked"
    assert result["pairs"][0]["reward_delta"] < 0
    assert result["pairs"][0]["checkpoint"]["component_scores"]["outcome"] < 1
    assert result["model_execution_attestation"] == "unknown"
    assert result["panel_chronology_attestation"] == "unknown"
    assert result["training_validated"] is False and result["capability_gain"] is None
    assert result == compare_frozen_panel(panel, before, after, **kwargs)
    assert unchanged == (panel.model_dump(), before[0].model_dump(), after[0].model_dump())


@pytest.mark.parametrize("which", ["before", "after"])
@pytest.mark.parametrize("mutation", ["missing", "duplicate", "substituted"])
def test_complete_pair_membership_required(comparison, which, mutation):
    panel, before, after, kwargs = comparison
    selected = before if which == "before" else after
    changed = {
        "missing": (),
        "duplicate": selected * 2,
        "substituted": (selected[0].model_copy(update={"case_id": "other"}),),
    }[mutation]
    with pytest.raises(ValueError, match="paired"):
        compare_frozen_panel(
            panel,
            changed if which == "before" else before,
            changed if which == "after" else after,
            **kwargs,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", "other"),
        ("source_digest", "a" * 64),
        ("runtime_source_digest", "b" * 64),
        ("run_id", "other"),
        ("evaluation_config_digest", "c" * 64),
        ("checkpoint_identity", "d" * 64),
    ],
)
def test_attempt_provenance_drift_rejected(comparison, field, value):
    panel, before, after, kwargs = comparison
    after = (after[0].model_copy(update={field: value}),)
    with pytest.raises(ValueError, match="drift|substitution"):
        compare_frozen_panel(panel, before, after, **kwargs)


def _bind_constructed_bundle(kwargs):
    # Constructed integrity envelope for a deliberately changed synthetic training set.
    kwargs["receipt"] = kwargs["receipt"].model_copy(
        update={
            "bundle_digest": canonical_hash(kwargs["training_bundle"]),
        }
    )


@pytest.mark.parametrize("kind", ["task", "source"])
def test_panel_training_overlap_rejected(comparison, kind):
    panel, before, after, kwargs = comparison
    bundle = kwargs["training_bundle"]
    if kind == "task":
        bundle.train_examples[0].task_id = panel.cases[0].task.task_id
        bundle.metadata["verified_learning_lineage"][0]["task_id"] = panel.cases[0].task.task_id
    else:
        bundle.metadata["verified_learning_lineage"][0]["source_id"] = panel.cases[0].source_id
    _bind_constructed_bundle(kwargs)
    with pytest.raises(ValueError, match="overlap"):
        compare_frozen_panel(panel, before, after, **kwargs)


def test_changed_panel_and_changed_manifest_reject(comparison):
    panel, before, after, kwargs = comparison
    changed = panel.model_copy(update={"evaluation_config": {"decoding": "changed"}})
    with pytest.raises(ValueError, match="panel identity drift"):
        compare_frozen_panel(changed, before, after, **kwargs)
    manifest = kwargs["receipt"].expected_manifest.model_copy(update={"parameters": {}})
    kwargs["receipt"] = kwargs["receipt"].model_copy(update={"expected_manifest": manifest})
    with pytest.raises(ValueError, match="commitment"):
        compare_frozen_panel(panel, before, after, **kwargs)


def test_missing_replay_is_explicit_unknown_not_omitted(comparison):
    panel, before, after, kwargs = comparison
    trajectory = after[0].trajectory.model_copy(update={"private_metadata": {}})
    after = (after[0].model_copy(update={"trajectory": trajectory}),)
    result = compare_frozen_panel(panel, before, after, **kwargs)
    assert result["status"] == "unknown" and len(result["pairs"]) == 1
    row = result["pairs"][0]
    assert row["reward_delta"] is None and row["checkpoint"]["reward"] is None
    assert row["checkpoint"]["reason_code"] == "PRIVATE_REPLAY_EVIDENCE_MISSING"


def test_contract_substitution_rejects_even_private_metadata(comparison):
    panel, before, after, kwargs = comparison
    trajectory = after[0].trajectory.model_copy(deep=True)
    trajectory.private_metadata[REPLAY_EVIDENCE_PRIVATE_KEY]["portable_contract"][
        "schema_version"
    ] = "bad"
    after = (after[0].model_copy(update={"trajectory": trajectory}),)
    with pytest.raises(ValueError, match="contract drift"):
        compare_frozen_panel(panel, before, after, **kwargs)


def test_caller_claimed_pass_does_not_replace_authorized_verification(comparison):
    panel, before, after, kwargs = comparison
    kwargs["registry"] = AuthorizedVerifierRegistry(())
    with pytest.raises(ValueError, match="unauthorized"):
        compare_frozen_panel(panel, before, after, **kwargs)


def test_duplicate_or_train_panel_rejected(comparison):
    panel, _, _, _ = comparison
    with pytest.raises(ValueError, match="duplicate"):
        FrozenPanel(
            cases=panel.cases * 2, evaluation_config={}, run_id="run", model_provider="constructed"
        )
    with pytest.raises(ValueError, match="held out"):
        PanelCase.model_validate({**panel.cases[0].model_dump(), "split": "train"})


def test_receipt_cannot_select_expected_manifest(comparison):
    panel, before, after, kwargs = comparison
    other = kwargs["receipt"].expected_manifest.model_copy(update={"seed": 19})
    kwargs["receipt"] = kwargs["receipt"].model_copy(
        update={
            "expected_manifest": other,
            "manifest_digest": canonical_hash(other),
        }
    )
    with pytest.raises(ValueError, match="commitment"):
        compare_frozen_panel(panel, before, after, **kwargs)


def test_exact_model_snapshot_required(comparison):
    panel, before, after, kwargs = comparison
    trajectory = after[0].trajectory
    data = trajectory.model_dump(mode="python")
    data["trajectory_id"] = ""
    data["model"]["snapshot"] = "substituted-revision"
    from investigation_world.trajectory import TrajectoryV2

    changed = TrajectoryV2.model_validate(data)
    with pytest.raises(ValueError, match="checkpoint/model"):
        compare_frozen_panel(
            panel,
            before,
            (after[0].model_copy(update={"trajectory": changed}),),
            **kwargs,
        )


def test_nonfinite_config_rejected(comparison):
    panel, _, _, _ = comparison
    with pytest.raises(ValueError):
        FrozenPanel(
            cases=panel.cases,
            evaluation_config={"temperature": float("nan")},
            run_id="run",
            model_provider="constructed",
        )


def test_source_content_alias_overlap_rejected(comparison):
    panel, before, after, kwargs = comparison
    kwargs["training_bundle"].metadata["verified_learning_lineage"][0]["source_digest"] = (
        panel.cases[0].source_digest
    )
    _bind_constructed_bundle(kwargs)
    with pytest.raises(ValueError, match="overlap"):
        compare_frozen_panel(panel, before, after, **kwargs)


def test_prior_record_is_not_used_as_current_evidence(comparison):
    from investigation_world.trajectory.reverify import reverify_trajectory

    panel, before, after, kwargs = comparison
    first = reverify_trajectory(
        after[0].trajectory,
        verifier=panel.cases[0].verifier,
        registry=kwargs["registry"],
    )
    record = first.record.model_copy(update={"private_metadata": {"caller_claimed_pass": True}})
    trajectory = after[0].trajectory.with_reverification(record)
    after = (after[0].model_copy(update={"trajectory": trajectory}),)
    report = compare_frozen_panel(panel, before, after, **kwargs)
    assert report["pairs"][0]["checkpoint"]["status"] == "reverified"
    assert report["pairs"][0]["reward_delta"] < 0
    assert trajectory.reverifications[0].private_metadata == {"caller_claimed_pass": True}


def test_timeout_remains_an_explicit_unscored_attempt(comparison):
    from investigation_world.trajectory import TrajectoryV2

    panel, before, after, kwargs = comparison
    data = after[0].trajectory.model_dump(mode="python")
    data["trajectory_id"] = ""
    data["termination"] = {"reason": "timeout", "terminated": False, "truncated": True}
    data["private_metadata"] = {}
    timeout = TrajectoryV2.model_validate(data)
    result = compare_frozen_panel(
        panel,
        before,
        (after[0].model_copy(update={"trajectory": timeout}),),
        **kwargs,
    )
    row = result["pairs"][0]["checkpoint"]
    assert row["termination"]["reason"] == "timeout"
    assert row["termination"]["truncated"] is True
    assert row["reward"] is None
    assert result["status"] == "unknown"


def test_incomplete_pinned_world_version_rejected(comparison):
    panel, _, _, _ = comparison
    world = panel.cases[0].world.model_copy(update={"world_version": None})
    with pytest.raises(ValueError, match="world/contract"):
        PanelCase.model_validate({**panel.cases[0].model_dump(), "world": world})


def test_unbound_training_bundle_change_rejected(comparison):
    panel, before, after, kwargs = comparison
    kwargs["training_bundle"].train_examples[0].task_id = panel.cases[0].task.task_id
    with pytest.raises(ValueError, match="bundle"):
        compare_frozen_panel(panel, before, after, **kwargs)


@pytest.mark.parametrize("mutation", ["missing", "empty", "duplicate", "mismatch", "bad_digest"])
def test_training_lineage_must_completely_bind_examples(comparison, mutation):
    panel, before, after, kwargs = comparison
    bundle = kwargs["training_bundle"]
    rows = bundle.metadata["verified_learning_lineage"]
    if mutation == "missing":
        del bundle.metadata["verified_learning_lineage"]
    elif mutation == "empty":
        bundle.metadata["verified_learning_lineage"] = []
    elif mutation == "duplicate":
        rows.append(dict(rows[0]))
    elif mutation == "mismatch":
        rows[0]["verified_trajectory_id"] = "unrelated"
    else:
        rows[0]["source_digest"] = ""
    _bind_constructed_bundle(kwargs)
    with pytest.raises(ValueError, match="lineage"):
        compare_frozen_panel(panel, before, after, **kwargs)
