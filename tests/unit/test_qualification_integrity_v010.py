import pytest

from investigation_world.projectworld.v2_grammar import compile_project_grammar, default_project_grammar
from investigation_world.projectworld.v2_models import POStatus, ProjectType, V2Action, V2ActionKind
from investigation_world.projectworld.v2_runtime import OperationalProjectWorldV2
from investigation_world.qualification.cluster_split import cluster_disjoint_split_map
from investigation_world.qualification.models import PolicyClass, QualificationScenario, QualificationSplit
from investigation_world.qualification.projectworld_calibration import _progress_controlled
from investigation_world.qualification.sre import SRECausalClass, _keyword_prediction


def _scenario(scenario_id: str, text: str) -> QualificationScenario:
    return QualificationScenario(
        scenario_id=scenario_id,
        source_group_id=f"source:{scenario_id}",
        split=QualificationSplit.TRAIN,
        normalized_text=text,
        public_digest=f"public-{scenario_id}",
    )


def test_near_duplicate_components_are_never_split_across_qualification_panels():
    scenarios = [
        _scenario("A", "database network incident affecting login requests in production"),
        _scenario("B", "database network incident affecting login requests in production."),
        _scenario("C", "capacity saturation caused worker overload"),
        _scenario("D", "deployment rollback after release regression"),
        _scenario("E", "transient intermittent API errors recovered"),
        _scenario("F", "power hardware failure in storage cluster"),
    ]

    mapping = cluster_disjoint_split_map(scenarios)

    assert mapping["A"] == mapping["B"]
    assert set(mapping.values()) == set(QualificationSplit)


def test_projectworld_authority_owned_packages_are_executable_by_their_owner():
    spec = compile_project_grammar(
        default_project_grammar(ProjectType.COMMERCIAL, project_id="AUTHORITY-FEASIBILITY", seed=1)
    )
    authority = next(role for role in spec.roles if role.role_id == "authority")
    owned = [work for work in spec.work_packages if work.owner_role_id == "authority"]

    assert owned
    assert V2ActionKind.START_WORK in authority.allowed_actions


def test_projectworld_noop_policy_receives_zero_aggregate_reward():
    spec = compile_project_grammar(
        default_project_grammar(ProjectType.COMMERCIAL, project_id="NOOP-REWARD", seed=2)
    )
    world = OperationalProjectWorldV2(spec)

    report = world.verify()

    assert report.completion == 0.0
    assert report.schedule == 1.0
    assert report.cost == 1.0
    assert report.overall_reward == 0.0
    assert report.passed is False


def test_arrived_purchase_orders_do_not_consume_storage_commitment_twice():
    grammar = default_project_grammar(ProjectType.COMMERCIAL, project_id="PO-STORAGE", seed=3)
    grammar = grammar.model_copy(update={"disturbance_process": []})
    world = OperationalProjectWorldV2(compile_project_grammar(grammar))
    resource = world._resources["concrete"]
    supplier = min(
        (item for item in world.spec.suppliers if item.resource_id == "concrete"),
        key=lambda item: item.lead_days,
    )
    quantity = min(600.0, supplier.capacity_per_order)
    placed = world.step(
        "procurement",
        V2Action(
            kind=V2ActionKind.PLACE_PO,
            target_id="concrete",
            parameters={"supplier_id": supplier.supplier_id, "quantity": quantity},
        ),
    )
    assert placed.accepted
    order = world.state.procurement_orders["PO-00001"]
    world.step(
        "project_manager",
        V2Action(kind=V2ActionKind.ADVANCE_TIME, parameters={"days": order.expected_day}),
    )
    assert order.status == POStatus.ARRIVED
    assert world.state.resource_available["concrete"] == quantity

    # Consume the arrived material, freeing storage, then order it again. The historical ARRIVED
    # PO must not be counted as an outstanding storage commitment.
    world.state.resource_available["concrete"] = 0.0
    second = world.step(
        "procurement",
        V2Action(
            kind=V2ActionKind.PLACE_PO,
            target_id="concrete",
            parameters={"supplier_id": supplier.supplier_id, "quantity": quantity},
        ),
    )
    assert resource.storage_capacity is not None
    assert second.accepted


@pytest.mark.parametrize("project_type", list(ProjectType))
def test_projectworld_oracle_can_complete_every_structural_archetype(project_type: ProjectType):
    spec = compile_project_grammar(
        default_project_grammar(project_type, project_id=f"ORACLE-{project_type.value}", seed=7)
    )

    reward, passed, metadata = _progress_controlled(
        spec,
        mode=PolicyClass.ORACLE,
        random_seed=7,
    )

    assert passed is True, (project_type, metadata)
    assert metadata["completion"] == 1.0
    assert reward >= 0.95


def test_competent_sre_policy_respects_causal_ontology_precedence():
    public = "Traffic rose after a release; rollback is underway while capacity is monitored."

    competent = _keyword_prediction(public, competent=True)
    myopic = _keyword_prediction(public, competent=False)

    assert competent == SRECausalClass.REGRESSION
    assert myopic == SRECausalClass.CAPACITY
