from __future__ import annotations

from datetime import datetime, timezone

import pytest

from investigation_world.evidence import (
    EvidenceDependencyRef,
    EvidencePolicyRef,
    EvidenceProducerRef,
    EvidenceVisibility,
)
from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    GateOutcome,
    VerifierIdentity,
)
from investigation_world.qualification.task_qa import (
    REQUIRED_TASK_QA_STAGES,
    ExpertAssignment,
    ExpertConflictStatus,
    ExpertPanel,
    ExpertRef,
    ExpertRole,
    QATaskIdentity,
    TaskQAMetrics,
    TaskQAStage,
    TaskQAStageEvidence,
    qualify_task_qa,
    task_qa_evidence_record,
)

NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)
ENVIRONMENT = EnvironmentIdentity(
    environment_id="ENV-task-qa",
    environment_version="1.0.0",
    content_sha256="a" * 64,
)
VERIFIER = VerifierIdentity(
    verifier_id="VER-task-qa",
    verifier_version="1.0.0",
    content_sha256="b" * 64,
)
TASK = QATaskIdentity(
    task_id="TASK-001",
    task_version="1.0.0",
    content_sha256="c" * 64,
)


def _expert(index: int) -> ExpertRef:
    return ExpertRef(
        expert_id=f"EXPERT-{index}",
        qualification_profile_id=f"EXPERT-PROFILE-{index}",
        qualification_profile_sha256=f"{index:064x}",
        domain_scopes=("enterprise-operations",),
    )


def _panel() -> ExpertPanel:
    return ExpertPanel(
        assignments=(
            ExpertAssignment(role=ExpertRole.AUTHOR, expert=_expert(1)),
            ExpertAssignment(role=ExpertRole.BLIND_EXECUTOR, expert=_expert(2)),
            ExpertAssignment(role=ExpertRole.ADJUDICATOR, expert=_expert(3)),
            ExpertAssignment(role=ExpertRole.VERIFIER_REVIEWER, expert=_expert(4)),
        )
    )


def _dependency(index: int) -> EvidenceDependencyRef:
    return EvidenceDependencyRef(
        evidence_id=f"EVID-{index:024X}",
        content_sha256=f"{index:064x}",
        relation="task_qa_stage",
    )


def _reviewer(stage: TaskQAStage) -> ExpertRole:
    return {
        TaskQAStage.AUTHORING_REVIEW: ExpertRole.AUTHOR,
        TaskQAStage.BLIND_EXECUTION: ExpertRole.BLIND_EXECUTOR,
        TaskQAStage.ALTERNATIVE_STRATEGY_REVIEW: ExpertRole.BLIND_EXECUTOR,
        TaskQAStage.DISAGREEMENT_ADJUDICATION: ExpertRole.ADJUDICATOR,
        TaskQAStage.VERIFIER_ATTACK: ExpertRole.VERIFIER_REVIEWER,
        TaskQAStage.AMBIGUITY_ADJUDICATION: ExpertRole.ADJUDICATOR,
        TaskQAStage.DETERMINISTIC_REPLAY: ExpertRole.VERIFIER_REVIEWER,
    }[stage]


def _stages(*, failed: TaskQAStage | None = None) -> tuple[TaskQAStageEvidence, ...]:
    return tuple(
        TaskQAStageEvidence(
            stage=stage,
            outcome=GateOutcome.FAIL if stage == failed else GateOutcome.PASS,
            evidence=_dependency(index),
            reviewer_role=_reviewer(stage),
        )
        for index, stage in enumerate(REQUIRED_TASK_QA_STAGES, start=1)
    )


def _metrics(**updates: object) -> TaskQAMetrics:
    values: dict[str, object] = {
        "blind_execution_success": True,
        "disagreements_found": 2,
        "disagreements_resolved": 2,
        "alternative_strategies_reviewed": 3,
        "accepted_alternative_strategies": 2,
        "verifier_exploits_found": 1,
        "verifier_exploits_resolved": 1,
        "ambiguities_found": 1,
        "ambiguities_resolved": 1,
        "deterministic_replay_count": 2,
        "deterministic_replay_match": True,
    }
    values.update(updates)
    return TaskQAMetrics(**values)


def _report(*, metrics: TaskQAMetrics | None = None, stages=None):
    return qualify_task_qa(
        task_identity=TASK,
        environment_identity=ENVIRONMENT,
        verifier_identity=VERIFIER,
        expert_panel=_panel(),
        metrics=metrics or _metrics(),
        stage_evidence=_stages() if stages is None else stages,
    )


