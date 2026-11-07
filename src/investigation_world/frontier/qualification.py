from __future__ import annotations

from typing import Any

from .calibration import calibration_gates
from .models import (
    FrontierCalibrationObservation,
    FrontierQualificationPolicy,
    FrontierQualificationReport,
    FrontierStatus,
    FrontierUtilityGateResult,
    GateStatus,
    GeneralizationEvidenceSummary,
    PairedCapabilityComparison,
    TaskDiversityReport,
    TrainingValueEvidenceSummary,
)

_GENERALIZATION_KEYS = (
    "random_held_out",
    "source_disjoint",
    "grammar_disjoint",
    "component_disjoint",
    "compositional_ood_transfer",
)
_TRAINING_KEYS = (
    "within_family_transfer",
    "cross_family_transfer",
    "external_benchmark_transfer",
    "control_benchmark_preservation",
)


def _status(value: Any) -> GateStatus:
    if isinstance(value, GateStatus):
        return value
    if value is True:
        return GateStatus.PASS
    if value is False:
        return GateStatus.FAIL
    if isinstance(value, str):
        normalized = value.upper()
        if normalized in GateStatus.__members__:
            return GateStatus[normalized]
    return GateStatus.UNKNOWN


def summarize_generalization(data: dict[str, Any] | None) -> GeneralizationEvidenceSummary:
    data = data or {}
    source = data.get("generalization", data)
    values = {key: _status(source.get(key)) for key in _GENERALIZATION_KEYS}
    evidence_ids = (
        source.get("evidence_ids", {})
        if isinstance(source.get("evidence_ids", {}), dict)
        else {}
    )
    notes = source.get("notes", {}) if isinstance(source.get("notes", {}), dict) else {}
    return GeneralizationEvidenceSummary(**values, evidence_ids=evidence_ids, notes=notes)


def summarize_training_value(data: dict[str, Any] | None) -> TrainingValueEvidenceSummary:
    if not data:
        return TrainingValueEvidenceSummary()

    # Explicit frontier schema takes precedence and is never widened implicitly.
    if any(key in data for key in _TRAINING_KEYS):
        values = {key: _status(data.get(key)) for key in _TRAINING_KEYS}
        return TrainingValueEvidenceSummary(
            **values,
            model_identity=data.get("model_identity") or data.get("model"),
            model_tier=data.get("model_tier"),
            evidence_ids=data.get("evidence_ids", {}),
            notes=data.get("notes", {}),
        )

    # Existing Veritas Training Value v3 aggregate is a replicated within-family held-out result.
    if data.get("experiment") == "diagnostic_lora_sft_hardened_replicated_transfer":
        estimate = data.get("seed_level_mean_delta", {})
        low = estimate.get("ci95_low")
        high = estimate.get("ci95_high")
        if isinstance(low, (int, float)) and low > 0:
            within = GateStatus.PASS
        elif isinstance(high, (int, float)) and high <= 0:
            within = GateStatus.FAIL
        else:
            within = GateStatus.UNKNOWN
        return TrainingValueEvidenceSummary(
            within_family_transfer=within,
            cross_family_transfer=GateStatus.UNKNOWN,
            external_benchmark_transfer=GateStatus.UNKNOWN,
            control_benchmark_preservation=GateStatus.UNKNOWN,
            model_identity=data.get("model"),
            model_tier=data.get("model_tier"),
            notes={
                "within_family_transfer": (
                    "Replicated held-out transfer within the Training Value v3 task family."
                ),
                "cross_family_transfer": "Not measured by the v3 aggregate schema.",
                "external_benchmark_transfer": (
                    "Not measured; within-family evidence is not promoted to external transfer."
                ),
                "control_benchmark_preservation": "Not measured by the v3 aggregate schema.",
            },
        )
    return TrainingValueEvidenceSummary(
        model_identity=data.get("model_identity") or data.get("model"),
        model_tier=data.get("model_tier"),
        notes={
            "unrecognized_schema": (
                "Training-value schema was not recognized; no PASS was inferred."
            )
        },
    )


