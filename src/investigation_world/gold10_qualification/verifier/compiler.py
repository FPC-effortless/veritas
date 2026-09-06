from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import investigation_world.gold10.targets as gold_targets
import investigation_world.gold10.verifier as gold_verifier
from investigation_world.gold10.models import Gold10Submission
from investigation_world.gold10.registry import (
    ROOT,
    build_task,
    build_taskset,
    load_pilot_contract,
)
from investigation_world.gold10.replay import reference_submission
from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    GateOutcome,
    VerifierIdentity,
)
from investigation_world.qualification.verifier_suite import (
    VerifierFixture,
    VerifierFixtureCategory,
    VerifierFixtureManifest,
    VerifierQualificationReport,
    VerifierReplay,
    qualify_verifier,
)

from .models import (
    Applicability,
    Gold10ApplicabilityRecord,
    Gold10TaskBinding,
    Gold10TaskVerifierQualification,
    Gold10VerifierQualification,
)

_FIXED_TIME = datetime(2026, 9, 4, tzinfo=timezone.utc)


def _digest_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return sha256(encoded).hexdigest()


def _module_digest(path: str | None) -> str:
    if not path:
        raise ValueError("qualification requires importable verifier source")
    return sha256(Path(path).read_bytes()).hexdigest()


def _environment_identity(case_id: str, root: Path) -> EnvironmentIdentity:
    task = build_task(case_id, root)
    contract = load_pilot_contract(root)
    payload = {
        "world_id": contract.world_id,
        "world_version": contract.world_version,
        "task": task.model_dump(mode="json"),
        "manifest_sha256": task.manifest_sha256,
    }
    return EnvironmentIdentity(
        environment_id=contract.world_id,
        environment_version=contract.world_version,
        content_sha256=_digest_json(payload),
    )


def _verifier_identity(root: Path) -> VerifierIdentity:
    contract = load_pilot_contract(root)
    payload = {
        "verifier_id": contract.verifier_id,
        "verifier_version": contract.verifier_version,
        "target_contract_sha256": contract.verifier_target_contract_sha256,
        "verifier_source_sha256": _module_digest(gold_verifier.__file__),
        "target_source_sha256": _module_digest(gold_targets.__file__),
    }
    return VerifierIdentity(
        verifier_id=contract.verifier_id,
        verifier_version=contract.verifier_version,
        content_sha256=_digest_json(payload),
    )


def _reordered(submission: Gold10Submission) -> Gold10Submission:
    return submission.model_copy(
        update={
            "evidence_ids": tuple(reversed(submission.evidence_ids)),
            "claims": tuple(reversed(submission.claims)),
        }
    )


def _missing_evidence(
    reference: Gold10Submission,
    available_evidence_ids: tuple[str, ...],
) -> Gold10Submission | str:
    if not reference.claims:
        raise ValueError("missing-evidence falsifier requires at least one retained claim")
    missing_id = reference.claims[0].evidence_ids[0]
    if missing_id not in reference.evidence_ids:
        raise ValueError("reference claim evidence is absent from cited evidence")
    cited = tuple(
        evidence_id
        for evidence_id in reference.evidence_ids
        if evidence_id != missing_id
    )
    if cited:
        return reference.model_copy(update={"evidence_ids": cited})

    replacement = next(
        (
            evidence_id
            for evidence_id in available_evidence_ids
            if evidence_id != missing_id
        ),
        None,
    )
    if replacement is not None:
        return reference.model_copy(update={"evidence_ids": (replacement,)})

    raw = reference.model_dump(mode="json")
    raw["evidence_ids"] = []
    return json.dumps(raw, sort_keys=True, separators=(",", ":"))


def _mutate_submission(
    category: VerifierFixtureCategory,
    reference: Gold10Submission,
    *,
    calibration_required: bool,
    available_evidence_ids: tuple[str, ...],
) -> Gold10Submission | str:
    if category == VerifierFixtureCategory.CORRECT_SOLUTION:
        return reference
    if category == VerifierFixtureCategory.NONDETERMINISTIC_PERTURBATION:
        return _reordered(reference)
    if category == VerifierFixtureCategory.PARTIALLY_CORRECT:
        return reference.model_copy(update={"claims": reference.claims[:-1]})
    if category in {
        VerifierFixtureCategory.INCORRECT_PLAUSIBLE,
        VerifierFixtureCategory.REWARD_HACK,
    }:
        return reference.model_copy(
            update={"primary_hypothesis": "A plausible but target-unbound causal story."}
        )
    if category == VerifierFixtureCategory.INVALID_STATE_MUTATION:
        first = reference.claims[0].model_copy(
            update={"statement": "Mutated canonical state."}
        )
        return reference.model_copy(update={"claims": (first, *reference.claims[1:])})
    if category == VerifierFixtureCategory.MISSING_EVIDENCE:
        return _missing_evidence(reference, available_evidence_ids)
    if category == VerifierFixtureCategory.MALFORMED_ARTIFACT:
        return "{not-valid-json"
    if category == VerifierFixtureCategory.ADVERSARIAL_EDGE_CASE:
        if calibration_required:
            return reference.model_copy(
                update={"unresolved_questions": ("Unbound generic uncertainty.",)}
            )
        duplicate = reference.claims[0].model_copy()
        return reference.model_copy(update={"claims": (*reference.claims, duplicate)})
    raise ValueError(f"unsupported Gold-10 verifier fixture category: {category.value}")


