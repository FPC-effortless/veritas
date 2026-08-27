from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.commercial.sre_release import SealedSRERelease
from investigation_world.foundry.models import stable_hash
from investigation_world.portability.models import PortableReleaseIdentity


class PortableGateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    passed: bool


class PortableQualificationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "0.11.0"
    evidence_id: str = ""
    release: PortableReleaseIdentity
    scientifically_qualified: bool
    scenario_count: int = Field(ge=0)
    split_counts: dict[str, int]
    source_group_count: int = Field(ge=0)
    gate_count: int = Field(ge=0)
    failed_gate_count: int = Field(ge=0)
    gates: list[PortableGateSummary]
    policy_means: dict[str, float]
    private_case_details_included: bool = False
    scenario_ids_included: bool = False
    hidden_ground_truth_included: bool = False

    @model_validator(mode="after")
    def validate_evidence_id(self) -> "PortableQualificationEvidence":
        payload = self.model_dump(mode="json", exclude={"evidence_id"})
        expected = f"PEVID-{stable_hash(payload)[:24].upper()}"
        if self.evidence_id and self.evidence_id != expected:
            raise ValueError("portable qualification evidence ID does not match immutable contents")
        object.__setattr__(self, "evidence_id", expected)
        return self


def build_sre_portable_qualification_evidence(
    release: SealedSRERelease,
    *,
    source_bundle_sha256: str | None = None,
) -> PortableQualificationEvidence:
    split_counts = Counter(scenario.split.value for scenario in release.candidate.scenarios)
    gates = [
        PortableGateSummary(name=gate.name, passed=gate.passed)
        for gate in release.qualification.gates
    ]
    release_identity = PortableReleaseIdentity(
        candidate_id=release.candidate.candidate_id,
        candidate_version=release.candidate.version,
        evidence_manifest_id=release.candidate.evidence_manifest.manifest_id,
        qualification_report_id=release.qualification.report_id,
        panel_id=release.qualification.panel_id,
        private_release_manifest_id=release.private_release_manifest.manifest_id,
        source_bundle_sha256=source_bundle_sha256,
    )
    return PortableQualificationEvidence(
        release=release_identity,
        scientifically_qualified=release.qualification.releaseable,
        scenario_count=len(release.candidate.scenarios),
        split_counts=dict(sorted(split_counts.items())),
        source_group_count=len({scenario.source_group_id for scenario in release.candidate.scenarios}),
        gate_count=len(gates),
        failed_gate_count=sum(not gate.passed for gate in gates),
        gates=gates,
        policy_means={
            str(policy.value if hasattr(policy, "value") else policy): float(value)
            for policy, value in sorted(
                release.qualification.policy_means.items(),
                key=lambda item: str(item[0]),
            )
        },
    )
