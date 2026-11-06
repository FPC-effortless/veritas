"""Recompute provider candidates before admitting their full material evidence."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, Self

from pydantic import model_validator

from investigation_world.experience import MachineExperience
from investigation_world.experience.counterfactual import CounterfactualReceipt
from investigation_world.experience.diagnostics import (
    CapabilityFailureCandidate,
    FailureFamilyCandidate,
    failure_family_candidates,
    intervention_failure_families,
)
from investigation_world.experience_foundry.admission import RecordedExperience
from investigation_world.trajectory import VisibilityClass, canonical_hash

from .core import CapabilitySpec, Digest, ScienceRecord, validate_references


class DiagnosticFamilyEvidence(ScienceRecord):
    schema_version: Literal["veritas.diagnostic-family-evidence.v1"] = (
        "veritas.diagnostic-family-evidence.v1"
    )
    candidate: FailureFamilyCandidate
    source_digests: dict[str, Digest]
    capability_spec: None = None
    capability_mapping: Literal["UNKNOWN"] = "UNKNOWN"
    frequency_scope: Literal["distinct_source_experiences_not_population_rate"] = (
        "distinct_source_experiences_not_population_rate"
    )
    causal_qualification: Literal["UNKNOWN"] = "UNKNOWN"
    visibility: Literal[VisibilityClass.EVALUATOR_PRIVATE] = VisibilityClass.EVALUATOR_PRIVATE

    @model_validator(mode="after")
    def validate_members(self) -> Self:
        validate_references(self.candidate.evidence_references)
        if set(self.source_digests) != set(self.candidate.family.member_experience_ids):
            raise ValueError("family source membership mismatch")
        if self.candidate.family.affected_capability != "unknown":
            raise ValueError("observational family lacks a validated capability binding")
        return self


class CapabilityGapEvidence(ScienceRecord):
    schema_version: Literal["veritas.capability-gap-evidence.v1"] = (
        "veritas.capability-gap-evidence.v1"
    )
    candidate: CapabilityFailureCandidate
    capability_spec: CapabilitySpec
    source_digests: dict[str, Digest]
    receipt_digests: dict[str, Digest]
    capability_mapping: Literal["DECLARED_TASK_ASSOCIATION"] = "DECLARED_TASK_ASSOCIATION"
    evidence_status: Literal["OBSERVED_BOUND_TASK_FAILURES"] = "OBSERVED_BOUND_TASK_FAILURES"
    frequency_scope: Literal["distinct_recorded_protocols_not_independent_agents"] = (
        "distinct_recorded_protocols_not_independent_agents"
    )
    severity_scope: Literal["normalized_unmet_target_fraction_not_general_harm"] = (
        "normalized_unmet_target_fraction_not_general_harm"
    )
    criterion_scope: Literal["verifier_target_set_not_individual_contract_terms"] = (
        "verifier_target_set_not_individual_contract_terms"
    )
    causal_qualification: Literal["UNKNOWN"] = "UNKNOWN"
    visibility: Literal[VisibilityClass.EVALUATOR_PRIVATE] = VisibilityClass.EVALUATOR_PRIVATE

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        refs = self.candidate.evidence_references
        validate_references(refs)
        capability = self.capability_spec.contract
        family, gap = self.candidate.family, self.candidate.gap
        if family.affected_capability != capability.capability_id or (
            gap.capability != capability.capability_id
        ):
            raise ValueError("capability binding mismatch")
        if set(self.source_digests) != set(family.member_experience_ids):
            raise ValueError("capability source membership mismatch")
        if self.receipt_digests != {ref.reference_id: ref.digest for ref in refs}:
            raise ValueError("receipt digest membership mismatch")
        if len(refs) != len(self.receipt_digests) or gap.frequency != len(self.source_digests):
            raise ValueError("candidate frequency does not match bound protocol sources")
        if gap.supporting_failure_family_ids != (family.family_id,):
            raise ValueError("gap does not bind the candidate family")
        if gap.severity != family.severity:
            raise ValueError("gap/family severity mismatch")
        if (
            gap.prerequisite_candidates
            or gap.missing_procedure_candidates
            or gap.likely_abstraction_deficit is not None
        ):
            raise ValueError("diagnostic evidence cannot invent prerequisites or abstractions")
        for ref in refs:
            metadata = ref.private_metadata
            if metadata.get("capability_digest") != capability.content_digest or (
                self.source_digests.get(str(metadata.get("source_experience_id")))
                != metadata.get("source_digest")
            ):
                raise ValueError("receipt/source capability evidence mismatch")
        return self


def ingest_failure_family(
    candidate: FailureFamilyCandidate, *, sources: Iterable[MachineExperience]
) -> DiagnosticFamilyEvidence:
    """Gold-10/coarse symptoms stay unbound; capability cannot be guessed from labels."""
    inputs = tuple(MachineExperience.model_validate(s.model_dump(mode="python")) for s in sources)
    expected = failure_family_candidates(inputs)
    payload = candidate.model_dump(mode="json")
    matches = [item for item in expected if item.model_dump(mode="json") == payload]
    if len(matches) != 1:
        raise ValueError("candidate does not match freshly computed source diagnostics")
    checked = matches[0]
    members = set(checked.family.member_experience_ids)
    return DiagnosticFamilyEvidence(
        candidate=checked,
        source_digests={
            s.experience_id: canonical_hash(s.model_dump(mode="json"))
            for s in inputs
            if s.experience_id in members
        },
    )


def ingest_capability_failure(
    candidate: CapabilityFailureCandidate,
    *,
    sources: Iterable[tuple[CounterfactualReceipt, RecordedExperience]],
) -> CapabilityGapEvidence:
    """Freshly validate retained receipts/artifacts via the provider, not caller PASS.

    Raw model parsing checks content integrity only. Always use this ingestion API
    when current source validity matters; a serialized envelope is not an attestation.
    """
    inputs = tuple(sources)
    expected = intervention_failure_families(inputs)
    payload = candidate.model_dump(mode="json")
    matches = [item for item in expected if item.model_dump(mode="json") == payload]
    if len(matches) != 1:
        raise ValueError("candidate does not match freshly validated source/receipt evidence")
    checked = matches[0]
    wanted = {ref.reference_id for ref in checked.evidence_references}
    selected = [(r, s) for r, s in inputs if r.receipt_id in wanted]
    specs = [
        CapabilitySpec(contract=s.capability, visibility=VisibilityClass.EVALUATOR_PRIVATE)
        for _, s in selected
    ]
    if not specs or len({s.contract_digest for s in specs}) != 1:
        raise ValueError("full capability contract mismatch")
    return CapabilityGapEvidence(
        candidate=checked,
        capability_spec=specs[0],
        source_digests={s.experience.experience_id: r.source_digest for r, s in selected},
        receipt_digests={
            r.receipt_id: canonical_hash(r.model_dump(mode="json")) for r, _ in selected
        },
    )
