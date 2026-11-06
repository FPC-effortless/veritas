from __future__ import annotations

import pytest

from investigation_world.companyworld.models import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
)
from investigation_world.foundry.models import DifficultyVector, DistributionSplit, FoundryTaskMetadata
from investigation_world.foundry.tracing import TracingRuntimeProxy
from investigation_world.observatory.analysis import behavior_from_trace
from investigation_world.observatory.runtime_interventions import (
    InterventionAwareCompanyWorldRuntime,
)


def _episode(constraints: dict | None = None) -> CompanyWorldEpisode:
    task = CompanyWorldTask(
        task_id="TASK-1",
        world_id="WORLD-1",
        task_type="LOOKUP",
        objective="Inspect operational records.",
        target_object_type="ORDER",
        target_object_id="ORD-1",
        permitted_systems=[CompanySystem.ERP, CompanySystem.WMS],
        constraints={"budget": 20, "max_tool_calls": 10, **(constraints or {})},
    )
    return CompanyWorldEpisode(
        episode_id="EP-1",
        world_id="WORLD-1",
        task=task,
        records=[
            CompanyWorldRecord(
                record_id="ERP-1",
                system=CompanySystem.ERP,
                record_type="order",
                object_type="ORDER",
                object_id="ORD-1",
                fields={"status": "OPEN"},
                source_file="erp.json",
            ),
            CompanyWorldRecord(
                record_id="WMS-1",
                system=CompanySystem.WMS,
                record_type="shipment",
                object_type="ORDER",
                object_id="ORD-1",
                fields={"status": "PICKED"},
                source_file="wms.json",
            ),
        ],
        oracle=CompanyWorldOracle(
            task_id="TASK-1",
            answer_class="lookup",
            expected_resolution="inspect",
            facts=[],
        ),
    )


def _metadata() -> FoundryTaskMetadata:
    return FoundryTaskMetadata(
        task_id="TASK-1",
        split=DistributionSplit.IID_TEST,
        capability_tags=["recovery"],
        difficulty=DifficultyVector(),
        seed=1,
        taskset_version="taskset-v1",
        harness_version="1",
        runtime_version="companyworld-runtime-v2",
    )


def test_one_shot_tool_failure_is_traced_and_retry_counts_as_recovery():
    runtime = InterventionAwareCompanyWorldRuntime(
        _episode(
            {
                "foundry_tool_failures": [
                    {"system": "ERP", "at_step": 0, "persistent": False}
                ]
            }
        )
    )
    proxy = TracingRuntimeProxy(
        runtime,
        _metadata(),
        environment_version="WORLD-V2",
    )

    with pytest.raises(RuntimeError, match="tool failure"):
        proxy.search_system(CompanySystem.ERP, "ORD-1")
    records = proxy.search_system(CompanySystem.ERP, "ORD-1")
    trace = proxy.trace(termination_reason="test")
    behavior = behavior_from_trace(trace)

    assert records and records[0]["record_id"] == "ERP-1"
    assert [event.event_type for event in trace.events] == [
        "search_system_error",
        "search_system",
    ]
    assert trace.events[0].payload["success"] is False
    assert trace.events[1].payload["success"] is True
    assert behavior.failure_signals == 1
    assert behavior.recovery_events == 1
    assert runtime.budget.calls == 1


def test_persistent_tool_failure_remains_unavailable():
    runtime = InterventionAwareCompanyWorldRuntime(
        _episode(
            {
                "foundry_tool_failures": [
                    {"system": "ERP", "at_step": 0, "persistent": True}
                ]
            }
        )
    )

    with pytest.raises(RuntimeError):
        runtime.search_system(CompanySystem.ERP, "ORD-1")
    with pytest.raises(RuntimeError):
        runtime.search_system(CompanySystem.ERP, "ORD-1")
    assert runtime.budget.calls == 0


def test_system_specific_failure_does_not_disable_cross_system_search():
    runtime = InterventionAwareCompanyWorldRuntime(
        _episode(
            {
                "foundry_tool_failures": [
                    {"system": "ERP", "at_step": 0, "persistent": True}
                ]
            }
        )
    )

    visible = runtime.search_all("ORD-1")
    assert {item["record_id"] for item in visible} == {"ERP-1", "WMS-1"}
    with pytest.raises(RuntimeError, match="ERP unavailable"):
        runtime.search_system(CompanySystem.ERP, "ORD-1")
    wms = runtime.search_system(CompanySystem.WMS, "ORD-1")
    assert wms and wms[0]["record_id"] == "WMS-1"


def test_aggregator_failure_is_distinct_from_system_failure():
    runtime = InterventionAwareCompanyWorldRuntime(
        _episode(
            {
                "foundry_tool_failures": [
                    {
                        "scope": "aggregator",
                        "system": None,
                        "at_step": 0,
                        "persistent": True,
                    }
                ]
            }
        )
    )

    with pytest.raises(RuntimeError, match="aggregator unavailable"):
        runtime.search_all("ORD-1")
    erp = runtime.search_system(CompanySystem.ERP, "ORD-1")
    assert erp and erp[0]["record_id"] == "ERP-1"


def test_permission_revoke_blocks_target_system_and_search_all_cannot_bypass():
    runtime = InterventionAwareCompanyWorldRuntime(
        _episode(
            {
                "foundry_permission_change": {
                    "system": "ERP",
                    "at_step": 0,
                    "action": "revoke",
                }
            }
        )
    )

    visible = runtime.search_all("ORD-1")
    assert {item["record_id"] for item in visible} == {"WMS-1"}
    with pytest.raises(PermissionError, match="revoked"):
        runtime.open_record("ERP-1")


def test_permission_can_be_restored_by_later_scheduled_change():
    runtime = InterventionAwareCompanyWorldRuntime(
        _episode(
            {
                "foundry_permission_change": [
                    {"system": "ERP", "at_step": 0, "action": "revoke"},
                    {"system": "ERP", "at_step": 2, "action": "restore"},
                ]
            }
        )
    )

    with pytest.raises(PermissionError):
        runtime.search_system(CompanySystem.ERP, "ORD-1")
    runtime.search_system(CompanySystem.WMS, "ORD-1")
    records = runtime.search_system(CompanySystem.ERP, "ORD-1")
    assert records and records[0]["record_id"] == "ERP-1"
