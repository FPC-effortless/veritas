from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from re import fullmatch
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.evidence import (
    EvidenceArtifactRef,
    EvidenceOutcome,
    EvidencePolicyRef,
    EvidenceProducerRef,
    EvidenceRecord,
    EvidenceSubjectRef,
    EvidenceVisibility,
)
from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    GateOutcome,
    VerifierIdentity,
)

TASK_QA_PROTOCOL_VERSION = "veritas.task-qa.v1"


class ExpertRole(StrEnum):
    AUTHOR = "author"
    BLIND_EXECUTOR = "blind_executor"
    ADJUDICATOR = "adjudicator"
    VERIFIER_REVIEWER = "verifier_reviewer"
    DOMAIN_AUTHORITY = "domain_authority"


REQUIRED_TASK_QA_ROLES = (
    ExpertRole.AUTHOR,
    ExpertRole.BLIND_EXECUTOR,
    ExpertRole.ADJUDICATOR,
    ExpertRole.VERIFIER_REVIEWER,
)


class ExpertConflictStatus(StrEnum):
    CLEAR = "clear"
    DISCLOSED_RESOLVED = "disclosed_resolved"
    UNRESOLVED = "unresolved"


class TaskQAStage(StrEnum):
    AUTHORING_REVIEW = "authoring_review"
    BLIND_EXECUTION = "blind_execution"
    ALTERNATIVE_STRATEGY_REVIEW = "alternative_strategy_review"
    DISAGREEMENT_ADJUDICATION = "disagreement_adjudication"
    VERIFIER_ATTACK = "verifier_attack"
    AMBIGUITY_ADJUDICATION = "ambiguity_adjudication"
    DETERMINISTIC_REPLAY = "deterministic_replay"


REQUIRED_TASK_QA_STAGES = tuple(TaskQAStage)


def _validate_sha256(value: str, *, field_name: str) -> None:
    if fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class QATaskIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    task_version: str = Field(min_length=1)
    content_sha256: str

    @model_validator(mode="after")
    def validate_digest(self) -> "QATaskIdentity":
        _validate_sha256(self.content_sha256, field_name="task content_sha256")
        return self


