"""Fresh, bounded TRAIN selection; private candidate evidence, not training qualification."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import islice
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from investigation_world.capability_science import CapabilityGapEvidence, ingest_capability_failure
from investigation_world.capability_science.core import CapabilitySpec, Digest, ScienceRecord, Text
from investigation_world.experience import MachineExperience
from investigation_world.experience.counterfactual import (
    CounterfactualReceipt,
    validate_counterfactual_receipt,
)
from investigation_world.experience.counterfactual.validation import verify_recorded
from investigation_world.experience.diagnostics import intervention_failure_families
from investigation_world.experience_foundry.admission import (
    RecordedExperience,
    admit_experience,
    authorized_registry,
)
from investigation_world.foundry.models import CapabilityContract, DistributionSplit, RolloutTrace
from investigation_world.trajectory import VisibilityClass, canonical_hash

POOL_SCHEMA: Literal["veritas.experience-candidate-pool.v1"] = (
    "veritas.experience-candidate-pool.v1"
)
MAX_POOL = 256
MAX_GAP_PROTOCOLS = 64
_PRIVATE: Literal[VisibilityClass.EVALUATOR_PRIVATE] = VisibilityClass.EVALUATOR_PRIVATE
Reason = Literal[
    "selected",
    "non_train",
    "nonpublic_source",
    "heldout_overlap",
    "invalid_source",
    "no_useful_gap",
    "failed_not_training_candidate",
    "trivial_action_count",
    "duplicate_protocol",
    "stratum_quota_saturated",
    "hard_negative_budget",
    "selection_budget",
]
Role = Literal["verified_success_candidate", "private_hard_negative", "unassessed"]


class SelectionPolicy(ScienceRecord):
    schema_version: Literal["veritas.experience-selection-policy.v1"] = (
        "veritas.experience-selection-policy.v1"
    )
    version: Literal["1"] = "1"
    mode: Literal["representative", "random_control"] = "representative"
    seed: int = Field(default=0, strict=True, ge=0, le=2**32 - 1)
    max_items: int = Field(default=32, strict=True, ge=0, le=MAX_POOL)
    max_per_stratum: int = Field(default=1, strict=True, ge=1, le=MAX_POOL)
    min_actions: int = Field(default=2, strict=True, ge=1, le=MAX_POOL)
    max_hard_negatives: int = Field(default=0, strict=True, ge=0, le=MAX_POOL)
    target_capability_digests: tuple[Digest, ...] = ()
    heldout_task_ids: tuple[Text, ...] = ()
    heldout_source_digests: tuple[Digest, ...] = ()
    saturation_basis: Literal["policy_quota_not_empirical_mastery"] = (
        "policy_quota_not_empirical_mastery"
    )
    visibility: Literal[VisibilityClass.EVALUATOR_PRIVATE] = _PRIVATE

    @field_validator("target_capability_digests", "heldout_task_ids", "heldout_source_digests")
    @classmethod
    def canonical_sets(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if self.max_hard_negatives > self.max_items:
            raise ValueError("hard negative budget exceeds total selection budget")
        return self


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    slot_id: str
    input_digest: Digest
    experience_id: str
    reason: Reason
    role: Role = "unassessed"
    protocol_digest: Digest | None = None
    stratum_digest: Digest | None = None
    capability_digest: Digest | None = None
    gap_record_ids: tuple[str, ...] = ()
    verification_id: str | None = None
    source_fixture_digest: Digest | None = None
    recorded_execution_id: Digest | None = None
    recorded_cost: float | None = Field(default=None, ge=0)
    action_count: int | None = Field(default=None, ge=0)
    target_shortfall: float | None = Field(default=None, ge=0, le=1)


class SelectionResources(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    pool_entries: int = Field(ge=0)
    unique_input_snapshots: int = Field(ge=0)
    unique_validated_recordings: int = Field(ge=0)
    candidate_validation_attempts: int = Field(ge=0)
    training_admission_attempts: int = Field(ge=0)
    gap_input_protocols: int = Field(ge=0)
    distinct_gap_protocols: int = Field(ge=0)
    gap_receipt_validation_calls: int = Field(ge=0)
    gap_family_derivation_calls: int = Field(ge=0)
    selected_entries: int = Field(ge=0)
    rejected_entries: int = Field(ge=0)
    recorded_candidate_cost: float | None = Field(default=None, ge=0)
    known_candidate_recorded_cost: float | None = Field(default=None, ge=0)
    recorded_gap_execution_cost: float = Field(ge=0)
    known_union_recorded_cost: float | None = Field(default=None, ge=0)
    cost_unit: Literal["native_runtime_budget_units_not_compute_or_money"] = (
        "native_runtime_budget_units_not_compute_or_money"
    )
    generation_compute_cost: None = None
    teacher_tokens: None = None
    human_hours: None = None
    selection_wall_seconds: None = None
    selection_compute_cost: None = None
    accounting_complete: Literal[False] = False


class SelectionReport(ScienceRecord):
    schema_version: Literal["veritas.experience-selection-report.v1"] = (
        "veritas.experience-selection-report.v1"
    )
    policy: SelectionPolicy
    pool_schema: Literal["veritas.experience-candidate-pool.v1"] = POOL_SCHEMA
    pool_id: str
    gap_input_digest: Digest
    gaps: tuple[CapabilityGapEvidence, ...]
    eligibility_digest: Digest
    decisions: tuple[Decision, ...]
    selected_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    rejection_counts: dict[str, int]
    resources: SelectionResources
    training_qualified: Literal[False] = False
    training_usefulness: Literal["UNKNOWN"] = "UNKNOWN"
    causal_qualification: Literal["UNKNOWN"] = "UNKNOWN"
    diversity_scope: Literal["declared_capability_task_role_not_population_coverage"] = (
        "declared_capability_task_role_not_population_coverage"
    )
    visibility: Literal[VisibilityClass.EVALUATOR_PRIVATE] = _PRIVATE

    @model_validator(mode="after")
    def accounting(self) -> Self:
        selected = [d for d in self.decisions if d.reason == "selected"]
        rejected = Counter(d.reason for d in self.decisions if d.reason != "selected")
        if len({d.slot_id for d in self.decisions}) != len(self.decisions):
            raise ValueError("selection slots must be unique")
        if (
            self.selected_count != len(selected)
            or self.rejection_counts != dict(rejected)
            or self.rejected_count != len(self.decisions) - len(selected)
        ):
            raise ValueError("selection accounting mismatch")
        if (
            self.resources.pool_entries != len(self.decisions)
            or self.resources.selected_entries != self.selected_count
            or self.resources.rejected_entries != self.rejected_count
        ):
            raise ValueError("resource accounting mismatch")
        if len(selected) > self.policy.max_items or any(
            not d.gap_record_ids
            or not d.protocol_digest
            or not d.verification_id
            or d.role == "unassessed"
            for d in selected
        ):
            raise ValueError("selected candidates require bound evidence and policy budget")
        if (
            sum(d.role == "private_hard_negative" for d in selected)
            > self.policy.max_hard_negatives
        ):
            raise ValueError("hard negative budget mismatch")
        return self


def _bounded(values: Iterable, limit: int) -> tuple:
    items = tuple(islice(values, limit + 1))
    if len(items) > limit:
        raise ValueError("selection input bound exceeded")
    return items


def _source_payload(source: RecordedExperience) -> dict:
    return {
        "experience": source.experience.model_dump(mode="json"),
        "companion": source.companion.model_dump(mode="json"),
        "capability": source.capability.model_dump(mode="json"),
    }


def _protocol_digest(source: RecordedExperience, breakdown: dict) -> str:
    """Verifier-relevant behavior for the pinned, freshly validated provider only."""
    return canonical_hash(
        {
            "fixture": source.companion.metadata["source_digest"],
            "capability": CapabilitySpec(contract=source.capability).contract_digest,
            "actions": [
                (event.payload["action_name"], event.payload["kwargs"])
                for event in source.companion.events
                if event.event_type == "act"
            ],
            "initial": source.companion.initial_state_hash,
            "final": source.companion.final_state_hash,
            "breakdown": breakdown,
        }
    )


def _execution_id(source: RecordedExperience) -> str:
    # Cached reverifications/annotations change material pool identity, not the
    # authenticated original recording. Use only after fresh provider validation.
    return canonical_hash(
        {
            "trajectory": source.experience.trajectory.trajectory_id,
            "companion": source.companion.trace_id,
        }
    )


def _copy_source(source: RecordedExperience) -> RecordedExperience:
    payload = _source_payload(source)
    return RecordedExperience(
        MachineExperience.model_validate(payload["experience"]),
        RolloutTrace.model_validate(payload["companion"]),
        CapabilityContract.model_validate(payload["capability"]),
    )


def _boundary(source: RecordedExperience, policy: SelectionPolicy) -> Reason | None:
    # Check declared partition/visibility before any evaluator or artifact access.
    trajectory = source.experience.trajectory
    if source.companion.split != DistributionSplit.TRAIN or (
        trajectory.task.split is not None and trajectory.task.split != DistributionSplit.TRAIN
    ):
        return "non_train"
    if source.experience.visibility != VisibilityClass.PUBLIC or (
        trajectory.visibility != VisibilityClass.PUBLIC
    ):
        return "nonpublic_source"
    digests = {source.companion.metadata.get("source_digest")}
    digests.update(p.source_digest for p in trajectory.provenance)
    if (
        trajectory.task.task_id in policy.heldout_task_ids
        or source.companion.task_id in policy.heldout_task_ids
        or set(policy.heldout_source_digests).intersection(digests)
    ):
        return "heldout_overlap"
    return None


@dataclass
class _Candidate:
    decision: Decision
    tie: str


def _choose(candidates: list[_Candidate], policy: SelectionPolicy) -> dict[str, Reason]:
    """Quota-constrained seeded control or balanced, compact stratum representatives."""
    remaining = list(candidates)
    counts: Counter[str | None] = Counter()
    reasons: dict[str, Reason] = {}
    selected = negative = 0
    while remaining:
        if policy.mode == "random_control":
            item = min(remaining, key=lambda c: (c.tie, c.decision.slot_id))
        else:
            item = min(
                remaining,
                key=lambda c: (
                    counts[c.decision.stratum_digest],
                    c.decision.recorded_cost,
                    c.tie,
                    c.decision.slot_id,
                ),
            )
        remaining.remove(item)
        row = item.decision
        if counts[row.stratum_digest] >= policy.max_per_stratum:
            reason: Reason = "stratum_quota_saturated"
        elif row.role == "private_hard_negative" and negative >= policy.max_hard_negatives:
            reason = "hard_negative_budget"
        elif selected >= policy.max_items:
            reason = "selection_budget"
        else:
            reason = "selected"
            counts[row.stratum_digest] += 1
            selected += 1
            negative += row.role == "private_hard_negative"
        reasons[row.slot_id] = reason
    return reasons


def select_experiences(
    sources: Iterable[RecordedExperience],
    *,
    gap_sources: Iterable[tuple[CounterfactualReceipt, RecordedExperience]] = (),
    policy: SelectionPolicy | None = None,
) -> SelectionReport:
    """Reverify the actual bounded pool and recompute gap evidence on every invocation.

    Only the existing pinned public native TRAIN provider is currently supported.
    Hard negatives are evaluator-private analysis candidates, never SFT admission.
    No model answer text, hidden label selection, trainer or model call is introduced.
    """
    policy = (policy or SelectionPolicy()).checked()
    raw = _bounded(sources, MAX_POOL)
    gap_inputs = _bounded(gap_sources, MAX_GAP_PROTOCOLS)
    # A contaminated evidence pool aborts before reading any receipt outcomes.
    if any(_boundary(source, policy) for _, source in gap_inputs):
        raise ValueError("gap evidence violates TRAIN/public/heldout boundary")
    try:
        gap_inputs = tuple(
            (CounterfactualReceipt.model_validate(r.model_dump(mode="json")), _copy_source(s))
            for r, s in gap_inputs
        )
        # Validate every raw receipt, even ones later removed as behavioral aliases.
        # Provider snapshot fingerprints retain submission prose; prose must not
        # manufacture the selector's minimum distinct failure-protocol evidence.
        gap_inputs = tuple((validate_counterfactual_receipt(r, source=s), s) for r, s in gap_inputs)
        representatives: dict[str, tuple[CounterfactualReceipt, RecordedExperience]] = {}
        for receipt, source in sorted(
            gap_inputs,
            key=lambda pair: (
                pair[1].experience.experience_id,
                pair[0].receipt_id,
            ),
        ):
            key = _protocol_digest(source, receipt.source.breakdown)
            representatives.setdefault(key, (receipt, source))
        distinct_gap_inputs = tuple(representatives[key] for key in sorted(representatives))
        families = intervention_failure_families(distinct_gap_inputs)
        gaps = tuple(ingest_capability_failure(f, sources=distinct_gap_inputs) for f in families)
    except (ValueError, OSError):
        raise ValueError("gap evidence failed fresh provider validation") from None
    gaps = tuple(sorted(gaps, key=lambda g: g.record_id))
    gap_digest = canonical_hash(
        sorted(
            canonical_hash({"receipt": r.model_dump(mode="json"), "source": _source_payload(s)})
            for r, s in gap_inputs
        )
    )
    targets: dict[str, tuple[str, ...]] = {}
    for gap in gaps:
        key = gap.capability_spec.contract_digest
        if not policy.target_capability_digests or key in policy.target_capability_digests:
            targets[key] = tuple(sorted((*targets.get(key, ()), gap.record_id)))

    ordered = sorted((canonical_hash(_source_payload(s)), i, s) for i, s in enumerate(raw))
    occurrences: Counter[str] = Counter()
    decisions: list[Decision] = []
    eligible: list[_Candidate] = []
    protocols: set[str] = set()
    costs: dict[str, float] = {}
    validated_snapshots: set[str] = set()
    validation_attempts = admission_attempts = 0
    for digest, _, source in ordered:
        occurrence = occurrences[digest]
        occurrences[digest] += 1
        slot = digest + ":" + str(occurrence)
        data = dict(
            slot_id=slot, input_digest=digest, experience_id=source.experience.experience_id
        )
        reason = _boundary(source, policy)
        if reason:
            decisions.append(Decision(**data, reason=reason))
            continue
        validation_attempts += 1
        try:
            source, evidence, verification, breakdown = verify_recorded(_copy_source(source))
            total = breakdown["target_assertions_total"]
            met = breakdown["target_assertions_met"]
            if total <= 0 or not 0 <= met <= total:
                raise ValueError("invalid verifier target counts")
        except (ValueError, OSError):
            decisions.append(Decision(**data, reason="invalid_source"))
            continue
        cost = float(source.companion.total_cost)
        capability = CapabilitySpec(contract=source.capability).contract_digest
        role: Role = "private_hard_negative"
        failures = (
            "invariant_violations",
            "missing_required_actions",
            "forbidden_actions_taken",
            "missing_evidence_ids",
            "process_violations",
        )
        explicit_failure = (
            met < total or breakdown["outcome"] != 1.0 or any(breakdown[key] for key in failures)
        )
        if not explicit_failure:
            admission_attempts += 1
            try:
                admit_experience(source, registry=authorized_registry())
                role = "verified_success_candidate"
            except (ValueError, OSError):
                # Integrity/admission errors are not evidence of a useful negative.
                decisions.append(Decision(**data, reason="invalid_source"))
                continue
        execution_id = _execution_id(source)
        if execution_id in costs and costs[execution_id] != cost:
            raise ValueError("same authenticated recording has inconsistent resource cost")
        costs[execution_id] = cost
        validated_snapshots.add(digest)
        actions = [(a.action_name, a.parameters) for a in evidence.action_events]
        fixture = source.companion.metadata["source_digest"]
        protocol = _protocol_digest(source, breakdown)
        # Neither artifact location/ZIP timestamp nor free-form submission prose
        # buys another example. This is protocol equality, not near-duplicate science.
        stratum = canonical_hash({"capability": capability, "fixture": fixture, "role": role})
        data.update(
            role=role,
            protocol_digest=protocol,
            stratum_digest=stratum,
            capability_digest=capability,
            gap_record_ids=targets.get(capability, ()),
            verification_id=verification.record_id,
            source_fixture_digest=fixture,
            recorded_execution_id=execution_id,
            recorded_cost=cost,
            action_count=len(actions),
            target_shortfall=(total - met) / total,
        )
        if not targets.get(capability):
            reason = "no_useful_gap"
        elif role == "private_hard_negative" and policy.max_hard_negatives == 0:
            reason = "failed_not_training_candidate"
        elif len(actions) < policy.min_actions:
            reason = "trivial_action_count"
        elif protocol in protocols:
            reason = "duplicate_protocol"
        else:
            reason = "selected"  # Scheduler applies final quota/budget reason below.
            protocols.add(protocol)
        decision = Decision(**data, reason=reason)
        decisions.append(decision)
        if reason == "selected":
            eligible.append(
                _Candidate(decision, canonical_hash({"seed": policy.seed, "protocol": protocol}))
            )
    eligibility = canonical_hash(
        {
            "pool": [d.input_digest for d in decisions],
            "gaps": gap_digest,
            "policy": policy.model_dump(mode="json", exclude={"record_id", "mode", "seed"}),
            "eligible": sorted((c.decision.protocol_digest, c.decision.role) for c in eligible),
        }
    )
    chosen = _choose(eligible, policy)
    decisions = [
        d.model_copy(update={"reason": chosen[d.slot_id]}) if d.slot_id in chosen else d
        for d in decisions
    ]
    rejected = Counter(d.reason for d in decisions if d.reason != "selected")
    selected = sum(d.reason == "selected" for d in decisions)
    gap_costs = {
        _execution_id(execution.recorded()): float(execution.companion.total_cost)
        for receipt, _ in gap_inputs
        for execution in (receipt.source, receipt.baseline, receipt.alternative, receipt.repeated)
    }
    known = sum(costs.values()) if costs or not raw else None
    union = {**gap_costs, **costs}
    resources = SelectionResources(
        pool_entries=len(raw),
        unique_input_snapshots=len(occurrences),
        unique_validated_recordings=len(costs),
        candidate_validation_attempts=validation_attempts,
        training_admission_attempts=admission_attempts,
        gap_input_protocols=len(gap_inputs),
        distinct_gap_protocols=len(distinct_gap_inputs),
        gap_receipt_validation_calls=len(gap_inputs),
        gap_family_derivation_calls=1 + len(gaps),
        selected_entries=selected,
        rejected_entries=len(raw) - selected,
        recorded_candidate_cost=(
            sum(costs.values()) if validated_snapshots == occurrences.keys() else None
        ),
        known_candidate_recorded_cost=known,
        recorded_gap_execution_cost=sum(gap_costs.values()),
        known_union_recorded_cost=sum(union.values()) if union or not raw else None,
    )
    return SelectionReport(
        policy=policy,
        pool_id="POOL-"
        + canonical_hash({"schema": POOL_SCHEMA, "entries": [d.input_digest for d in decisions]}),
        gap_input_digest=gap_digest,
        gaps=gaps,
        eligibility_digest=eligibility,
        decisions=tuple(decisions),
        selected_count=selected,
        rejected_count=len(raw) - selected,
        rejection_counts=dict(sorted(rejected.items())),
        resources=resources,
    )


def validate_selection(
    report: SelectionReport,
    sources: Iterable[RecordedExperience],
    *,
    gap_sources: Iterable[tuple[CounterfactualReceipt, RecordedExperience]] = (),
    policy: SelectionPolicy,
) -> SelectionReport:
    """A parsed/self-hashed report is not current-source attestation; recompute it."""
    checked = report.checked()
    policy = policy.checked()
    if checked.policy != policy:
        raise ValueError("selection policy does not match expected policy")
    expected = select_experiences(sources, gap_sources=gap_sources, policy=policy)
    if checked != expected:
        raise ValueError("selection report does not match freshly validated actual inputs")
    return expected
