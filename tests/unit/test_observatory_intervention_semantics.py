from investigation_world.companyworld.models import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    OperationalFactTarget,
)
from investigation_world.foundry.models import MutationKind
from investigation_world.observatory.companyworld import CompanyWorldBundleRepository
from investigation_world.observatory.interventions import (
    InterventionMutation,
    InterventionSpec,
    materialize_companyworld_intervention,
)
from investigation_world.observatory.models import ScenarioRef


def _repository() -> CompanyWorldBundleRepository:
    episode = CompanyWorldEpisode(
        episode_id="EP-1",
        world_id="WORLD-1",
        task=CompanyWorldTask(
            task_id="TASK-1",
            world_id="WORLD-1",
            task_type="STATUS",
            objective="Determine status.",
            target_object_type="ORDER",
            target_object_id="ORD-1",
            permitted_systems=[CompanySystem.ERP, CompanySystem.WMS],
            constraints={"budget": 10, "max_tool_calls": 5},
        ),
        records=[
            CompanyWorldRecord(
                record_id="REC-1",
                system=CompanySystem.ERP,
                record_type="order_status",
                object_type="ORDER",
                object_id="ORD-1",
                fields={"status": "OPEN"},
                source_file="erp.json",
            )
        ],
        oracle=CompanyWorldOracle(
            task_id="TASK-1",
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
        ),
    )
    return CompanyWorldBundleRepository([episode], taskset_version="test-v1")


def _scenario() -> ScenarioRef:
    return ScenarioRef(scenario_id="EP-1", task_id="TASK-1", seed=1)


def test_record_reordering_preserves_truth_and_evidence_solvability():
    spec = InterventionSpec(
        name="reorder",
        scenario=_scenario(),
        mutations=[InterventionMutation(kind=MutationKind.REORDER_RECORDS, seed=2)],
    )
    _, materialized = materialize_companyworld_intervention(_repository(), spec)

    assert spec.semantic_truth_preserved is True
    assert spec.evidence_solvability_preserved is True
    assert materialized.semantic_truth_preserved is True
    assert materialized.evidence_solvability_preserved is True
    assert materialized.protected_record_ids == ["REC-1"]


def test_tool_failure_preserves_semantic_truth_but_not_guaranteed_solvability():
    spec = InterventionSpec(
        name="erp-outage",
        scenario=_scenario(),
        mutations=[
            InterventionMutation(
                kind=MutationKind.TOOL_FAILURE,
                seed=2,
                parameters={"system": "ERP", "at_step": 0, "persistent": True},
            )
        ],
    )
    variant, materialized = materialize_companyworld_intervention(_repository(), spec)

    assert spec.truth_preserving is True
    assert spec.semantic_truth_preserved is True
    assert spec.evidence_solvability_preserved is False
    assert materialized.semantic_truth_preserved is True
    assert materialized.evidence_solvability_preserved is False
    assert variant.episode(_scenario()).oracle == _repository().episode(_scenario()).oracle


def test_aggregator_failure_materializes_without_fake_system():
    spec = InterventionSpec(
        name="aggregator-outage",
        scenario=_scenario(),
        mutations=[
            InterventionMutation(
                kind=MutationKind.TOOL_FAILURE,
                seed=2,
                parameters={"scope": "aggregator", "at_step": 0, "persistent": True},
            )
        ],
    )
    variant, _ = materialize_companyworld_intervention(_repository(), spec)
    failure = variant.episode(_scenario()).task.constraints["foundry_tool_failures"][0]

    assert failure == {
        "scope": "aggregator",
        "at_step": 0,
        "persistent": True,
    }
