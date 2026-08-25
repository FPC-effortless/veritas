from investigation_world.companyworld import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldRuntime,
    CompanyWorldTask,
    OperationalFactTarget,
)
from investigation_world.core.models import InvestigationResult


def _episode() -> CompanyWorldEpisode:
    record = CompanyWorldRecord(
        record_id="REC-1",
        system=CompanySystem.WMS,
        record_type="carrier_manifest",
        object_type="SHIPMENT",
        object_id="SHP-1",
        fields={"delivered_quantity": 9},
        source_file="derived/carrier_manifest",
    )
    task = CompanyWorldTask(
        task_id="TASK-1",
        world_id="companyworld:test:1",
        task_type="INVESTIGATE_MISSING_SHIPMENT",
        objective="Investigate shipment SHP-1.",
        target_object_type="SHIPMENT",
        target_object_id="SHP-1",
        permitted_systems=[CompanySystem.WMS],
    )
    oracle = CompanyWorldOracle(
        task_id="TASK-1",
        answer_class="shipment_short_pick",
        expected_resolution="Reconcile shipment evidence.",
        facts=[
            OperationalFactTarget(
                object_type="SHIPMENT",
                object_id="SHP-1",
                field_name="delivered_quantity",
                expected_value=9,
                supporting_record_ids=["REC-1"],
            )
        ],
    )
    return CompanyWorldEpisode(
        episode_id="CW-TASK-1",
        world_id="companyworld:test:1",
        task=task,
        records=[record],
        oracle=oracle,
    )


def test_runtime_keeps_system_surfaces_separate_and_charges_budget():
    runtime = CompanyWorldRuntime(_episode(), total_cost=10, max_tool_calls=5)
    assert runtime.search_system(CompanySystem.ERP, "SHP-1") == []
    assert runtime.budget_snapshot()["spent"] == 0

    records = runtime.search_system(CompanySystem.WMS, "SHP-1")
    assert [record["record_id"] for record in records] == ["REC-1"]
    assert runtime.budget_snapshot()["spent"] == 2
    assert runtime.budget_snapshot()["calls"] == 1


def test_runtime_submit_closes_episode_and_uses_operational_verifier():
    runtime = CompanyWorldRuntime(_episode())
    result = InvestigationResult(
        claims=[{
            "object_type": "SHIPMENT",
            "object_id": "SHP-1",
            "field_name": "delivered_quantity",
            "value": 9,
        }],
        evidence=[{"record_id": "REC-1"}],
        overall_confidence=1.0,
    )
    verification = runtime.submit(result)
    assert verification.fact_score == 1.0
    assert verification.evidence_support == 1.0
    assert runtime.closed

    try:
        runtime.search_system(CompanySystem.WMS, "shipment")
    except ValueError as error:
        assert "already submitted" in str(error)
    else:
        raise AssertionError("closed episode allowed another tool call")