def test_flagship_panel_requires_independent_expert_identities() -> None:
    shared = _expert(1)
    with pytest.raises(ValueError, match="independent expert identities"):
        ExpertPanel(
            assignments=(
                ExpertAssignment(role=ExpertRole.AUTHOR, expert=shared),
                ExpertAssignment(role=ExpertRole.BLIND_EXECUTOR, expert=shared),
                ExpertAssignment(role=ExpertRole.ADJUDICATOR, expert=_expert(3)),
                ExpertAssignment(role=ExpertRole.VERIFIER_REVIEWER, expert=_expert(4)),
            )
        )


def test_panel_requires_all_core_roles() -> None:
    with pytest.raises(ValueError, match="missing required roles"):
        ExpertPanel(
            assignments=(
                ExpertAssignment(role=ExpertRole.AUTHOR, expert=_expert(1)),
                ExpertAssignment(role=ExpertRole.BLIND_EXECUTOR, expert=_expert(2)),
                ExpertAssignment(role=ExpertRole.ADJUDICATOR, expert=_expert(3)),
            )
        )


def test_unresolved_expert_conflict_fails_before_task_qa() -> None:
    with pytest.raises(ValueError, match="unresolved conflicts"):
        ExpertAssignment(
            role=ExpertRole.AUTHOR,
            expert=_expert(1),
            conflict_status=ExpertConflictStatus.UNRESOLVED,
        )


def test_complete_task_qa_protocol_qualifies() -> None:
    report = _report()

    assert report.qualified
    assert report.status == GateOutcome.PASS
    assert report.report_id.startswith("QAREPORT-")
    assert len(report.report_content_sha256) == 64


def test_missing_required_stage_remains_unknown() -> None:
    stages = tuple(
        item for item in _stages() if item.stage != TaskQAStage.VERIFIER_ATTACK
    )

    report = _report(stages=stages)

    assert report.status == GateOutcome.UNKNOWN
    assert not report.qualified


def test_failed_blind_execution_fails_task_qa() -> None:
    report = _report(metrics=_metrics(blind_execution_success=False))

    assert report.status == GateOutcome.FAIL
    assert not report.qualified


def test_unresolved_verifier_exploit_blocks_qualification() -> None:
    report = _report(
        metrics=_metrics(verifier_exploits_found=2, verifier_exploits_resolved=1)
    )

    assert report.status == GateOutcome.FAIL
    gate = next(item for item in report.gates if item.name == "verifier_exploit_resolution")
    assert gate.outcome == GateOutcome.FAIL


def test_unresolved_ambiguity_blocks_qualification() -> None:
    report = _report(metrics=_metrics(ambiguities_found=2, ambiguities_resolved=1))

    assert report.status == GateOutcome.FAIL


def test_single_replay_cannot_claim_task_determinism() -> None:
    report = _report(metrics=_metrics(deterministic_replay_count=1))

    assert report.status == GateOutcome.UNKNOWN


def test_stage_reviewer_role_is_constrained_by_protocol() -> None:
    with pytest.raises(ValueError, match="not authorized"):
        TaskQAStageEvidence(
            stage=TaskQAStage.VERIFIER_ATTACK,
            outcome=GateOutcome.PASS,
            evidence=_dependency(99),
            reviewer_role=ExpertRole.AUTHOR,
        )


def test_task_qa_report_identity_changes_with_material_findings() -> None:
    first = _report()
    second = _report(metrics=_metrics(alternative_strategies_reviewed=4))

    assert first.report_id != second.report_id
    assert first.report_content_sha256 != second.report_content_sha256


def test_task_qa_emits_shared_composable_evidence() -> None:
    report = _report()
    record = task_qa_evidence_record(
        report,
        producer=EvidenceProducerRef(
            producer_id="task-qa-suite",
            producer_version="1.0.0",
            content_sha256="d" * 64,
        ),
        policy=EvidencePolicyRef(
            policy_id="TASK-QA-POLICY-v1",
            policy_version="veritas.task-qa.v1",
            content_sha256="e" * 64,
        ),
        visibility=EvidenceVisibility.OPERATOR_PRIVATE,
        observed_at=NOW,
        provenance={"runner": "unit-test"},
    )

    assert record.outcome.value == "PASS"
    assert record.evidence_type == "qualification.task_qa"
    assert len(record.dependencies) == len(REQUIRED_TASK_QA_STAGES)
    assert {subject.kind for subject in record.subjects} == {
        "environment",
        "verifier",
        "task",
    }
