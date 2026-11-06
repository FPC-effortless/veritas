from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.operational_world.models import (
    CalibrationProfile,
    CompiledOperationalWorld,
    QuantileDistribution,
)


class MetricDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    generated_observations: int = 0
    calibrated_observations: int = 0
    calibrated: dict[str, float] = Field(default_factory=dict)
    generated: dict[str, float] = Field(default_factory=dict)
    normalized_errors: dict[str, float] = Field(default_factory=dict)
    max_normalized_error: float = 0.0
    passed: bool = False
    reason: str = ""


class DistributionDiagnosticReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worlds: int
    metrics: dict[str, MetricDiagnostic] = Field(default_factory=dict)
    required_metrics: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors and all(
            self.metrics[metric].passed
            for metric in self.required_metrics
            if metric in self.metrics
        )


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(value for value in values if isfinite(value))
    if not ordered:
        raise ValueError("cannot calculate quantile from no finite observations")
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _summarize(values: list[float]) -> dict[str, float]:
    return {
        "p10": _quantile(values, 0.10),
        "p50": _quantile(values, 0.50),
        "p90": _quantile(values, 0.90),
    }


def _target_summary(distribution: QuantileDistribution) -> dict[str, float]:
    return {
        "p10": distribution.p10,
        "p50": distribution.p50,
        "p90": distribution.p90,
    }


def _scale(distribution: QuantileDistribution) -> float:
    # Prefer robust IQR-like spread. Fall back to magnitude for degenerate empirical metrics.
    spread = abs(distribution.p90 - distribution.p10)
    magnitude = max(abs(distribution.p50), abs(distribution.p90), 1.0)
    return max(spread, magnitude * 0.1, 1e-9)


def extract_world_metric_observations(world: CompiledOperationalWorld) -> dict[str, list[float]]:
    """Extract generated statistics that correspond directly to calibration metric semantics."""

    metrics: dict[str, list[float]] = defaultdict(list)
    organization = world.entities.get("ORG-000001")
    if organization is not None:
        headcount = organization.attributes.get("employee_count")
        if headcount is not None:
            metrics["firm.employee_count"].append(float(headcount))

    purchase_orders = [record for record in world.records if record.record_type == "purchase_order"]
    if purchase_orders:
        for record in purchase_orders:
            amount = record.fields.get("amount")
            fx = float(world.spec.metadata.get("usd_to_local", 1.0))
            if amount is not None and fx > 0:
                metrics["procurement.po_amount_usd"].append(float(amount) / fx)
            if record.fields.get("line_item_count") is not None:
                metrics["procurement.items_per_tender"].append(
                    float(record.fields["line_item_count"])
                )
            if record.fields.get("sourcing_party_count") is not None:
                metrics["procurement.parties_per_process"].append(
                    float(record.fields["sourcing_party_count"])
                )

        employee_count = max(1, len([
            entity for entity in world.entities.values() if entity.entity_type == "employee"
        ]))
        annualized_po_rate = (
            len(purchase_orders) * 365.0 / max(1, world.spec.simulation_days) / employee_count
        )
        metrics["procurement.purchase_orders_per_employee_year"].append(annualized_po_rate)

    vendors = [entity for entity in world.entities.values() if entity.entity_type == "vendor"]
    employees = [entity for entity in world.entities.values() if entity.entity_type == "employee"]
    if employees:
        metrics["procurement.vendors_per_100_employees"].append(
            len(vendors) * 100.0 / len(employees)
        )

    for record in world.records:
        if record.record_type == "financial_snapshot":
            fields = record.fields
            if fields.get("assets_usd") is not None:
                metrics["finance.assets_usd"].append(float(fields["assets_usd"]))
            assets = float(fields.get("assets_usd") or 0.0)
            if assets > 0:
                if fields.get("liabilities_usd") is not None:
                    metrics["finance.liabilities_to_assets"].append(
                        float(fields["liabilities_usd"]) / assets
                    )
                if fields.get("accounts_payable_usd") is not None:
                    metrics["finance.accounts_payable_to_assets"].append(
                        float(fields["accounts_payable_usd"]) / assets
                    )
                if fields.get("annual_revenue_usd") is not None:
                    metrics["finance.revenue_to_assets"].append(
                        float(fields["annual_revenue_usd"]) / assets
                    )
                    metrics["finance.annual_revenue_usd"].append(
                        float(fields["annual_revenue_usd"])
                    )

    return dict(metrics)


def diagnose_generated_distribution(
    worlds: Iterable[CompiledOperationalWorld],
    calibration: CalibrationProfile,
    *,
    metrics: Iterable[str] | None = None,
    max_normalized_error: float = 0.75,
    minimum_generated_observations: int = 25,
    empirical_only: bool = True,
) -> DistributionDiagnosticReport:
    """Compare generated quantiles to the empirical/hybrid calibration target.

    Error is normalized by each target distribution's robust spread. This intentionally avoids
    fragile percentage errors around zero-valued metrics. The report refuses to treat bootstrap
    priors as empirical validation when `empirical_only=True`.
    """

    world_list = list(worlds)
    aggregated: dict[str, list[float]] = defaultdict(list)
    for world in world_list:
        for metric, values in extract_world_metric_observations(world).items():
            aggregated[metric].extend(values)

    if metrics is None:
        requested = [
            metric
            for metric, distribution in calibration.distributions.items()
            if not empirical_only or distribution.observation_count > 0
        ]
    else:
        requested = list(dict.fromkeys(metrics))

    report = DistributionDiagnosticReport(
        worlds=len(world_list),
        required_metrics=requested,
    )
    for metric in requested:
        target = calibration.distributions.get(metric)
        if target is None:
            report.errors.append(f"missing calibration metric: {metric}")
            continue
        if empirical_only and target.observation_count == 0:
            report.warnings.append(f"skipped non-empirical calibration metric: {metric}")
            report.required_metrics.remove(metric)
            continue

        values = aggregated.get(metric, [])
        diagnostic = MetricDiagnostic(
            metric=metric,
            generated_observations=len(values),
            calibrated_observations=target.observation_count,
            calibrated=_target_summary(target),
        )
        if len(values) < minimum_generated_observations:
            diagnostic.reason = (
                f"requires at least {minimum_generated_observations} generated observations"
            )
            report.metrics[metric] = diagnostic
            report.errors.append(
                f"{metric}: {len(values)} generated observations is insufficient"
            )
            continue

        generated = _summarize(values)
        scale = _scale(target)
        errors = {
            quantile: abs(generated[quantile] - target_value) / scale
            for quantile, target_value in diagnostic.calibrated.items()
        }
        diagnostic.generated = generated
        diagnostic.normalized_errors = errors
        diagnostic.max_normalized_error = max(errors.values())
        diagnostic.passed = diagnostic.max_normalized_error <= max_normalized_error
        diagnostic.reason = (
            "within tolerance"
            if diagnostic.passed
            else f"normalized quantile error exceeds {max_normalized_error:.3f}"
        )
        report.metrics[metric] = diagnostic
        if not diagnostic.passed:
            report.errors.append(
                f"{metric}: max normalized error {diagnostic.max_normalized_error:.3f}"
            )

    return report
