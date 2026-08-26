from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from investigation_world.foundry.models import CapabilityContract


class CapabilityFamilyId(StrEnum):
    COMPANYWORLD = "companyworld"
    EXTERNAL_INVESTIGATION = "external_investigation"


class CapabilityFamily(BaseModel):
    family_id: CapabilityFamilyId
    name: str
    description: str
    capability_contract: CapabilityContract
    source_surfaces: list[str] = Field(default_factory=list)
    task_families: list[str] = Field(default_factory=list)


def external_investigation_capability_contract() -> CapabilityContract:
    return CapabilityContract(
        capability_id="external-investigation",
        objective=(
            "Investigate a partially observable external world through heterogeneous noisy sources; resolve identities, "
            "reconstruct temporal and relational state, maintain calibrated uncertainty, select tools under cost constraints, "
            "and produce a precise conclusion whose claims can be independently verified against hidden ground truth."
        ),
        subcapabilities=[
            "discover", "source_selection", "entity_resolution", "provenance", "temporal_reconstruction",
            "relationship_reconstruction", "conflict_resolution", "hypothesis_management", "uncertainty",
            "evidence", "abstention", "verify", "communicate",
        ],
        success_conditions=[
            "claims match hidden task-scoped ground truth",
            "material claims are supported by public evidence with valid provenance",
            "identity merges and temporal conclusions meet precision requirements",
            "uncertainty or abstention is used when evidence is insufficient",
        ],
        failure_conditions=[
            "false entity merge or target substitution",
            "unsupported or laundered evidence",
            "confident conclusion despite unresolved contradictory evidence",
            "private oracle leakage or shortcut use",
        ],
        hard_invariants=[
            "no private oracle access",
            "public evidence is immutable",
            "canonical hidden identifiers are never agent-visible",
            "evaluation ground truth remains independent of investigator output",
        ],
        transfer_targets=[
            "unseen entities and source mixtures",
            "new evidence topologies",
            "OOD temporal histories",
            "adversarial provenance and identity cases",
            "customer-specific investigative domains",
        ],
    )


def external_investigation_family() -> CapabilityFamily:
    return CapabilityFamily(
        family_id=CapabilityFamilyId.EXTERNAL_INVESTIGATION,
        name="External Investigation",
        description=(
            "OSINT-style and evidence-heavy investigation environments where the agent must discover, correlate, resolve, "
            "reconstruct and verify facts from noisy heterogeneous source surfaces."
        ),
        capability_contract=external_investigation_capability_contract(),
        source_surfaces=["web", "registry", "filing", "archive", "documents", "structured databases"],
        task_families=[
            "entity_resolution", "ownership_reconstruction", "temporal_reconstruction", "provenance",
            "conflict_resolution", "due_diligence",
        ],
    )