def scientific_qualification_summary(data: dict[str, Any] | None) -> tuple[bool, bool | None, str]:
    if not data:
        return False, None, "No scientific qualification artifact was supplied."
    if "scientifically_qualified" in data:
        value = data.get("scientifically_qualified")
        return (
            True,
            bool(value) if isinstance(value, bool) else None,
            "Consumed explicit scientific qualification state.",
        )
    if "releaseable" in data:
        return (
            True,
            bool(data["releaseable"]),
            "Consumed QualificationReport.releaseable without modification.",
        )
    if data.get("status") in {"benchmark_candidate", "qualified", "scientifically_qualified"}:
        # A status label alone is not scientific evidence. Only consume a frozen release
        # status as PASS when the artifact explicitly carries its failed-gate result.
        if "failed_gates" in data and data.get("failed_gates") == []:
            return (
                True,
                True,
                "Consumed frozen public release status with explicit zero failed gates; "
                "Frontier Qualification did not alter it.",
            )
    if data.get("status") in {"not_qualified", "failed"}:
        return True, False, "Consumed scientific qualification failure without modification."
    return (
        True,
        None,
        "Scientific artifact was supplied but its qualification state was not recognizable "
        "or required explicit gate evidence was missing.",
    )


def task_diversity_gate(
    diversity: TaskDiversityReport | None, policy: FrontierQualificationPolicy
) -> FrontierUtilityGateResult:
    required = {
        "minimum_effective_diversity": policy.minimum_effective_diversity,
        "maximum_largest_cluster_share": policy.maximum_largest_cluster_share,
        "maximum_near_duplicate_share": policy.maximum_near_duplicate_share,
        "minimum_source_normalized_entropy": policy.minimum_source_normalized_entropy,
        "maximum_dimension_concentration": policy.maximum_dimension_concentration,
        "minimum_required_diversity_dimensions": policy.minimum_required_diversity_dimensions,
    }
    if diversity is None:
        return FrontierUtilityGateResult(
            name="task_diversity",
            status=GateStatus.UNKNOWN,
            observed=None,
            required=required,
            detail="No task-diversity report was supplied.",
        )
    source = diversity.dimensions.get("source_family")
    if source is None or not source.available:
        return FrontierUtilityGateResult(
            name="task_diversity",
            status=GateStatus.UNKNOWN,
            observed={"report_id": diversity.report_id, "raw_task_count": diversity.raw_task_count},
            required=required,
            detail=(
                "Source-family metadata is absent, so the configured diversity policy "
                "cannot be evaluated."
            ),
            evidence_ids=[diversity.report_id],
        )
    core_dimension_names = (
        "source_family", "workflow_topology", "tool_action_sequence", "causal_failure_mode",
        "verifier_condition", "artifact_schema", "component_signature", "grammar_family",
    )
    available_dimension_concentration = {
        name: diversity.dimensions[name].largest_category_share
        for name in core_dimension_names
        if name in diversity.dimensions and diversity.dimensions[name].available
    }
    missing_dimensions = [
        name for name in core_dimension_names if name not in available_dimension_concentration
    ]
    if len(available_dimension_concentration) < policy.minimum_required_diversity_dimensions:
        return FrontierUtilityGateResult(
            name="task_diversity",
            status=GateStatus.UNKNOWN,
            observed={
                "report_id": diversity.report_id,
                "raw_task_count": diversity.raw_task_count,
                "available_diversity_dimensions": sorted(available_dimension_concentration),
                "available_diversity_dimension_count": len(available_dimension_concentration),
                "missing_dimensions": missing_dimensions,
                "missing_diversity_dimensions": missing_dimensions,
            },
            required=required,
            detail=(
                "Too few structural diversity dimensions are available to support a PASS; "
                "missing dimensions remain UNKNOWN rather than being silently ignored."
            ),
            evidence_ids=[diversity.report_id],
        )
    maximum_observed_dimension_concentration = max(
        available_dimension_concentration.values(), default=0.0
    )
    checks = {
        "effective_diversity": diversity.effective_diversity >= policy.minimum_effective_diversity,
        "largest_cluster_share": (
            diversity.largest_cluster_share <= policy.maximum_largest_cluster_share
        ),
        "near_duplicate_share": (
            diversity.near_duplicate_share <= policy.maximum_near_duplicate_share
        ),
        "source_normalized_entropy": (
            source.normalized_entropy >= policy.minimum_source_normalized_entropy
        ),
        "dimension_concentration": (
            maximum_observed_dimension_concentration <= policy.maximum_dimension_concentration
        ),
    }
    status = GateStatus.PASS if all(checks.values()) else GateStatus.FAIL
    return FrontierUtilityGateResult(
        name="task_diversity",
        status=status,
        observed={
            "report_id": diversity.report_id,
            "raw_task_count": diversity.raw_task_count,
            "effective_diversity": diversity.effective_diversity,
            "cluster_count": diversity.cluster_count,
            "largest_cluster_share": diversity.largest_cluster_share,
            "near_duplicate_share": diversity.near_duplicate_share,
            "source_concentration": diversity.source_concentration,
            "source_normalized_entropy": source.normalized_entropy,
            "dimension_concentration": available_dimension_concentration,
            "maximum_dimension_concentration": maximum_observed_dimension_concentration,
            "checks": checks,
        },
        required=required,
        detail=(
            "Structural/categorical diversity meets the configured thresholds."
            if status is GateStatus.PASS
            else (
                "Raw task count overstates useful diversity under one or more "
                "concentration thresholds."
            )
        ),
        evidence_ids=[diversity.report_id],
    )


