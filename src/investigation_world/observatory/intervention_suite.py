from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.models import stable_hash
from investigation_world.observatory.intervention_stats import (
    AggregatedInterventionEffect,
    InterventionEffectSample,
    ModelInterventionInteractionReport,
    aggregate_intervention_effects,
    compare_model_intervention_effects,
    intervention_family_key,
)
from investigation_world.observatory.interventions import InterventionSpec
from investigation_world.observatory.live import (
    CompanyWorldInterventionRunReport,
    CompanyWorldLiveRunConfig,
    run_companyworld_intervention,
)
from investigation_world.observatory.models import ModelSpec
from investigation_world.observatory.store import ObservatoryStore


class CompanyWorldInterventionSuiteReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    suite_id: str
    family_key: str
    model: ModelSpec
    intervention_report_ids: list[str] = Field(min_length=1)
    aggregate: AggregatedInterventionEffect
    created_at: datetime


class CompanyWorldModelInteractionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    report_id: str
    first_suite_id: str
    second_suite_id: str
    interaction: ModelInterventionInteractionReport
    created_at: datetime


def _persist(root: Path, filename: str, payload: BaseModel) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / filename).write_text(
        json.dumps(payload.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )


def run_companyworld_intervention_suite(
    config: CompanyWorldLiveRunConfig,
    specs: Iterable[InterventionSpec],
    *,
    persist_report: bool = True,
) -> CompanyWorldInterventionSuiteReport:
    """Execute one intervention family across multiple scenario seeds and aggregate paired effects."""
    items = list(specs)
    if not items:
        raise ValueError("intervention suite requires at least one InterventionSpec")
    family = intervention_family_key(items[0])
    if any(intervention_family_key(spec) != family for spec in items[1:]):
        raise ValueError("all suite interventions must belong to one intervention family")
    scenario_pairs = [(spec.scenario.scenario_id, spec.scenario.seed) for spec in items]
    if len(set(scenario_pairs)) != len(scenario_pairs):
        raise ValueError("intervention suite requires unique scenario/seed pairs")

    reports: list[CompanyWorldInterventionRunReport] = [
        run_companyworld_intervention(config, spec, persist_report=persist_report)
        for spec in items
    ]
    store = ObservatoryStore(config.store_root)
    runs = {run.run_id: run for run in store.load()}
    samples: list[InterventionEffectSample] = []
    for report in reports:
        baseline = runs.get(report.effect.baseline_run_id)
        if baseline is None:
            raise RuntimeError(
                f"missing baseline run {report.effect.baseline_run_id!r} for intervention suite"
            )
        samples.append(
            InterventionEffectSample(
                model=baseline.cell.model,
                intervention=report.intervention,
                effect=report.effect,
            )
        )
    aggregate = aggregate_intervention_effects(samples)
    model = samples[0].model
    created_at = datetime.now(timezone.utc)
    report_ids = sorted(report.report_id for report in reports)
    suite_id = f"ISUITE-{stable_hash([family, model.model_dump(mode='json'), report_ids])[:20].upper()}"
    suite = CompanyWorldInterventionSuiteReport(
        suite_id=suite_id,
        family_key=family,
        model=model,
        intervention_report_ids=report_ids,
        aggregate=aggregate,
        created_at=created_at,
    )
    if persist_report:
        _persist(
            config.store_root / "intervention_suites",
            f"{suite_id}.json",
            suite,
        )
    return suite


def compare_companyworld_intervention_suites(
    first: CompanyWorldInterventionSuiteReport,
    second: CompanyWorldInterventionSuiteReport,
    *,
    store_root: str | Path | None = None,
) -> CompanyWorldModelInteractionReport:
    """Compare how two model configurations respond to the same intervention family."""
    interaction = compare_model_intervention_effects(first.aggregate, second.aggregate)
    created_at = datetime.now(timezone.utc)
    report_id = f"IMODELINT-{stable_hash([first.suite_id, second.suite_id])[:20].upper()}"
    report = CompanyWorldModelInteractionReport(
        report_id=report_id,
        first_suite_id=first.suite_id,
        second_suite_id=second.suite_id,
        interaction=interaction,
        created_at=created_at,
    )
    if store_root is not None:
        _persist(Path(store_root) / "intervention_interactions", f"{report_id}.json", report)
    return report
