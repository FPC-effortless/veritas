from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from investigation_world.companyworld.models import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    OperationalFactTarget,
)
from investigation_world.foundry.models import MutationKind
from investigation_world.observatory.aggregation import AggregateDriftReport
from investigation_world.observatory.cadence import (
    CadencePolicy,
    CadenceStore,
    CadencedObservationRunner,
    cadence_decision,
)
from investigation_world.observatory.capability_graph import (
    attribute_drift,
    companyworld_investigation_capability_graph,
)
from investigation_world.observatory.companyworld import CompanyWorldBundleRepository
from investigation_world.observatory.cycles import ObservationCycleReport
from investigation_world.observatory.interventions import (
    InterventionMutation,
    InterventionSpec,
    materialize_companyworld_intervention,
)
from investigation_world.observatory.models import DimensionDelta, ScenarioPool, ScenarioRef
from investigation_world.observatory.scheduler import SchedulerReport


def _episode() -> CompanyWorldEpisode:
    task = CompanyWorldTask(
        task_id="TASK-1",
        world_id="WORLD-1",
        task_type="STATUS_INVESTIGATION",
        objective="Determine order status.",
        target_object_type="ORDER",
        target_object_id="ORD-1",
        permitted_systems=[CompanySystem.ERP],
        constraints={"budget": 10, "max_tool_calls": 5},
    )
    support = CompanyWorldRecord(
        record_id="REC-1",
        system=CompanySystem.ERP,
        record_type="order_status",
        object_type="ORDER",
        object_id="ORD-1",
        fields={"status": "OPEN"},
        source_file="test/orders.json",
    )
    optional = CompanyWorldRecord(
        record_id="REC-2",
        system=CompanySystem.ERP,
        record_type="order_note",
        object_type="ORDER",
        object_id="ORD-1",
        fields={"note": "Routine note", "owner": "ops"},
        source_file="test/orders.json",
    )
    oracle = CompanyWorldOracle(
        task_id=task.task_id,
        answer_class="status",
        expected_resolution="OPEN",
        facts=[
            OperationalFactTarget(
                object_type="ORDER",
                object_id="ORD-1",
                field_name="status",
                expected_value="OPEN",
                supporting_record_ids=["REC-1"],
            )
        ],
    )
    return CompanyWorldEpisode(
        episode_id="EP-1",
        world_id="WORLD-1",
        task=task,
        records=[support, optional],
        oracle=oracle,
    )


def test_graph_attribution_identifies_upstream_regression():
    graph = companyworld_investigation_capability_graph()
    report = AggregateDriftReport(
        cohort_key="COHORT-1",
        baseline_aggregate_id="AGG-1",
        current_aggregate_id="AGG-2",
        baseline_snapshot="t1",
        current_snapshot="t2",
        reward=DimensionDelta(baseline=0.9, current=0.7, delta=-0.2),
        cost=DimensionDelta(baseline=1.0, current=1.0, delta=0.0),
        steps=DimensionDelta(baseline=3.0, current=3.0, delta=0.0),
        dimensions={
            "evidence_support": DimensionDelta(baseline=1.0, current=0.5, delta=-0.5),
            "fact_precision": DimensionDelta(baseline=1.0, current=0.7, delta=-0.3),
            "fact_recall": DimensionDelta(baseline=1.0, current=0.8, delta=-0.2),
            "fact_score": DimensionDelta(baseline=1.0, current=0.75, delta=-0.25),
        },
        regressions=["evidence_support", "fact_precision", "fact_recall", "fact_score"],
    )

    attributed = attribute_drift(graph, report)

    assert "evidence_selection" in attributed.candidate_roots
    assert attributed.attributions[0].diagnostic_score > 0
    assert "not causal proof" in attributed.caveat


def test_cadence_is_checkpointed_and_does_not_repeat_early(tmp_path):
    policy = CadencePolicy(name="weekly-anchor", interval_seconds=7 * 24 * 3600)
    store = CadenceStore(tmp_path)
    calls: list[str] = []

    def run_cycle(snapshot: str) -> ObservationCycleReport:
        calls.append(snapshot)
        now = datetime.now(timezone.utc)
        return ObservationCycleReport(
            cycle_id=f"CYCLE-{len(calls)}",
            experiment_id="EXP-1",
            started_at=now,
            finished_at=now,
            scheduler=SchedulerReport(
                experiment_id="EXP-1",
                planned=0,
                succeeded=0,
                failed=0,
                skipped=0,
            ),
        )

    runner = CadencedObservationRunner(policy, store, run_cycle)
    t0 = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    first = runner.run_if_due(now=t0)
    checkpoint = store.load(policy.cadence_id)
    early = cadence_decision(policy, checkpoint, now=t0 + timedelta(days=1))

    assert first.cycle is not None
    assert len(calls) == 1
    assert not early.due
    assert checkpoint.last_cycle_id == "CYCLE-1"
    assert checkpoint.consecutive_failures == 0


def test_truth_preserving_intervention_protects_oracle_support():
    episode = _episode()
    repository = CompanyWorldBundleRepository(
        [episode],
        taskset_version="test-v1",
        splits={"public_eval": [episode.episode_id]},
    )
    scenario = ScenarioRef(
        scenario_id="EP-1",
        task_id="TASK-1",
        seed=1,
        pool=ScenarioPool.ANCHOR,
    )
    spec = InterventionSpec(
        name="distractor-and-redaction",
        scenario=scenario,
        mutations=[
            InterventionMutation(kind=MutationKind.INJECT_DISTRACTOR, seed=10),
            InterventionMutation(kind=MutationKind.REDACT_OPTIONAL_FIELD, seed=11),
            InterventionMutation(kind=MutationKind.REORDER_RECORDS, seed=12),
        ],
    )

    variant, materialized = materialize_companyworld_intervention(repository, spec)
    mutated = variant.episode(scenario)
    support = next(item for item in mutated.records if item.record_id == "REC-1")

    assert "REC-1" in materialized.protected_record_ids
    assert support.fields["status"] == "OPEN"
    assert mutated.oracle == episode.oracle
    assert variant.bundle_version != repository.bundle_version
    assert any(item.record_type == "foundry_distractor" for item in mutated.records)


def test_truth_preserving_intervention_rejects_unimplemented_runtime_semantics():
    spec_args = dict(
        name="tool-failure",
        scenario=ScenarioRef(scenario_id="EP-1", task_id="TASK-1", seed=1),
        mutations=[
            InterventionMutation(
                kind=MutationKind.TOOL_FAILURE,
                seed=2,
                parameters={"system": "ERP", "at_step": 1},
            )
        ],
    )
    with pytest.raises(ValueError, match="do not yet support"):
        InterventionSpec(**spec_args)