def generalization_gate(
    summary: GeneralizationEvidenceSummary, policy: FrontierQualificationPolicy
) -> FrontierUtilityGateResult:
    observed = {key: getattr(summary, key).value for key in _GENERALIZATION_KEYS}
    required = {"required_evidence": list(policy.required_generalization_evidence)}
    values = [getattr(summary, key) for key in policy.required_generalization_evidence]
    if any(value is GateStatus.FAIL for value in values):
        status = GateStatus.FAIL
        detail = "At least one policy-required generalization mode failed."
    elif any(value is GateStatus.UNKNOWN for value in values):
        status = GateStatus.UNKNOWN
        detail = "One or more policy-required generalization modes have not been measured."
    else:
        status = GateStatus.PASS
        detail = "All policy-required held-out/generalization modes passed."
    return FrontierUtilityGateResult(
        name="held_out_compositional_generalization",
        status=status,
        observed=observed,
        required=required,
        detail=detail,
        evidence_ids=sorted({eid for ids in summary.evidence_ids.values() for eid in ids}),
    )


def training_value_gate(
    summary: TrainingValueEvidenceSummary, policy: FrontierQualificationPolicy
) -> FrontierUtilityGateResult:
    required = {
        "required_transfer_kinds": list(policy.required_training_transfer_kinds),
        "require_training_on_strong_tier": policy.require_training_on_strong_tier,
        "strong_model_tiers": list(policy.strong_model_tiers),
    }
    observed = {key: getattr(summary, key).value for key in _TRAINING_KEYS}
    observed.update({"model_identity": summary.model_identity, "model_tier": summary.model_tier})
    values = [getattr(summary, key) for key in policy.required_training_transfer_kinds]
    if any(value is GateStatus.FAIL for value in values):
        status = GateStatus.FAIL
        detail = "At least one policy-required training-transfer claim failed."
    elif any(value is GateStatus.UNKNOWN for value in values):
        status = GateStatus.UNKNOWN
        detail = "Required training-transfer evidence is missing or inconclusive."
    elif (
        policy.require_training_on_strong_tier
        and summary.model_tier not in set(policy.strong_model_tiers)
    ):
        status = GateStatus.UNKNOWN
        detail = (
            "Training value exists, but it is not tied to a policy-declared "
            "strong/frontier model tier."
        )
    else:
        status = GateStatus.PASS
        detail = "Required training-value evidence is positive within its declared claim boundary."
    return FrontierUtilityGateResult(
        name="training_value",
        status=status,
        observed=observed,
        required=required,
        detail=detail,
        evidence_ids=sorted({eid for ids in summary.evidence_ids.values() for eid in ids}),
    )


