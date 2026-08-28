from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from re import fullmatch
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash
from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    GateOutcome,
    VerifierIdentity,
)


def _validate_sha256(value: str, *, field_name: str) -> None:
    if fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


class ExploitClass(StrEnum):
    REWARD_HACK = "reward_hack"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"
    EVIDENCE_BYPASS = "evidence_bypass"
    STATE_SPOOF = "state_spoof"
    AUTHORITY_BYPASS = "authority_bypass"
    PROCESS_BYPASS = "process_bypass"
    SIDE_EFFECT_BLINDNESS = "side_effect_blindness"
    NONDETERMINISM = "nondeterminism"
    MALFORMED_ARTIFACT = "malformed_artifact"
    AMBIGUITY = "ambiguity"


class ExploitSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {
            ExploitSeverity.LOW: 1,
            ExploitSeverity.MEDIUM: 2,
            ExploitSeverity.HIGH: 3,
            ExploitSeverity.CRITICAL: 4,
        }[self]


class DiscoverySource(StrEnum):
    HUMAN_RED_TEAM = "human_red_team"
    MODEL_RUN = "model_run"
    TASK_QA = "task_qa"
    SYNTHETIC_FALSIFIER = "synthetic_falsifier"
    PRODUCTION_REPLAY = "production_replay"
    EXPERT_REVIEW = "expert_review"


class DisclosureLevel(StrEnum):
    PUBLIC = "public"
    BUYER_SAFE = "buyer_safe"
    OPERATOR_PRIVATE = "operator_private"


class ExploitDispositionStatus(StrEnum):
    OPEN = "open"
    FIXED = "fixed"
    SUPERSEDED = "superseded"


class RegressionOutcome(StrEnum):
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    ERROR = "error"
    NOT_RUN = "not_run"


class ExploitEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evidence_id: str = Field(min_length=1)
    content_sha256: str
    reference_uri: str = Field(min_length=1)
    disclosure: DisclosureLevel

    @model_validator(mode="after")
    def validate_digest(self) -> "ExploitEvidenceReference":
        _validate_sha256(self.content_sha256, field_name="exploit evidence content_sha256")
        return self


class ExploitFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    exploit_id: str = ""
    exploit_class: ExploitClass
    severity: ExploitSeverity
    environment_identity: EnvironmentIdentity
    verifier_identity: VerifierIdentity
    reproducer: ExploitEvidenceReference
    discovery_source: DiscoverySource
    discovered_at: datetime
    applicable_environment_versions: tuple[str, ...] = ()
    applicable_verifier_versions: tuple[str, ...] = ()
    disclosure: DisclosureLevel = DisclosureLevel.OPERATOR_PRIVATE
    summary: str = Field(min_length=1)
    provenance: dict[str, Any] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_finding(self) -> "ExploitFinding":
        if len(self.applicable_environment_versions) != len(
            set(self.applicable_environment_versions)
        ):
            raise ValueError("applicable environment versions must be unique")
        if len(self.applicable_verifier_versions) != len(set(self.applicable_verifier_versions)):
            raise ValueError("applicable verifier versions must be unique")
        payload = self.model_dump(mode="json", exclude={"exploit_id", "provenance"})
        expected = f"VEXP-{stable_hash(payload)[:24].upper()}"
        if self.exploit_id and self.exploit_id != expected:
            raise ValueError("exploit ID does not match immutable finding contents")
        object.__setattr__(self, "exploit_id", expected)
        return self

    def applies_to(
        self,
        environment_identity: EnvironmentIdentity,
        verifier_identity: VerifierIdentity,
    ) -> bool:
        if self.environment_identity.environment_id != environment_identity.environment_id:
            return False
        if self.verifier_identity.verifier_id != verifier_identity.verifier_id:
            return False
        if (
            self.applicable_environment_versions
            and environment_identity.environment_version not in self.applicable_environment_versions
        ):
            return False
        return not (
            self.applicable_verifier_versions
            and verifier_identity.verifier_version not in self.applicable_verifier_versions
        )


