from __future__ import annotations

from investigation_world.companyworld.models import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
)
from investigation_world.companyworld.runtime import CompanyWorldRuntime
from investigation_world.foundry.models import MutationKind
from investigation_world.observatory.companyworld import (
    CompanyWorldBundleRepository,
    CompanyWorldObservatoryRuntimeFactory,
)
from investigation_world.observatory.interventions import (
    InterventionMutation,
    InterventionSpec,
    materialize_companyworld_intervention,
)
from investigation_world.observatory.models import (
    HarnessSpec,
    LongitudinalCell,
    ModelSpec,
    ScenarioRef,
    VerifierSpec,
    WorldKind,
    WorldRef,
)
from investigation_world.observatory.runtime_interventions import (
    InterventionAwareCompanyWorldRuntime,
)


def _episode() -> CompanyWorldEpisode:
    return CompanyWorldEpisode(
        episode_id="EP-1",
        world_id="WORLD-1",
        task=CompanyWorldTask(
            task_id="TASK-1",
            world_id="WORLD-1",
            task_type="LOOKUP",
            objective="Inspect ERP status.",
            target_object_type="ORDER",
            target_object_id="ORD-1",
            permitted_systems=[CompanySystem.ERP],
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
            answer_class="lookup",
            expected_resolution="OPEN",
            facts=[],
        ),
    )


def _cell(repository: CompanyWorldBundleRepository) -> LongitudinalCell:
    return LongitudinalCell(
        world=WorldRef(
            world_id=repository.world_id,
            version=repository.bundle_version,
            kind=WorldKind.OPERATIONAL,
        ),
        scenario=ScenarioRef(
            scenario_id="EP-1",
            task_id="TASK-1",
            seed=1,
        ),
        model=ModelSpec(provider="test", model_id="model-a", snapshot="v1"),
        harness=HarnessSpec(harness_id="companyworld-json-agent", version="1"),
        verifier=VerifierSpec(verifier_id="companyworld", version="1"),
        time_snapshot="2026-08-26T12:00:00+00:00",
    )


def test_factory_uses_intervention_runtime_only_for_scheduled_perturbations():
    source = CompanyWorldBundleRepository([_episode()], taskset_version="test-v1")
    baseline_context = CompanyWorldObservatoryRuntimeFactory(source).create(_cell(source))

    spec = InterventionSpec(
        name="erp-one-shot",
        scenario=ScenarioRef(scenario_id="EP-1", task_id="TASK-1", seed=1),
        mutations=[
            InterventionMutation(
                kind=MutationKind.TOOL_FAILURE,
                seed=7,
                parameters={"system": "ERP", "at_step": 0, "persistent": False},
            )
        ],
    )
    variant, _ = materialize_companyworld_intervention(source, spec)
    treatment_context = CompanyWorldObservatoryRuntimeFactory(variant).create(_cell(variant))

    assert type(baseline_context.runtime) is CompanyWorldRuntime
    assert isinstance(treatment_context.runtime, InterventionAwareCompanyWorldRuntime)
    assert baseline_context.runtime_version == "companyworld-runtime-v2"
    assert treatment_context.runtime_version == "companyworld-runtime-v2"