def _confidence_role_inversion(reference: Gold10Submission) -> Gold10Submission:
    return reference.model_copy(
        update={"primary_confidence": 0.25, "alternative_confidence": 0.55}
    )


def _expected(category: VerifierFixtureCategory) -> tuple[bool, float, float]:
    if category in {
        VerifierFixtureCategory.CORRECT_SOLUTION,
        VerifierFixtureCategory.NONDETERMINISTIC_PERTURBATION,
    }:
        return True, 0.75, 0.75
    return False, 0.0, 0.0


def _payload_digest(payload: Gold10Submission | str) -> str:
    if isinstance(payload, str):
        return sha256(payload.encode()).hexdigest()
    return _digest_json(payload.model_dump(mode="json"))


def _execute(
    case_id: str,
    payload: Gold10Submission | str,
    root: Path,
) -> tuple[bool, float, dict[str, float], str]:
    try:
        if isinstance(payload, str):
            score = gold_verifier.score_submission_json(case_id, payload, root)
        else:
            score = gold_verifier.score_submission(case_id, payload, root)
    except Exception as exc:
        evidence = {"exception_type": type(exc).__name__, "message": str(exc)}
        return False, 0.0, {}, _digest_json(evidence)
    passed = not score.hard_failures and score.reward > 0.0
    output = score.model_dump(mode="json")
    return passed, score.reward, score.component_scores, _digest_json(output)


def _neutralize_noncalibration_ambiguity(
    report: VerifierQualificationReport,
) -> VerifierQualificationReport:
    metrics = dict(report.metrics)
    metrics["ambiguity_sensitivity"] = None
    gates = tuple(
        gate.model_copy(
            update={
                "outcome": GateOutcome.UNKNOWN,
                "observed": None,
                "detail": (
                    "Gold-10 non-calibration adversarial fixtures test verifier "
                    "robustness, not ambiguity or calibration sensitivity."
                ),
            }
        )
        if gate.name == "ambiguity_sensitivity"
        else gate
        for gate in report.gates
    )
    payload = report.model_dump(
        mode="python",
        exclude={"report_id", "metrics", "gates", "status"},
    )
    return VerifierQualificationReport(
        **payload,
        metrics=metrics,
        gates=gates,
        status=GateOutcome.UNKNOWN,
    )