class ExploitDisposition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    disposition_id: str = ""
    exploit_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    previous_disposition_id: str | None = None
    status: ExploitDispositionStatus
    verifier_identity: VerifierIdentity
    recorded_at: datetime
    regression_evidence: ExploitEvidenceReference | None = None
    superseded_by_exploit_id: str | None = None
    rationale: str = Field(min_length=1)
    provenance: dict[str, Any] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_disposition(self) -> "ExploitDisposition":
        if self.sequence == 1:
            if self.previous_disposition_id is not None:
                raise ValueError("initial exploit disposition cannot reference a predecessor")
            if self.status != ExploitDispositionStatus.OPEN:
                raise ValueError("initial exploit disposition must be OPEN")
        elif self.previous_disposition_id is None:
            raise ValueError("later exploit dispositions must reference their predecessor")
        if self.status == ExploitDispositionStatus.FIXED and self.regression_evidence is None:
            raise ValueError("FIXED disposition requires regression evidence")
        if (
            self.status == ExploitDispositionStatus.SUPERSEDED
            and self.superseded_by_exploit_id is None
        ):
            raise ValueError("SUPERSEDED disposition requires a replacement exploit ID")
        if (
            self.status != ExploitDispositionStatus.SUPERSEDED
            and self.superseded_by_exploit_id is not None
        ):
            raise ValueError("only SUPERSEDED dispositions may name a replacement exploit")
        payload = self.model_dump(mode="json", exclude={"disposition_id", "provenance"})
        expected = f"VDISP-{stable_hash(payload)[:24].upper()}"
        if self.disposition_id and self.disposition_id != expected:
            raise ValueError("disposition ID does not match immutable contents")
        object.__setattr__(self, "disposition_id", expected)
        return self


class ExploitCorpus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    corpus_id: str = ""
    schema_version: str = Field(min_length=1)
    findings: tuple[ExploitFinding, ...]
    dispositions: tuple[ExploitDisposition, ...]

    @model_validator(mode="after")
    def validate_corpus(self) -> "ExploitCorpus":
        finding_ids = [finding.exploit_id for finding in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("exploit findings must be unique")
        findings = set(finding_ids)
        by_exploit: dict[str, list[ExploitDisposition]] = {}
        for disposition in self.dispositions:
            if disposition.exploit_id not in findings:
                raise ValueError("exploit disposition references an unknown finding")
            by_exploit.setdefault(disposition.exploit_id, []).append(disposition)
        if set(by_exploit) != findings:
            raise ValueError("every exploit finding requires disposition history")

        for exploit_id, history in by_exploit.items():
            ordered = sorted(history, key=lambda item: item.sequence)
            if [item.sequence for item in ordered] != list(range(1, len(ordered) + 1)):
                raise ValueError("exploit disposition sequence must be contiguous from one")
            for index, disposition in enumerate(ordered):
                if index == 0:
                    continue
                previous = ordered[index - 1]
                if disposition.previous_disposition_id != previous.disposition_id:
                    raise ValueError("exploit disposition history is not append-only contiguous")
                if previous.status == ExploitDispositionStatus.SUPERSEDED:
                    raise ValueError("SUPERSEDED exploit history is terminal")
                if (
                    previous.status == ExploitDispositionStatus.OPEN
                    and disposition.status == ExploitDispositionStatus.OPEN
                ):
                    raise ValueError("OPEN exploit must be fixed or superseded before reopening")
            latest = ordered[-1]
            if latest.status == ExploitDispositionStatus.SUPERSEDED:
                replacement = latest.superseded_by_exploit_id
                if replacement not in findings or replacement == exploit_id:
                    raise ValueError("superseding exploit must be another finding in the corpus")

        supersession_edges = {
            exploit_id: history[-1].superseded_by_exploit_id
            for exploit_id, values in by_exploit.items()
            if (history := sorted(values, key=lambda item: item.sequence))[-1].status
            == ExploitDispositionStatus.SUPERSEDED
        }
        for start in supersession_edges:
            visited: set[str] = set()
            current: str | None = start
            while current in supersession_edges:
                if current in visited:
                    raise ValueError("exploit supersession graph cannot contain a cycle")
                visited.add(current)
                current = supersession_edges[current]

        payload = {
            "schema_version": self.schema_version,
            "findings": [
                item.model_dump(mode="json", exclude={"provenance"})
                for item in sorted(self.findings, key=lambda finding: finding.exploit_id)
            ],
            "dispositions": [
                item.model_dump(mode="json", exclude={"provenance"})
                for item in sorted(
                    self.dispositions,
                    key=lambda disposition: (disposition.exploit_id, disposition.sequence),
                )
            ],
        }
        expected = f"VEXPCORP-{stable_hash(payload)[:24].upper()}"
        if self.corpus_id and self.corpus_id != expected:
            raise ValueError("exploit corpus ID does not match immutable contents")
        object.__setattr__(self, "corpus_id", expected)
        return self

    def latest_disposition(self, exploit_id: str) -> ExploitDisposition:
        history = [item for item in self.dispositions if item.exploit_id == exploit_id]
        if not history:
            raise KeyError(exploit_id)
        return max(history, key=lambda item: item.sequence)

    def append_finding(
        self,
        finding: ExploitFinding,
        *,
        recorded_at: datetime,
        provenance: dict[str, Any],
    ) -> "ExploitCorpus":
        initial = ExploitDisposition(
            exploit_id=finding.exploit_id,
            sequence=1,
            status=ExploitDispositionStatus.OPEN,
            verifier_identity=finding.verifier_identity,
            recorded_at=recorded_at,
            rationale="exploit discovered",
            provenance=provenance,
        )
        return ExploitCorpus(
            schema_version=self.schema_version,
            findings=self.findings + (finding,),
            dispositions=self.dispositions + (initial,),
        )

    def append_disposition(self, disposition: ExploitDisposition) -> "ExploitCorpus":
        previous = self.latest_disposition(disposition.exploit_id)
        if disposition.sequence != previous.sequence + 1:
            raise ValueError("new disposition sequence must immediately follow current history")
        if disposition.previous_disposition_id != previous.disposition_id:
            raise ValueError("new disposition must reference the current disposition")
        return ExploitCorpus(
            schema_version=self.schema_version,
            findings=self.findings,
            dispositions=self.dispositions + (disposition,),
        )


class ExploitRegressionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    observation_id: str = ""
    exploit_id: str = Field(min_length=1)
    environment_identity: EnvironmentIdentity
    verifier_identity: VerifierIdentity
    outcome: RegressionOutcome
    canonical_reward: float = Field(ge=0.0, le=1.0)
    observed_reward: float = Field(ge=0.0, le=1.0)
    evidence: ExploitEvidenceReference | None = None
    observed_at: datetime
    provenance: dict[str, Any] = Field(min_length=1)

    @property
    def score_parity(self) -> bool:
        return self.canonical_reward == self.observed_reward

    @model_validator(mode="after")
    def validate_observation(self) -> "ExploitRegressionObservation":
        if self.outcome in {RegressionOutcome.BLOCKED, RegressionOutcome.SUCCEEDED}:
            if self.evidence is None:
                raise ValueError("executed exploit regression requires evidence")
        payload = self.model_dump(mode="json", exclude={"observation_id", "provenance"})
        expected = f"VOBS-{stable_hash(payload)[:24].upper()}"
        if self.observation_id and self.observation_id != expected:
            raise ValueError("regression observation ID does not match immutable contents")
        object.__setattr__(self, "observation_id", expected)
        return self


class ExploitMonitorPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy_version: str = Field(default="verifier-exploit-monitor-v1", min_length=1)
    blocking_severity: ExploitSeverity = ExploitSeverity.HIGH


class ExploitMonitorGate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1)
    outcome: GateOutcome
    observed: Any = None
    required: Any = None
    detail: str = ""


class ExploitMonitorReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    report_id: str = ""
    policy_version: str
    corpus_id: str
    environment_identity: EnvironmentIdentity
    verifier_identity: VerifierIdentity
    applicable_exploit_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    gates: tuple[ExploitMonitorGate, ...]
    status: GateOutcome
    generated_at: datetime
    provenance: dict[str, Any] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_report(self) -> "ExploitMonitorReport":
        expected_status = (
            GateOutcome.FAIL
            if any(gate.outcome == GateOutcome.FAIL for gate in self.gates)
            else GateOutcome.UNKNOWN
            if any(gate.outcome == GateOutcome.UNKNOWN for gate in self.gates)
            else GateOutcome.PASS
        )
        if self.status != expected_status:
            raise ValueError("exploit monitor status does not match gate outcomes")
        payload = self.model_dump(
            mode="json",
            exclude={"report_id", "generated_at", "provenance"},
        )
        expected = f"VEXPREP-{stable_hash(payload)[:24].upper()}"
        if self.report_id and self.report_id != expected:
            raise ValueError("exploit monitor report ID does not match immutable contents")
        object.__setattr__(self, "report_id", expected)
        return self


class BuyerSafePublicFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    exploit_id: str
    exploit_class: ExploitClass
    severity: ExploitSeverity
    outcome: RegressionOutcome | None


class BuyerSafeExploitSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    summary_id: str = ""
    environment_id: str
    environment_version: str
    verifier_id: str
    verifier_version: str
    status: GateOutcome
    applicable_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    severe_unresolved_count: int = Field(ge=0)
    private_finding_count: int = Field(ge=0)
    public_findings: tuple[BuyerSafePublicFinding, ...]

    @model_validator(mode="after")
    def validate_summary_id(self) -> "BuyerSafeExploitSummary":
        payload = self.model_dump(mode="json", exclude={"summary_id"})
        expected = f"VEXPBUY-{stable_hash(payload)[:24].upper()}"
        if self.summary_id and self.summary_id != expected:
            raise ValueError("buyer-safe summary ID does not match sanitized contents")
        object.__setattr__(self, "summary_id", expected)
        return self
