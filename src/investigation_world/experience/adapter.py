from __future__ import annotations

from investigation_world.trajectory import TrajectoryV2

from .models import (
    BeliefRevision,
    EpistemicSnapshot,
    ExperienceDiagnostics,
    ExperienceInitialConditions,
    ExperienceMaturity,
    ExperienceReadiness,
    ExperienceReference,
    ExperienceSpan,
    MachineExperience,
    StructuralRecord,
)


def machine_experience_from_trajectory(
    trajectory: TrajectoryV2,
    *,
    maturity: ExperienceMaturity = ExperienceMaturity.E0_TRACEABLE,
    readiness: ExperienceReadiness | None = None,
    initial_conditions: ExperienceInitialConditions | None = None,
    epistemic_snapshots: tuple[EpistemicSnapshot, ...] = (),
    belief_revisions: tuple[BeliefRevision, ...] = (),
    spans: tuple[ExperienceSpan, ...] = (),
    structural_records: tuple[StructuralRecord, ...] = (),
    diagnostics: ExperienceDiagnostics | None = None,
    derivation_references: tuple[ExperienceReference, ...] = (),
) -> MachineExperience:
    """Wrap one canonical trajectory without duplicating execution semantics."""
    return MachineExperience(
        trajectory=trajectory,
        maturity=maturity,
        readiness=readiness or ExperienceReadiness(),
        initial_conditions=initial_conditions or ExperienceInitialConditions(),
        epistemic_snapshots=epistemic_snapshots,
        belief_revisions=belief_revisions,
        spans=spans,
        structural_records=structural_records,
        diagnostics=diagnostics or ExperienceDiagnostics(),
        derivation_references=derivation_references,
    )
