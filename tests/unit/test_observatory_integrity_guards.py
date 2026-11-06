from __future__ import annotations

from datetime import datetime
from pathlib import Path

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
from investigation_world.observatory.cadence import CadencePolicy
from investigation_world.observatory.companyworld import CompanyWorldBundleRepository
from investigation_world.observatory.interventions import InterventionMutation, InterventionSpec
from investigation_world.observatory.live import (
    CompanyWorldLiveRunConfig,
    _cadence_experiment_identity,
    run_companyworld_intervention,
)
from investigation_world.observatory.models import ScenarioRef


def _repository(status: str = "OPEN") -> CompanyWorldBundleRepository:
    task = CompanyWorldTask(
        task_id="TASK-1",
        world_id="WORLD-1",
        task_type="STATUS_INVESTIGATION",
        objective="Determine status.",
        target_object_type="ORDER",
        target_object_id="ORD-1",
        permitted_systems=[CompanySystem.ERP],
        constraints={"budget": 10, "max_tool_calls": 5},
    )
    record = CompanyWorldRecord(
        record_id="REC-1",
        system=CompanySystem.ERP,
        record_type="order_status",
        object_type="ORDER",
        object_id="ORD-1",
        fields={"status": status},
        source_file="test/orders.json",
    )
    episode = CompanyWorldEpisode(
        episode_id="EP-1",
        world_id="WORLD-1",
        task=task,
        records=[record],
        oracle=CompanyWorldOracle(
            task_id="TASK-1",
            answer_class="status",
            expected_resolution=status,
            facts=[
                OperationalFactTarget(
                    object_type="ORDER",
                    object_id="ORD-1",
                    field_name="status",
                    expected_value=status,
                    supporting_record_ids=["REC-1"],
                )
            ],
        ),
    )
    return CompanyWorldBundleRepository([episode], taskset_version="test-v1")


def _config(**updates) -> CompanyWorldLiveRunConfig:
    payload = dict(
        public_bundle=Path("public.json"),
        oracle_bundle=Path("oracle.json"),
        provider="local",
        provider_id="local",
        model_id="agent-a",
        model_snapshot="snapshot-1",
        local_command=["agent"],
        token_budget=1000,
        tool_call_budget=10,
        provider_cost_budget=1.0,
        scenario_limit=1,
    )
    payload.update(updates)
    return CompanyWorldLiveRunConfig(**payload)


def test_cadence_start_requires_timezone():
    with pytest.raises(ValueError, match="timezone-aware"):
        CadencePolicy(
            name="weekly",
            interval_seconds=7 * 24 * 3600,
            start_at=datetime(2026, 8, 26, 12, 0, 0),
        )


def test_cadence_identity_ignores_time_and_model_snapshot_only():
    repository = _repository()
    baseline = _config(time_snapshot="2026-08-20T00:00:00+00:00", model_snapshot="v1")
    later = baseline.model_copy(
        update={"time_snapshot": "2026-08-27T00:00:00+00:00", "model_snapshot": "v2"}
    )

    assert _cadence_experiment_identity(baseline, repository) == _cadence_experiment_identity(
        later, repository
    )


def test_cadence_identity_changes_with_frozen_experiment_configuration():
    repository = _repository()
    baseline = _config()
    tighter = baseline.model_copy(update={"token_budget": 500})
    other_model = baseline.model_copy(update={"model_id": "agent-b"})

    base_id = _cadence_experiment_identity(baseline, repository)
    assert _cadence_experiment_identity(tighter, repository) != base_id
    assert _cadence_experiment_identity(other_model, repository) != base_id


def test_cadence_identity_changes_with_world_contents():
    config = _config()
    assert _cadence_experiment_identity(config, _repository("OPEN")) != _cadence_experiment_identity(
        config, _repository("CLOSED")
    )


def test_explicit_world_budget_cannot_mask_tighten_budget_intervention():
    config = _config(world_cost_budget=40)
    spec = InterventionSpec(
        name="tight-budget",
        scenario=ScenarioRef(scenario_id="EP-1", task_id="TASK-1", seed=1),
        mutations=[
            InterventionMutation(
                kind=MutationKind.TIGHTEN_BUDGET,
                seed=2,
                parameters={"factor": 0.5},
            )
        ],
    )

    with pytest.raises(ValueError, match="would mask"):
        run_companyworld_intervention(config, spec)
