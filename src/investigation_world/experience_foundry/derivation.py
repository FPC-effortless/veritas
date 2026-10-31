"""Evidence-bound candidate transforms, deliberately separate from successful SFT admission.

ponytail: the existing public financial TRAIN recorder is the only validated profile.
Additional profiles need an equivalent source/receipt validator, not caller PASS fields.
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, Self, get_args

from pydantic import Field, TypeAdapter, model_validator

from investigation_world.capability_science import (
    AcquisitionCurve,
    CapabilityGapEvidence,
    CapabilitySpec,
    ingest_capability_failure,
)
from investigation_world.capability_science.core import (
    Digest,
    ScienceRecord,
    Text,
    validate_references,
)
from investigation_world.experience import ExperienceReference
from investigation_world.experience.counterfactual import (
    CounterfactualReceipt,
    validate_counterfactual_receipt,
)
from investigation_world.experience.counterfactual.validation import verify_recorded
from investigation_world.experience.diagnostics import (
    DiagnosticReport,
    diagnose_counterfactual,
    diagnose_experience,
    intervention_failure_families,
)
from investigation_world.experience_foundry.admission import (
    RecordedExperience,
    authorized_registry,
    public_training_fixture,
)
from investigation_world.trajectory import ReverificationRecord, VisibilityClass, canonical_hash
from investigation_world.trajectory.reverify import OperationalReplayEvidence

TransformKind = Literal[
    "negative",
    "verifier_feedback",
    "evidence_selection",
    "next_state",
    "alternative_action",
    "counterfactual",
    "recovery",
    "preference",
    "structured_repair",
    "curriculum",
    "procedure",
    "abstraction",
]
_CONTRAST = {"alternative_action", "counterfactual", "recovery", "preference", "structured_repair"}
_REASONS = (
    "invariant_violations",
    "process_violations",
    "forbidden_actions_taken",
    "missing_required_actions",
    "missing_evidence_ids",
)


class TransformRule(ScienceRecord):
    """Independent policy revision; implementation version is not caller-invented."""

    kind: TransformKind
    revision: Text = "1"
    implementation_version: Literal["1"] = "1"
    enabled: bool = True


class TransformPolicy(ScienceRecord):
    schema_version: Literal["veritas.learning-transform-policy.v1"] = (
        "veritas.learning-transform-policy.v1"
    )
    rules: tuple[TransformRule, ...] = Field(
        default_factory=lambda: tuple(
            TransformRule(kind=kind, enabled=kind not in {"procedure", "abstraction"})
            for kind in get_args(TransformKind)
        )
    )
    per_family_transform_quota: int | None = Field(default=None, ge=1, strict=True)
    require_saturation_evidence: bool = False

    @model_validator(mode="after")
    def unique_rules(self) -> Self:
        if len({rule.kind for rule in self.rules}) != len(self.rules):
            raise ValueError("DUPLICATE_TRANSFORM_RULE")
        return self


class PrivateRecord(ScienceRecord):
    visibility: Literal[VisibilityClass.EVALUATOR_PRIVATE] = VisibilityClass.EVALUATOR_PRIVATE

    @model_validator(mode="after")
    def forbid_sealed_widening(self) -> Self:
        if _contains_sealed(self.model_dump(mode="json")):
            raise ValueError("SEALED_INPUT_REQUIRES_STRICTER_BOUNDARY")
        return self


class DerivationLineage(PrivateRecord):
    source: ExperienceReference
    trajectory: ExperienceReference
    companion: ExperienceReference
    verifier: ExperienceReference
    reverification: ExperienceReference
    diagnostic: ExperienceReference
    native_receipt: ExperienceReference
    portable_contract: ExperienceReference
    capability_spec: CapabilitySpec
    recorded_runtime_digest: Text
    recorded_source_split: Literal["TRAIN"] = "TRAIN"
    canonical_split: None = None
    counterfactual: ExperienceReference | None = None
    family_evidence: tuple[ExperienceReference, ...] = ()
    family_ids: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def full_references(self) -> Self:
        validate_references(
            (
                self.source,
                self.trajectory,
                self.companion,
                self.verifier,
                self.reverification,
                self.diagnostic,
                self.native_receipt,
                self.portable_contract,
                *self.family_evidence,
                *((self.counterfactual,) if self.counterfactual else ()),
            )
        )
        if not len(self.family_evidence) == len(self.family_ids) == len(self.gap_ids):
            raise ValueError("FAMILY_GAP_LINEAGE_MISMATCH")
        return self


class CandidateLearningAsset(PrivateRecord):
    schema_version: Literal["veritas.candidate-learning-asset.v1"] = (
        "veritas.candidate-learning-asset.v1"
    )
    transform: TransformRule
    lineage: DerivationLineage
    material: dict[str, Any] = Field(min_length=1)
    training_qualified: Literal[False] = False
    training_usefulness: Literal["UNKNOWN"] = "UNKNOWN"
    causal_qualification: Literal["UNKNOWN"] = "UNKNOWN"

    @property
    def material_digest(self) -> str:
        checked = self.checked()
        return canonical_hash({"kind": checked.transform.kind, "material": checked.material})

    def trainer_payload(self) -> dict[str, Any]:
        self.checked()
        raise ValueError("CANDIDATE_NOT_TRAINING_ADMITTED")


class DerivationRejection(PrivateRecord):
    source_id: str
    transform_kind: TransformKind
    reason: str
    evidence: dict[str, Any]
    candidate: CandidateLearningAsset | None = None


class LearningAssetCompilation(PrivateRecord):
    schema_version: Literal["veritas.learning-asset-compilation.v1"] = (
        "veritas.learning-asset-compilation.v1"
    )
    policy: TransformPolicy
    sources: tuple[ExperienceReference, ...]
    receipts: tuple[ExperienceReference, ...]
    source_occurrences: dict[str, int]
    receipt_occurrences: dict[str, int]
    frozen_panel_task_ids: tuple[Text, ...]
    frozen_panel_source_digests: tuple[Digest, ...]
    diagnostics: tuple[DiagnosticReport, ...]
    family_evidence: tuple[CapabilityGapEvidence, ...]
    saturation_evidence: tuple[AcquisitionCurve, ...]
    assets: tuple[CandidateLearningAsset, ...]
    rejections: tuple[DerivationRejection, ...]
    counts: dict[str, int | None]
    saturation_status: Literal["UNKNOWN"] = "UNKNOWN"
    saturation_reason: Literal["NO_ATTESTED_SATURATION_EVIDENCE"] = (
        "NO_ATTESTED_SATURATION_EVIDENCE"
    )
    training_qualified: Literal[False] = False
    causal_qualification: Literal["UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def reconcile_counts(self) -> Self:
        reasons = Counter(r.reason for r in self.rejections)
        expected = {
            "distinct_sources": len(self.sources),
            "distinct_receipts": len(self.receipts),
            "selected": len(self.assets),
            "rejected": len(self.rejections),
            "proposed": len(self.assets) + sum(r.candidate is not None for r in self.rejections),
            "duplicate": reasons["DUPLICATE_MATERIAL"],
            "trivial": reasons["TRIVIAL_IDENTICAL_ACTION"],
            "semantic_alias": reasons["SEMANTIC_SOURCE_ALIAS"],
            "quota": reasons["POLICY_FAMILY_QUOTA"],
            "saturation_unknown": reasons["SATURATION_UNKNOWN"],
            "saturated": None,
        }
        for kind, occurrences in (
            ("sources", self.source_occurrences),
            ("receipts", self.receipt_occurrences),
        ):
            if set(occurrences) != {r.reference_id for r in getattr(self, kind)} or any(
                type(count) is not int or count < 1 for count in occurrences.values()
            ):
                raise ValueError("INVALID_INPUT_OCCURRENCES")
            expected["input_" + kind] = sum(occurrences.values())
            expected["duplicate_" + kind] = sum(occurrences.values()) - len(occurrences)
        if self.counts != expected:
            raise ValueError("COMPILATION_COUNT_MISMATCH")
        return self


@dataclass(frozen=True)
class _Validated:
    source: RecordedExperience
    evidence: OperationalReplayEvidence
    verification: ReverificationRecord
    feedback: dict[str, Any]
    diagnostics: DiagnosticReport


def _ref(kind: str, identity: str, value: Any) -> ExperienceReference:
    return ExperienceReference(
        reference_id=identity,
        reference_type=kind,
        digest=canonical_hash(value),
        visibility=VisibilityClass.EVALUATOR_PRIVATE,
    )


def _actions(source: RecordedExperience) -> list[dict[str, Any]]:
    return [
        {key: copy.deepcopy(event.payload[key]) for key in ("method", "args", "kwargs")}
        for event in source.companion.events
        if event.event_type == "act"
    ]


def _feedback(raw: dict[str, Any]) -> dict[str, Any]:
    required = (*_REASONS, "outcome", "target_assertions_total", "target_assertions_met")
    if any(key not in raw for key in required):
        raise ValueError("COMPLETE_VERIFIER_FEEDBACK_REQUIRED")
    return {key: copy.deepcopy(raw[key]) for key in required}


def _failed(feedback: dict[str, Any]) -> bool:
    return (
        feedback["outcome"] < 1
        or feedback["target_assertions_met"] < feedback["target_assertions_total"]
        or any(feedback[key] for key in _REASONS)
    )


def _lineage(
    value: _Validated,
    gaps: tuple[CapabilityGapEvidence, ...],
    receipt: CounterfactualReceipt | None,
) -> DerivationLineage:
    source, evidence, record = value.source, value.evidence, value.verification
    trajectory = source.experience.trajectory
    native = evidence.native_submission
    assert native is not None  # verify_recorded requires retained native receipt evidence.
    relevant = tuple(g for g in gaps if source.experience.experience_id in g.source_digests)
    return DerivationLineage(
        source=_ref("machine_experience", source.experience.experience_id, source.experience),
        trajectory=_ref("trajectory_v2", trajectory.trajectory_id, trajectory),
        companion=_ref("original_rollout_companion", source.companion.trace_id, source.companion),
        verifier=_ref(
            "verifier",
            f"{trajectory.verifier.verifier_id}:{trajectory.verifier.version}",
            trajectory.verifier,
        ),
        reverification=_ref("fresh_reverification", record.record_id, record),
        diagnostic=_ref(
            "diagnostic_report",
            "diagnostic-" + canonical_hash(value.diagnostics),
            value.diagnostics,
        ),
        native_receipt=_ref("native_submission_receipt", native.receipt_id, native),
        portable_contract=_ref(
            "portable_contract", evidence.portable_contract.contract_id, evidence.portable_contract
        ),
        capability_spec=CapabilitySpec(
            contract=source.capability, visibility=VisibilityClass.EVALUATOR_PRIVATE
        ),
        recorded_runtime_digest=source.companion.runtime_version,
        counterfactual=_ref("validated_counterfactual", receipt.receipt_id, receipt)
        if receipt
        else None,
        family_evidence=tuple(_ref("capability_gap_evidence", g.record_id, g) for g in relevant),
        family_ids=tuple(g.candidate.family.family_id for g in relevant),
        gap_ids=tuple(g.candidate.gap.gap_id for g in relevant),
    )


def _source_material(kind: TransformKind, value: _Validated) -> dict[str, Any] | None:
    evidence, feedback = value.evidence, value.feedback
    if kind == "verifier_feedback":
        return {"feedback": feedback, "component_scores": value.verification.component_scores}
    if kind == "negative":
        return (
            {
                "actions": _actions(value.source),
                "submission": evidence.submission.model_dump(mode="json"),
                "feedback": feedback,
            }
            if _failed(feedback)
            else None
        )
    if kind == "evidence_selection":
        case, _ = public_training_fixture()
        return {
            "available_public_record_ids": sorted(r.record_id for r in case.episode.records),
            "submitted_evidence_ids": list(evidence.submission.evidence_ids),
            "missing_required_evidence_ids": feedback["missing_evidence_ids"],
            "selection_quality": "UNKNOWN",
            "scope": "recorded_selection_not_optimal_policy",
        }
    if kind == "next_state":
        if not evidence.action_events:
            return None
        state = copy.deepcopy(evidence.initial_state)
        rows = []
        for action in evidence.action_events:
            before = copy.deepcopy(state)
            state.update(copy.deepcopy(action.state_changes))
            rows.append(
                {
                    "action": action.action_name,
                    "parameters": action.parameters,
                    "state_before": before,
                    "state_after": copy.deepcopy(state),
                }
            )
        return {
            "transitions": rows,
            "target_kind": "observed_simulator_state",
            "predictive_validation": "UNKNOWN",
        }
    return None


def _contrast_material(kind: TransformKind, receipt: CounterfactualReceipt) -> dict[str, Any]:
    actions = {
        "baseline": _actions(receipt.baseline.recorded()),
        "alternative": _actions(receipt.alternative.recorded()),
    }
    if kind == "alternative_action":
        return {
            "step": receipt.branch.branch_step,
            "original": receipt.bindings["original_call"],
            "alternative": receipt.bindings["replacement_call"],
            "public_at_cut": receipt.public_at_cut,
        }
    if kind == "preference":
        return {"actions": actions, "preference": receipt.preference}
    if kind == "recovery":
        return {
            "actions": actions,
            "feedback": _feedback(receipt.alternative.breakdown),
            "recovery_kind": "counterfactual_outcome_restoration",
        }
    if kind == "structured_repair":
        return {
            "step": receipt.branch.branch_step,
            "replacement": receipt.bindings["replacement_call"],
            "state_delta": receipt.state_delta,
            "outcome_delta": receipt.outcome_delta,
        }
    return {
        "actions": actions,
        "state_delta": receipt.state_delta,
        "outcome_delta": receipt.outcome_delta,
        "repeatability": "VERIFIED_SIMULATED_CONTRAST",
    }


def _contains_sealed(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("visibility") == VisibilityClass.SEALED or any(
            _contains_sealed(child) for child in value.values()
        )
    if isinstance(value, (tuple, list)):
        return any(_contains_sealed(child) for child in value)
    return False


def _check_exclusions(
    source: RecordedExperience, task_ids: tuple[str, ...], source_digests: tuple[str, ...]
) -> None:
    commitments = {
        canonical_hash(source.experience),
        source.companion.metadata["source_digest"],
        *(p.source_digest for p in source.experience.trajectory.provenance),
    }
    if source.companion.task_id in task_ids or commitments.intersection(source_digests):
        raise ValueError("FROZEN_PANEL_OVERLAP")


def compile_learning_assets(
    sources: Iterable[RecordedExperience],
    *,
    receipts: Iterable[CounterfactualReceipt] = (),
    policy: TransformPolicy | None = None,
    saturation_evidence: Iterable[AcquisitionCurve] = (),
    frozen_panel_task_ids: tuple[str, ...] = (),
    frozen_panel_source_digests: tuple[str, ...] = (),
) -> LearningAssetCompilation:
    """Revalidate actual sources/artifacts; never execute a trainer or generated action.

    Saturation observations are retained, not attested. CAP-001's measurement contract
    cannot currently establish model execution; the optional evidence-required gate
    rejects UNKNOWN, never relabels a quota or a supplied plateau as empirical mastery.
    """
    policy = (policy or TransformPolicy()).checked()
    if _contains_sealed(policy.model_dump(mode="json")):
        raise ValueError("SEALED_INPUT_REQUIRES_STRICTER_BOUNDARY")
    # Normalize once, before membership checks, using the same stored contract.
    frozen_panel_task_ids = tuple(
        sorted(set(TypeAdapter(tuple[Text, ...]).validate_python(frozen_panel_task_ids)))
    )
    frozen_panel_source_digests = tuple(
        sorted(set(TypeAdapter(tuple[Digest, ...]).validate_python(frozen_panel_source_digests)))
    )
    inputs, receipt_inputs = tuple(sources), tuple(receipts)
    known: dict[str, _Validated] = {}
    duplicate_sources = duplicate_receipts = 0
    source_occurrences: Counter[str] = Counter()
    receipt_occurrences: Counter[str] = Counter()
    for original in inputs:
        if _contains_sealed(
            {
                "experience": original.experience.model_dump(mode="json"),
                "companion": original.companion.model_dump(mode="json"),
                "capability": original.capability.model_dump(mode="json"),
            }
        ):
            raise ValueError("SEALED_SOURCE_EVIDENCE_UNSUPPORTED")
        source, evidence, verification, raw = verify_recorded(original)
        sid = source.experience.experience_id
        source_occurrences[sid] += 1
        _check_exclusions(source, frozen_panel_task_ids, frozen_panel_source_digests)
        if sid in known:
            if known[sid].source != source:
                raise ValueError("CONFLICTING_SOURCE_IDENTITY")
            duplicate_sources += 1
            continue
        known[sid] = _Validated(
            source,
            evidence,
            verification,
            _feedback(raw),
            diagnose_experience(source.experience, registry=authorized_registry()),
        )
    checked_receipts: dict[str, CounterfactualReceipt] = {}
    for receipt in receipt_inputs:
        if _contains_sealed(receipt.model_dump(mode="json")):
            raise ValueError("SEALED_RECEIPT_EVIDENCE_UNSUPPORTED")
        sid = receipt.source.experience.experience_id
        if sid not in known:
            raise ValueError("COUNTERFACTUAL_SOURCE_NOT_IN_INPUT")
        checked = validate_counterfactual_receipt(receipt, source=known[sid].source)
        for execution in (checked.baseline, checked.alternative, checked.repeated):
            _check_exclusions(
                execution.recorded(), frozen_panel_task_ids, frozen_panel_source_digests
            )
        receipt_occurrences[checked.receipt_id] += 1
        if checked.receipt_id in checked_receipts:
            if checked_receipts[checked.receipt_id] != checked:
                raise ValueError("CONFLICTING_RECEIPT_IDENTITY")
            duplicate_receipts += 1
        checked_receipts[checked.receipt_id] = checked
    pairs = tuple(
        (r, known[r.source.experience.experience_id].source)
        for _, r in sorted(checked_receipts.items())
    )
    gaps = tuple(
        ingest_capability_failure(c, sources=pairs) for c in intervention_failure_families(pairs)
    )
    # Provider family membership is exact and may omit semantically duplicate protocols.
    # Reject evidenced aliases rather than assigning them another source's family identity.
    members = {sid for gap in gaps for sid in gap.source_digests}
    aliases: dict[str, dict[str, Any]] = {}
    for receipt, source in pairs:
        sid = source.experience.experience_id
        equivalent = [
            (r, s)
            for r, s in pairs
            if s.experience.experience_id in members
            and r.source.semantic_fingerprint == receipt.source.semantic_fingerprint
        ]
        if sid not in members and equivalent:
            representative, member = min(
                equivalent, key=lambda pair: (pair[1].experience.experience_id, pair[0].receipt_id)
            )
            aliases[sid] = {
                "semantic_fingerprint": receipt.source.semantic_fingerprint,
                "representative_source_id": member.experience.experience_id,
                "alias_receipt": _ref(
                    "validated_counterfactual", receipt.receipt_id, receipt
                ).model_dump(mode="json"),
                "representative_receipt": _ref(
                    "validated_counterfactual", representative.receipt_id, representative
                ).model_dump(mode="json"),
                "family_evidence_ids": [
                    g.record_id for g in gaps if member.experience.experience_id in g.source_digests
                ],
            }
    curves = tuple(
        sorted((curve.checked() for curve in saturation_evidence), key=lambda c: c.record_id)
    )
    if any(_contains_sealed(curve.model_dump(mode="json")) for curve in curves):
        raise ValueError("SEALED_SATURATION_EVIDENCE_UNSUPPORTED")
    specs = {_lineage(v, (), None).capability_spec.contract_digest for v in known.values()}
    if any(c.points[0].population.capability.contract_digest not in specs for c in curves):
        raise ValueError("SATURATION_CAPABILITY_BINDING_MISMATCH")
    proposed: list[CandidateLearningAsset] = []
    rejected: list[DerivationRejection] = []

    def reject(sid, rule, reason, evidence, candidate=None):
        rejected.append(
            DerivationRejection(
                source_id=sid,
                transform_kind=rule.kind,
                reason=reason,
                evidence=evidence,
                candidate=candidate,
            )
        )

    for sid, value in sorted(known.items()):
        local_receipts = tuple(r for r, s in pairs if s.experience.experience_id == sid)
        lineage = _lineage(value, gaps, None)
        contrasts = {
            r.receipt_id: diagnose_counterfactual(r, source=value.source) for r in local_receipts
        }
        for rule in sorted(policy.rules, key=lambda r: r.kind):
            basis = {"rule_id": rule.record_id, "source_digest": lineage.source.digest}
            if not rule.enabled:
                reject(sid, rule, "FEATURE_DISABLED", basis)
                continue
            if rule.kind in {"procedure", "abstraction"}:
                reject(sid, rule, "PROVIDER_UNAVAILABLE", basis)
                continue
            if sid in aliases:
                reject(sid, rule, "SEMANTIC_SOURCE_ALIAS", {**basis, **aliases[sid]})
                continue
            if rule.kind in _CONTRAST:
                if not local_receipts:
                    reject(sid, rule, "COUNTERFACTUAL_EVIDENCE_REQUIRED", basis)
                for receipt in local_receipts:
                    proof = {
                        **basis,
                        "receipt_id": receipt.receipt_id,
                        "receipt_digest": canonical_hash(receipt),
                    }
                    if receipt.bindings["original_call"] == receipt.bindings["replacement_call"]:
                        reject(sid, rule, "TRIVIAL_IDENTICAL_ACTION", proof)
                        continue
                    diagnostic = contrasts[receipt.receipt_id]
                    if (
                        rule.kind in {"recovery", "structured_repair"}
                        and not diagnostic.diagnostics.successful_recovery_references
                    ):
                        reject(sid, rule, "VERIFIED_RESTORATION_REQUIRED", proof)
                        continue
                    if rule.kind == "preference" and receipt.preference["preferred"] == "NONE":
                        reject(sid, rule, "SUPPORTED_PREFERENCE_REQUIRED", proof)
                        continue
                    proposed.append(
                        CandidateLearningAsset(
                            transform=rule,
                            lineage=_lineage(value, gaps, receipt),
                            material=copy.deepcopy(_contrast_material(rule.kind, receipt)),
                        )
                    )
            elif rule.kind == "curriculum":
                if not lineage.family_evidence:
                    reject(sid, rule, "FAMILY_GAP_EVIDENCE_REQUIRED", basis)
                    continue
                proposed.append(
                    CandidateLearningAsset(
                        transform=rule,
                        lineage=lineage,
                        material={
                            "actions": _actions(value.source),
                            "feedback": value.feedback,
                            "challenge_scope": "observed_bound_task_failure_not_general_capability",
                        },
                    )
                )
            else:
                material = _source_material(rule.kind, value)
                if material is None:
                    reject(
                        sid,
                        rule,
                        "OBSERVED_FAILURE_REQUIRED"
                        if rule.kind == "negative"
                        else "OBSERVED_STATE_TRANSITION_REQUIRED",
                        basis,
                    )
                else:
                    proposed.append(
                        CandidateLearningAsset(
                            transform=rule, lineage=lineage, material=copy.deepcopy(material)
                        )
                    )

    selected: list[CandidateLearningAsset] = []
    seen: dict[str, str] = {}
    quotas: Counter[tuple[str, str]] = Counter()
    # Prefer actual provider family members over semantically duplicate, path-distinct
    # sources excluded by provider deduplication. Never invent alias membership.
    for asset in sorted(proposed, key=lambda a: (not bool(a.lineage.family_evidence), a.record_id)):
        sid, rule = asset.lineage.source.reference_id, asset.transform
        fingerprint = asset.material_digest
        filter_proof: dict[str, Any] = {
            "material_digest": fingerprint,
            "policy_id": policy.record_id,
        }
        if fingerprint in seen:
            reject(
                sid,
                rule,
                "DUPLICATE_MATERIAL",
                {**filter_proof, "representative_candidate_id": seen[fingerprint]},
                asset,
            )
            continue
        seen[fingerprint] = asset.record_id
        keys = [(family, rule.kind) for family in asset.lineage.family_ids]
        if policy.per_family_transform_quota is not None and any(
            quotas[key] >= policy.per_family_transform_quota for key in keys
        ):
            reject(
                sid,
                rule,
                "POLICY_FAMILY_QUOTA",
                {
                    **filter_proof,
                    "quota": policy.per_family_transform_quota,
                    "families": asset.lineage.family_ids,
                    "selected_candidate_ids": [a.record_id for a in selected],
                },
                asset,
            )
            continue
        if policy.require_saturation_evidence:
            reject(
                sid,
                rule,
                "SATURATION_UNKNOWN",
                {
                    **filter_proof,
                    "measurement_ids": [c.record_id for c in curves],
                    "reason": "model_execution_attestation_UNKNOWN",
                },
                asset,
            )
            continue
        selected.append(asset)
        quotas.update(keys)
    reason_counts = Counter(r.reason for r in rejected)
    return LearningAssetCompilation(
        policy=policy,
        sources=tuple(
            _ref("machine_experience", sid, value.source.experience)
            for sid, value in sorted(known.items())
        ),
        receipts=tuple(
            _ref("validated_counterfactual", rid, r) for rid, r in sorted(checked_receipts.items())
        ),
        source_occurrences=dict(sorted(source_occurrences.items())),
        receipt_occurrences=dict(sorted(receipt_occurrences.items())),
        frozen_panel_task_ids=tuple(sorted(set(frozen_panel_task_ids))),
        frozen_panel_source_digests=tuple(sorted(set(frozen_panel_source_digests))),
        diagnostics=tuple(v.diagnostics for _, v in sorted(known.items())),
        family_evidence=gaps,
        saturation_evidence=curves,
        assets=tuple(selected),
        rejections=tuple(sorted(rejected, key=lambda r: r.record_id)),
        counts={
            "input_sources": len(inputs),
            "distinct_sources": len(known),
            "duplicate_sources": duplicate_sources,
            "input_receipts": len(receipt_inputs),
            "distinct_receipts": len(pairs),
            "duplicate_receipts": duplicate_receipts,
            "proposed": len(proposed),
            "selected": len(selected),
            "rejected": len(rejected),
            "duplicate": reason_counts["DUPLICATE_MATERIAL"],
            "trivial": reason_counts["TRIVIAL_IDENTICAL_ACTION"],
            "semantic_alias": reason_counts["SEMANTIC_SOURCE_ALIAS"],
            "quota": reason_counts["POLICY_FAMILY_QUOTA"],
            "saturation_unknown": reason_counts["SATURATION_UNKNOWN"],
            "saturated": None,
        },
    )


def validate_compilation(
    result: LearningAssetCompilation,
    *,
    sources: Iterable[RecordedExperience],
    receipts: Iterable[CounterfactualReceipt] = (),
    policy: TransformPolicy | None = None,
    saturation_evidence: Iterable[AcquisitionCurve] = (),
    frozen_panel_task_ids: tuple[str, ...] = (),
    frozen_panel_source_digests: tuple[str, ...] = (),
) -> LearningAssetCompilation:
    """Content identity alone is not execution evidence: recompute against pinned inputs."""
    checked = result.checked()
    expected = compile_learning_assets(
        sources,
        receipts=receipts,
        policy=policy,
        saturation_evidence=saturation_evidence,
        frozen_panel_task_ids=frozen_panel_task_ids,
        frozen_panel_source_digests=frozen_panel_source_digests,
    )
    if checked != expected:
        raise ValueError("COMPILATION_MISMATCH")
    return expected