def control_guardrail_gate(
    summary: TrainingValueEvidenceSummary, policy: FrontierQualificationPolicy
) -> FrontierUtilityGateResult:
    required = {"control_benchmark_required": policy.require_control_benchmark}
    if not policy.require_control_benchmark:
        return FrontierUtilityGateResult(
            name="control_regression_guardrail",
            status=GateStatus.PASS,
            observed={
                "control_benchmark_preservation": summary.control_benchmark_preservation.value
            },
            required=required,
            detail="The active policy does not require a control benchmark.",
        )
    status = summary.control_benchmark_preservation
    detail = {
        GateStatus.PASS: "Unrelated/control capability preservation was measured and passed.",
        GateStatus.FAIL: "A control benchmark detected post-training regression.",
        GateStatus.UNKNOWN: "No qualifying control benchmark evidence was measured.",
    }[status]
    return FrontierUtilityGateResult(
        name="control_regression_guardrail",
        status=status,
        observed={"control_benchmark_preservation": status.value},
        required=required,
        detail=detail,
        evidence_ids=summary.evidence_ids.get("control_benchmark_preservation", []),
    )


def build_frontier_qualification_report(
    *,
    scientific_qualification: dict[str, Any] | None,
    diversity: TaskDiversityReport | None = None,
    observations: list[FrontierCalibrationObservation] | None = None,
    paired_comparisons: list[PairedCapabilityComparison] | None = None,
    generalization: dict[str, Any] | GeneralizationEvidenceSummary | None = None,
    training_value: dict[str, Any] | TrainingValueEvidenceSummary | None = None,
    policy: FrontierQualificationPolicy | None = None,
    input_artifact_hashes: dict[str, str] | None = None,
) -> FrontierQualificationReport:
    policy = policy or FrontierQualificationPolicy()
    observations = observations or []
    paired_comparisons = paired_comparisons or []
    generalization_summary = (
        generalization
        if isinstance(generalization, GeneralizationEvidenceSummary)
        else summarize_generalization(generalization)
    )
    training_summary = (
        training_value
        if isinstance(training_value, TrainingValueEvidenceSummary)
        else summarize_training_value(training_value)
    )
    observed_science, science_passed, science_detail = scientific_qualification_summary(
        scientific_qualification
    )

    calibration = calibration_gates(observations, policy, paired_comparisons)
    gates = [
        *calibration,
        task_diversity_gate(diversity, policy),
        generalization_gate(generalization_summary, policy),
        training_value_gate(training_summary, policy),
        control_guardrail_gate(training_summary, policy),
    ]
    frontier_qualified = science_passed is True and all(g.status is GateStatus.PASS for g in gates)
    status = (
        FrontierStatus.FRONTIER_QUALIFIED
        if frontier_qualified
        else FrontierStatus.NOT_YET_FRONTIER_QUALIFIED
    )

    source = scientific_qualification or {}
    return FrontierQualificationReport(
        benchmark_name=source.get("benchmark_name") or source.get("domain") or source.get("name"),
        benchmark_version=(
            source.get("benchmark_version")
            or source.get("version")
            or source.get("candidate_version")
        ),
        candidate_id=source.get("candidate_id") or (diversity.candidate_id if diversity else None),
        panel_id=source.get("panel_id") or (diversity.panel_id if diversity else None),
        qualification_report_id=source.get("qualification_report_id") or source.get("report_id"),
        evidence_manifest_id=source.get("evidence_manifest_id"),
        release_manifest_id=(
            source.get("release_manifest_id")
            or source.get("private_release_manifest_id")
        ),
        input_artifact_hashes=input_artifact_hashes or {},
        scientific_qualification_observed=observed_science,
        scientifically_qualified=science_passed,
        scientific_qualification_detail=science_detail,
        policy=policy,
        gates=gates,
        generalization=generalization_summary,
        training_value=training_summary,
        frontier_status=status,
        frontier_qualified=frontier_qualified,
        buyer_safe=True,
    )
