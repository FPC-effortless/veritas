"""Consume validated executed contrasts; never infer general causal qualification."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Literal

from pydantic import Field

from investigation_world.experience.counterfactual import (
    CounterfactualReceipt,
    validate_counterfactual_receipt,
)
from investigation_world.experience.models import (
    CanonicalModel,
    CapabilityGap,
    ExperienceDiagnostics,
    ExperienceReference,
    FailureFamily,
    FailureMechanism,
    StructuralRecord,
)
from investigation_world.experience_foundry.admission import RecordedExperience
from investigation_world.trajectory import VisibilityClass, canonical_hash

_PRIVATE: Literal[VisibilityClass.EVALUATOR_PRIVATE] = VisibilityClass.EVALUATOR_PRIVATE


class InterventionDiagnostic(CanonicalModel):
    experience_id: str
    receipt_id: str
    source_semantic_fingerprint: str
    capability_digest: str
    capability_mapping: Literal["DECLARED_TASK_ASSOCIATION"] = "DECLARED_TASK_ASSOCIATION"
    criterion_scope: Literal["verifier_target_set_not_individual_contract_terms"] = (
        "verifier_target_set_not_individual_contract_terms"
    )
    affected_capability: str
    evidence_status: Literal["OBSERVED_CONTROLLED_CONTRAST"] = "OBSERVED_CONTROLLED_CONTRAST"
    mechanism_status: Literal["HYPOTHESIZED"] = "HYPOTHESIZED"
    causal_status: Literal["UNKNOWN"] = "UNKNOWN"
    direction_basis: Literal["verifier_target_counts_only"] = "verifier_target_counts_only"
    outcome_direction: Literal["improved", "worsened", "unchanged"]
    target_shortfall: float = Field(ge=0, le=1)
    diagnostics: ExperienceDiagnostics
    causal_candidate: StructuralRecord | None
    evidence_references: tuple[ExperienceReference, ...]
    residual_violations: dict[str, dict[str, list[str]]]
    unavailable: dict[str, str]
    visibility: Literal[VisibilityClass.EVALUATOR_PRIVATE] = _PRIVATE

    def public_payload(self):
        return {"status": "UNKNOWN", "reason": "evaluator_private"}

    def buyer_safe_payload(self):
        return self.public_payload()


class CapabilityFailureCandidate(CanonicalModel):
    """A sample-bound candidate deficit, not a measured agent capability or prerequisite."""

    family: FailureFamily
    gap: CapabilityGap
    status: Literal["HYPOTHESIZED"] = "HYPOTHESIZED"
    capability_mapping: Literal["DECLARED_TASK_ASSOCIATION"] = "DECLARED_TASK_ASSOCIATION"
    evidence_status: Literal["OBSERVED_BOUND_TASK_FAILURES"] = "OBSERVED_BOUND_TASK_FAILURES"
    frequency_scope: Literal["distinct_recorded_protocols_not_independent_agents"] = (
        "distinct_recorded_protocols_not_independent_agents"
    )
    evidence_references: tuple[ExperienceReference, ...]
    visibility: Literal[VisibilityClass.EVALUATOR_PRIVATE] = _PRIVATE

    def public_payload(self):
        return {"status": "UNKNOWN", "reason": "evaluator_private"}

    def buyer_safe_payload(self):
        return self.public_payload()


def diagnose_counterfactual(
    receipt: CounterfactualReceipt, *, source: RecordedExperience
) -> InterventionDiagnostic:
    """Revalidate retained artifacts and exact source; parsing/caller PASS is insufficient.

    The reference is qualified only as a valid solution to this pinned task. A changed
    action is not itself a policy error; even a positive contrast does not identify a
    model's mental mechanism, general recoverability or an independent causal effect.
    """
    checked = validate_counterfactual_receipt(receipt, source=source)
    before, after = checked.baseline.breakdown, checked.alternative.breakdown
    total = before["target_assertions_total"]
    if total <= 0 or after["target_assertions_total"] != total:
        raise ValueError("COMPARABLE_NONEMPTY_TARGET_SET_REQUIRED")
    shortfall = (total - before["target_assertions_met"]) / total
    changed = checked.bindings["original_call"] != checked.bindings["replacement_call"]
    difference = after["target_assertions_met"] - before["target_assertions_met"]
    direction: Literal["improved", "worsened", "unchanged"] = (
        "improved" if difference > 0 else "worsened" if difference < 0 else "unchanged"
    )
    digest = canonical_hash(checked.model_dump(mode="json"))
    ref = ExperienceReference(
        reference_id=checked.receipt_id,
        reference_type="validated_controlled_contrast",
        digest=digest,
        visibility=_PRIVATE,
        private_metadata={
            "source_experience_id": source.experience.experience_id,
            "source_digest": checked.source_digest,
            "capability_digest": checked.source.capability.content_digest,
            "criterion_scope": "verifier_target_set_not_individual_contract_terms",
            "branch_step": checked.branch.branch_step,
            "causal_status": "UNKNOWN",
        },
    )
    # This is alternative-outcome restoration, not a retry observed in the source run.
    restored = changed and shortfall > 0 and checked.recovery_status == "success"
    recovery = ref.model_copy(update={"reference_type": "counterfactual_valid_outcome_restoration"})
    divergence = ref.model_copy(update={"reference_type": "controlled_action_difference"})
    reasons = (
        "invariant_violations",
        "process_violations",
        "forbidden_actions_taken",
        "missing_required_actions",
        "missing_evidence_ids",
    )
    residuals = {
        label: {key: row[key] for key in reasons}
        for label, row in (("baseline", before), ("alternative", after))
    }
    unavailable = {
        "individual_failed_target": "Target counts only; individual failed target IDs unknown.",
        "causal_mechanism": "Contrast does not identify a mechanism or general causal effect.",
        "agent_capability": "Declared task capability, not measured agent competence.",
        "prerequisites": "No prerequisite intervention or transfer evidence.",
    }
    if not changed:
        unavailable["divergence"] = "Identical action; no intervention difference."
    if not restored:
        unavailable["recovery"] = (
            "No failed baseline followed by a changed, clean successful alternative."
        )
    candidate = None
    if changed:
        candidate = StructuralRecord(
            record_id="CAUSAL-CANDIDATE-" + digest,
            step=checked.branch.branch_step,
            record_type="causal_candidate",
            subject_references=(checked.receipt_id, source.experience.experience_id),
            attributes={
                "evidence_status": "OBSERVED_CONTROLLED_CONTRAST",
                "mechanism_status": "HYPOTHESIZED",
                "mechanism": FailureMechanism.UNKNOWN.value,
                "causal_status": "UNKNOWN",
                "hypothesis": "Action replacement may affect this pinned task's target set.",
                "outcome_direction": direction,
                "direction_basis": "verifier_target_counts_only",
                "target_counts": checked.preference["target_counts"],
                "residual_violations": residuals,
                "scope": "pinned_public_synthetic_task_only",
            },
            visibility=_PRIVATE,
        )
    return InterventionDiagnostic(
        experience_id=source.experience.experience_id,
        receipt_id=checked.receipt_id,
        source_semantic_fingerprint=checked.source.semantic_fingerprint,
        capability_digest=checked.source.capability.content_digest,
        affected_capability=checked.source.capability.capability_id,
        outcome_direction=direction,
        target_shortfall=shortfall,
        diagnostics=ExperienceDiagnostics(
            failure_mechanisms=(FailureMechanism.UNKNOWN,),
            first_divergence_reference=divergence if changed else None,
            recovery_point_references=(recovery,) if restored else (),
            successful_recovery_references=(recovery,) if restored else (),
            visibility=_PRIVATE,
        ),
        causal_candidate=candidate,
        evidence_references=(ref,),
        residual_violations=residuals,
        unavailable=unavailable,
    )


def intervention_failure_families(
    values: Iterable[tuple[CounterfactualReceipt, RecordedExperience]],
) -> tuple[CapabilityFailureCandidate, ...]:
    """Group observed task failures by declared capability; no graph promotion.

    Deduplicate semantic protocols, not path-bearing artifact identities. Frequency
    is descriptive sample count, not independent trials or a population failure rate.
    """
    groups: dict[tuple[str, str], dict[str, InterventionDiagnostic]] = defaultdict(dict)
    for receipt, source in values:
        report = diagnose_counterfactual(receipt, source=source)
        if report.target_shortfall == 0:
            continue
        key = (report.affected_capability, report.capability_digest)
        old = groups[key].get(report.source_semantic_fingerprint)
        if old is None or (report.experience_id, report.receipt_id) < (
            old.experience_id,
            old.receipt_id,
        ):
            groups[key][report.source_semantic_fingerprint] = report
    results = []
    for (capability, _), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        reports = sorted(members.values(), key=lambda r: r.experience_id)
        family = FailureFamily(
            member_experience_ids=tuple(r.experience_id for r in reports),
            affected_capability=capability,
            severity=max(r.target_shortfall for r in reports),
            mechanisms=(FailureMechanism.UNKNOWN,),
            visibility=_PRIVATE,
        )
        gap = CapabilityGap(
            capability=capability,
            supporting_failure_family_ids=(family.family_id,),
            frequency=len(reports),
            severity=family.severity,
            visibility=_PRIVATE,
        )
        results.append(
            CapabilityFailureCandidate(
                family=family,
                gap=gap,
                evidence_references=tuple(ref for r in reports for ref in r.evidence_references),
            )
        )
    return tuple(results)