def compile_task_qualification(
    case_id: str,
    root: Path | None = None,
) -> Gold10TaskVerifierQualification:
    repo_root = (root or ROOT).resolve()
    task = build_task(case_id, repo_root)
    contract = load_pilot_contract(repo_root)
    reference = reference_submission(case_id, repo_root)
    environment_identity = _environment_identity(case_id, repo_root)
    verifier_identity = _verifier_identity(repo_root)
    available_evidence_ids = tuple(item.evidence_id for item in task.available_evidence)
    qualification_binding = {
        "case_id": case_id,
        "task_id": task.task.task_id,
        "task_manifest_sha256": task.manifest_sha256,
        "taskset_version": contract.taskset_version,
        "world_id": contract.world_id,
        "world_version": contract.world_version,
        "environment_content_sha256": environment_identity.content_sha256,
        "verifier_id": contract.verifier_id,
        "verifier_version": contract.verifier_version,
        "verifier_content_sha256": verifier_identity.content_sha256,
        "verifier_target_contract_sha256": contract.verifier_target_contract_sha256,
    }
    qualification_binding_sha256 = _digest_json(qualification_binding)

    omitted_categories = {
        VerifierFixtureCategory.ALTERNATIVE_CORRECT_STRATEGY,
        VerifierFixtureCategory.AUTHORITY_PROCESS_VIOLATION,
        VerifierFixtureCategory.FORBIDDEN_SIDE_EFFECT,
    }
    fixture_payloads: list[
        tuple[VerifierFixtureCategory, Gold10Submission | str, str]
    ] = []
    for category in VerifierFixtureCategory:
        if category in omitted_categories:
            continue
        payload = _mutate_submission(
            category,
            reference,
            calibration_required=task.calibration_required,
            available_evidence_ids=available_evidence_ids,
        )
        fixture_payloads.append(
            (category, payload, f"Gold-10 {case_id} {category.value} falsifier")
        )

    fixture_payloads.append(
        (
            VerifierFixtureCategory.ADVERSARIAL_EDGE_CASE,
            _confidence_role_inversion(reference),
            f"Gold-10 {case_id} confidence-role inversion adversarial falsifier",
        )
    )

    fixtures: list[VerifierFixture] = []
    replays: list[VerifierReplay] = []
    for category, payload, description in fixture_payloads:
        expected_pass, minimum_reward, maximum_reward = _expected(category)
        fixture = VerifierFixture(
            category=category,
            payload_sha256=_payload_digest(payload),
            expected_pass=expected_pass,
            minimum_reward=minimum_reward,
            maximum_reward=maximum_reward,
            strategy_family=(
                f"gold10-deterministic-v1:{qualification_binding_sha256}"
            ),
            description=description,
            provenance={
                **qualification_binding,
                "qualification_binding_sha256": qualification_binding_sha256,
            },
        )
        fixtures.append(fixture)
        for repetition in range(2):
            passed, reward, component_scores, output_sha256 = _execute(
                case_id,
                payload,
                repo_root,
            )
            replays.append(
                VerifierReplay(
                    fixture_id=fixture.fixture_id,
                    repetition=repetition,
                    reward=reward,
                    passed=passed,
                    component_scores=component_scores,
                    output_sha256=output_sha256,
                    observed_at=_FIXED_TIME,
                    provenance={
                        **qualification_binding,
                        "qualification_binding_sha256": (
                            qualification_binding_sha256
                        ),
                        "repetition": repetition,
                    },
                )
            )

    manifest = VerifierFixtureManifest(
        suite_version="gold10-verifier-qualification-v1",
        environment_identity=environment_identity,
        verifier_identity=verifier_identity,
        fixtures=tuple(fixtures),
    )
    report = qualify_verifier(manifest, tuple(replays))
    if not task.calibration_required:
        report = _neutralize_noncalibration_ambiguity(report)

    applicability_records = [
        Gold10ApplicabilityRecord(
            gate="falsifier_fixture_coverage",
            applicability=Applicability.NOT_APPLICABLE,
            rationale=(
                "The generic taxonomy contains alternative-strategy, "
                "authority/process, and forbidden-side-effect categories that are "
                "not semantically represented by this read-only Gold-10 protocol. "
                "Those categories are omitted rather than fabricated."
            ),
        ),
        Gold10ApplicabilityRecord(
            gate="alternative_solution_acceptance",
            applicability=Applicability.NOT_APPLICABLE,
            rationale=(
                "No independently defensible second semantic solution strategy is "
                "established by this deterministic pilot; reordered reference "
                "content is not an alternative strategy."
            ),
        ),
        Gold10ApplicabilityRecord(
            gate="process_rule_correctness",
            applicability=Applicability.NOT_APPLICABLE,
            rationale=(
                "Gold-10 exposes no authority/process transition surface. "
                "Confidence-role inversion is retained as adversarial verifier "
                "evidence instead of process-rule evidence."
            ),
        ),
        Gold10ApplicabilityRecord(
            gate="side_effect_sensitivity",
            applicability=Applicability.NOT_APPLICABLE,
            rationale="Gold-10 exposes no mutating action or side-effect semantics.",
        ),
    ]
    if not task.calibration_required:
        applicability_records.append(
            Gold10ApplicabilityRecord(
                gate="ambiguity_sensitivity",
                applicability=Applicability.NOT_APPLICABLE,
                rationale=(
                    "This task has no declared calibration/ambiguity surface. Its "
                    "adversarial fixtures test duplicate-claim and confidence-role "
                    "robustness, not ambiguity sensitivity."
                ),
            )
        )

    return Gold10TaskVerifierQualification(
        binding=Gold10TaskBinding(
            case_id=case_id,
            task_id=task.task.task_id,
            split=task.split,
            task_manifest_sha256=task.manifest_sha256,
            verifier_target_contract_sha256=contract.verifier_target_contract_sha256,
        ),
        report=report,
        applicability=tuple(applicability_records),
    )


def compile_gold10_verifier_qualification(
    root: Path | None = None,
) -> Gold10VerifierQualification:
    repo_root = (root or ROOT).resolve()
    contract = load_pilot_contract(repo_root)
    tasks = build_taskset(repo_root)
    records = tuple(
        compile_task_qualification(task.case_id, repo_root) for task in tasks
    )
    statuses = tuple(record.effective_status for record in records)
    status = (
        GateOutcome.FAIL
        if GateOutcome.FAIL in statuses
        else GateOutcome.UNKNOWN
        if GateOutcome.UNKNOWN in statuses
        else GateOutcome.PASS
    )
    return Gold10VerifierQualification(
        pilot_id=contract.pilot_id,
        taskset_version=contract.taskset_version,
        verifier_target_contract_sha256=contract.verifier_target_contract_sha256,
        task_records=records,
        status=status,
    )