class ExpertRef(BaseModel):
    """Opaque expert identity bound to a qualification profile, not personal profile data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expert_id: str = Field(min_length=1)
    qualification_profile_id: str = Field(min_length=1)
    qualification_profile_sha256: str
    domain_scopes: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_profile(self) -> "ExpertRef":
        _validate_sha256(
            self.qualification_profile_sha256,
            field_name="expert qualification_profile_sha256",
        )
        normalized = tuple(sorted(set(self.domain_scopes)))
        if len(normalized) != len(self.domain_scopes):
            raise ValueError("expert domain scopes must be unique")
        object.__setattr__(self, "domain_scopes", normalized)
        return self


class ExpertAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: ExpertRole
    expert: ExpertRef
    conflict_status: ExpertConflictStatus = ExpertConflictStatus.CLEAR

    @model_validator(mode="after")
    def validate_conflict(self) -> "ExpertAssignment":
        if self.conflict_status == ExpertConflictStatus.UNRESOLVED:
            raise ValueError("expert assignments cannot retain unresolved conflicts")
        return self


class ExpertPanel(BaseModel):
    """Strict independent expert panel for flagship task QA."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    panel_id: str = ""
    protocol_version: str = TASK_QA_PROTOCOL_VERSION
    assignments: tuple[ExpertAssignment, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_panel(self) -> "ExpertPanel":
        if self.protocol_version != TASK_QA_PROTOCOL_VERSION:
            raise ValueError("unsupported task QA protocol version")
        assignments = tuple(sorted(self.assignments, key=lambda item: item.role.value))
        roles = [item.role for item in assignments]
        if len(roles) != len(set(roles)):
            raise ValueError("expert panel may assign each role only once")
        missing = set(REQUIRED_TASK_QA_ROLES) - set(roles)
        if missing:
            raise ValueError(
                "expert panel is missing required roles: "
                + ", ".join(sorted(role.value for role in missing))
            )
        expert_ids = [item.expert.expert_id for item in assignments]
        if len(expert_ids) != len(set(expert_ids)):
            raise ValueError(
                "task authoring, blind execution, adjudication, verifier review, and optional "
                "domain authority must use independent expert identities"
            )

        object.__setattr__(self, "assignments", assignments)
        payload = {
            "protocol_version": self.protocol_version,
            "assignments": [item.model_dump(mode="json") for item in assignments],
        }
        expected = f"QAPANEL-{_stable_hash(payload)[:24].upper()}"
        if self.panel_id and self.panel_id != expected:
            raise ValueError("expert panel ID does not match immutable assignments")
        object.__setattr__(self, "panel_id", expected)
        return self

    def role_assignment(self, role: ExpertRole) -> ExpertAssignment:
        return next(item for item in self.assignments if item.role == role)


class TaskQAStageEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: TaskQAStage
    outcome: GateOutcome
    evidence: Any
    reviewer_role: ExpertRole
    detail: str = ""

    @model_validator(mode="after")
    def validate_evidence_ref(self) -> "TaskQAStageEvidence":
        # Pydantic Any is used here only to avoid a circular serializer edge in older package builds;
        # enforce the exact shared dependency model at runtime.
        from investigation_world.evidence import EvidenceDependencyRef

        if not isinstance(self.evidence, EvidenceDependencyRef):
            raise ValueError("task QA stage evidence must use EvidenceDependencyRef")
        allowed_roles = {
            TaskQAStage.AUTHORING_REVIEW: {ExpertRole.AUTHOR},
            TaskQAStage.BLIND_EXECUTION: {ExpertRole.BLIND_EXECUTOR},
            TaskQAStage.ALTERNATIVE_STRATEGY_REVIEW: {
                ExpertRole.BLIND_EXECUTOR,
                ExpertRole.ADJUDICATOR,
            },
            TaskQAStage.DISAGREEMENT_ADJUDICATION: {ExpertRole.ADJUDICATOR},
            TaskQAStage.VERIFIER_ATTACK: {ExpertRole.VERIFIER_REVIEWER},
            TaskQAStage.AMBIGUITY_ADJUDICATION: {ExpertRole.ADJUDICATOR},
            TaskQAStage.DETERMINISTIC_REPLAY: {ExpertRole.VERIFIER_REVIEWER},
        }
        if self.reviewer_role not in allowed_roles[self.stage]:
            raise ValueError(f"reviewer role is not authorized for stage {self.stage.value}")
        return self


class TaskQAMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    blind_execution_success: bool | None = None
    disagreements_found: int | None = Field(default=None, ge=0)
    disagreements_resolved: int | None = Field(default=None, ge=0)
    alternative_strategies_reviewed: int | None = Field(default=None, ge=0)
    accepted_alternative_strategies: int | None = Field(default=None, ge=0)
    verifier_exploits_found: int | None = Field(default=None, ge=0)
    verifier_exploits_resolved: int | None = Field(default=None, ge=0)
    ambiguities_found: int | None = Field(default=None, ge=0)
    ambiguities_resolved: int | None = Field(default=None, ge=0)
    deterministic_replay_count: int | None = Field(default=None, ge=0)
    deterministic_replay_match: bool | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> "TaskQAMetrics":
        pairs = (
            ("disagreements", self.disagreements_found, self.disagreements_resolved),
            ("verifier exploits", self.verifier_exploits_found, self.verifier_exploits_resolved),
            ("ambiguities", self.ambiguities_found, self.ambiguities_resolved),
        )
        for label, found, resolved in pairs:
            if (found is None) != (resolved is None):
                raise ValueError(f"{label} found/resolved counts must be supplied together")
            if found is not None and resolved is not None and resolved > found:
                raise ValueError(f"resolved {label} cannot exceed findings")
        if (self.alternative_strategies_reviewed is None) != (
            self.accepted_alternative_strategies is None
        ):
            raise ValueError("alternative strategy reviewed/accepted counts must be supplied together")
        if (
            self.alternative_strategies_reviewed is not None
            and self.accepted_alternative_strategies is not None
            and self.accepted_alternative_strategies > self.alternative_strategies_reviewed
        ):
            raise ValueError("accepted alternative strategies cannot exceed reviewed strategies")
        return self


class TaskQAGate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    outcome: GateOutcome
    detail: str = ""


class TaskQAReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = ""
    report_content_sha256: str = ""
    protocol_version: str = TASK_QA_PROTOCOL_VERSION
    task_identity: QATaskIdentity
    environment_identity: EnvironmentIdentity
    verifier_identity: VerifierIdentity
    expert_panel: ExpertPanel
    metrics: TaskQAMetrics
    stage_evidence: tuple[TaskQAStageEvidence, ...]
    gates: tuple[TaskQAGate, ...]
    status: GateOutcome

    @model_validator(mode="after")
    def validate_report(self) -> "TaskQAReport":
        if self.protocol_version != TASK_QA_PROTOCOL_VERSION:
            raise ValueError("unsupported task QA protocol version")
        stage_evidence = tuple(sorted(self.stage_evidence, key=lambda item: item.stage.value))
        if len(stage_evidence) != len({item.stage for item in stage_evidence}):
            raise ValueError("task QA stage evidence may contain each stage only once")
        panel_roles = {item.role for item in self.expert_panel.assignments}
        if any(item.reviewer_role not in panel_roles for item in stage_evidence):
            raise ValueError("task QA stage evidence references a reviewer outside the expert panel")
        object.__setattr__(self, "stage_evidence", stage_evidence)

        expected_status = (
            GateOutcome.FAIL
            if any(gate.outcome == GateOutcome.FAIL for gate in self.gates)
            else GateOutcome.UNKNOWN
            if any(gate.outcome == GateOutcome.UNKNOWN for gate in self.gates)
            else GateOutcome.PASS
        )
        if self.status != expected_status:
            raise ValueError("task QA status does not match gate outcomes")

        payload = self.model_dump(
            mode="json", exclude={"report_id", "report_content_sha256"}
        )
        content_sha256 = _stable_hash(payload)
        report_id = f"QAREPORT-{content_sha256[:24].upper()}"
        if self.report_content_sha256 and self.report_content_sha256 != content_sha256:
            raise ValueError("task QA report content digest does not match immutable contents")
        if self.report_id and self.report_id != report_id:
            raise ValueError("task QA report ID does not match immutable contents")
        object.__setattr__(self, "report_content_sha256", content_sha256)
        object.__setattr__(self, "report_id", report_id)
        return self

    @property
    def qualified(self) -> bool:
        return self.status == GateOutcome.PASS


def _gate(name: str, outcome: GateOutcome, detail: str = "") -> TaskQAGate:
    return TaskQAGate(name=name, outcome=outcome, detail=detail)


def _resolved_gate(
    *, name: str, found: int | None, resolved: int | None
) -> TaskQAGate:
    if found is None or resolved is None:
        return _gate(name, GateOutcome.UNKNOWN, "required finding-resolution evidence is missing")
    if resolved != found:
        return _gate(name, GateOutcome.FAIL, f"{found - resolved} finding(s) remain unresolved")
    return _gate(name, GateOutcome.PASS)


def qualify_task_qa(
    *,
    task_identity: QATaskIdentity,
    environment_identity: EnvironmentIdentity,
    verifier_identity: VerifierIdentity,
    expert_panel: ExpertPanel,
    metrics: TaskQAMetrics,
    stage_evidence: tuple[TaskQAStageEvidence, ...] | list[TaskQAStageEvidence],
) -> TaskQAReport:
    by_stage: dict[TaskQAStage, TaskQAStageEvidence] = {}
    for item in stage_evidence:
        if item.stage in by_stage:
            raise ValueError(f"duplicate task QA stage: {item.stage.value}")
        by_stage[item.stage] = item

    missing_stages = set(REQUIRED_TASK_QA_STAGES) - set(by_stage)
    stage_coverage = (
        GateOutcome.UNKNOWN if missing_stages else GateOutcome.PASS
    )
    stage_failures = [
        item.stage.value for item in by_stage.values() if item.outcome == GateOutcome.FAIL
    ]
    stage_unknowns = [
        item.stage.value for item in by_stage.values() if item.outcome == GateOutcome.UNKNOWN
    ]
    stage_outcome = (
        GateOutcome.FAIL
        if stage_failures
        else GateOutcome.UNKNOWN
        if missing_stages or stage_unknowns
        else GateOutcome.PASS
    )

    blind_outcome = (
        GateOutcome.UNKNOWN
        if metrics.blind_execution_success is None
        else GateOutcome.PASS
        if metrics.blind_execution_success
        else GateOutcome.FAIL
    )
    alternative_outcome = (
        GateOutcome.UNKNOWN
        if metrics.alternative_strategies_reviewed is None
        else GateOutcome.PASS
    )
    replay_outcome = (
        GateOutcome.UNKNOWN
        if metrics.deterministic_replay_count is None
        or metrics.deterministic_replay_match is None
        or metrics.deterministic_replay_count < 2
        else GateOutcome.PASS
        if metrics.deterministic_replay_match
        else GateOutcome.FAIL
    )

    gates = (
        _gate("expert_panel_independence", GateOutcome.PASS),
        _gate(
            "required_stage_coverage",
            stage_coverage,
            (
                "missing: " + ", ".join(sorted(stage.value for stage in missing_stages))
                if missing_stages
                else ""
            ),
        ),
        _gate(
            "stage_outcomes",
            stage_outcome,
            (
                "failed: " + ", ".join(sorted(stage_failures))
                if stage_failures
                else "unknown: " + ", ".join(sorted(stage_unknowns))
                if stage_unknowns
                else ""
            ),
        ),
        _gate("blind_expert_execution", blind_outcome),
        _resolved_gate(
            name="disagreement_resolution",
            found=metrics.disagreements_found,
            resolved=metrics.disagreements_resolved,
        ),
        _gate("alternative_strategy_review", alternative_outcome),
        _resolved_gate(
            name="verifier_exploit_resolution",
            found=metrics.verifier_exploits_found,
            resolved=metrics.verifier_exploits_resolved,
        ),
        _resolved_gate(
            name="ambiguity_resolution",
            found=metrics.ambiguities_found,
            resolved=metrics.ambiguities_resolved,
        ),
        _gate("deterministic_replay", replay_outcome),
    )
    status = (
        GateOutcome.FAIL
        if any(gate.outcome == GateOutcome.FAIL for gate in gates)
        else GateOutcome.UNKNOWN
        if any(gate.outcome == GateOutcome.UNKNOWN for gate in gates)
        else GateOutcome.PASS
    )
    return TaskQAReport(
        task_identity=task_identity,
        environment_identity=environment_identity,
        verifier_identity=verifier_identity,
        expert_panel=expert_panel,
        metrics=metrics,
        stage_evidence=tuple(stage_evidence),
        gates=gates,
        status=status,
    )


def task_qa_evidence_record(
    report: TaskQAReport,
    *,
    producer: EvidenceProducerRef,
    policy: EvidencePolicyRef,
    visibility: EvidenceVisibility,
    observed_at: datetime,
    provenance: dict[str, Any],
) -> EvidenceRecord:
    """Wrap a task QA report in the shared evidence contract for cross-subsystem composition."""

    outcome = EvidenceOutcome(report.status.value)
    return EvidenceRecord(
        evidence_type="qualification.task_qa",
        outcome=outcome,
        visibility=visibility,
        claim="Task QA protocol requirements are satisfied." if report.qualified else "Task QA protocol requirements are not fully satisfied.",
        subjects=(
            EvidenceSubjectRef(
                kind="environment",
                subject_id=report.environment_identity.environment_id,
                version=report.environment_identity.environment_version,
                content_sha256=report.environment_identity.content_sha256,
            ),
            EvidenceSubjectRef(
                kind="verifier",
                subject_id=report.verifier_identity.verifier_id,
                version=report.verifier_identity.verifier_version,
                content_sha256=report.verifier_identity.content_sha256,
            ),
            EvidenceSubjectRef(
                kind="task",
                subject_id=report.task_identity.task_id,
                version=report.task_identity.task_version,
                content_sha256=report.task_identity.content_sha256,
            ),
        ),
        producer=producer,
        policy=policy,
        artifacts=(
            EvidenceArtifactRef(
                artifact_id=report.report_id,
                role="task_qa_report",
                content_sha256=report.report_content_sha256,
                media_type="application/json",
            ),
        ),
        dependencies=tuple(item.evidence for item in report.stage_evidence),
        observed_at=observed_at,
        provenance=provenance,
    )
