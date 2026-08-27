import pytest

from investigation_world.projectworld.v2_grammar import compile_project_grammar, default_project_grammar
from investigation_world.projectworld.v2_models import (
    DisturbanceKind,
    DisturbanceSpec,
    ProjectType,
    V2Action,
    V2ActionKind,
    V2WorkStatus,
)
from investigation_world.projectworld.v2_runtime import OperationalProjectWorldV2


def _world(project_type: ProjectType = ProjectType.DATA_CENTER, *, seed: int = 42):
    grammar = default_project_grammar(project_type, project_id=f"TEST-{project_type.value}", seed=seed)
    return OperationalProjectWorldV2(compile_project_grammar(grammar))


def test_project_archetypes_generate_structurally_different_graphs():
    data_center = compile_project_grammar(default_project_grammar(ProjectType.DATA_CENTER, project_id="DC", seed=1))
    hospital = compile_project_grammar(default_project_grammar(ProjectType.HOSPITAL, project_id="HOSP", seed=1))
    lab = compile_project_grammar(default_project_grammar(ProjectType.LABORATORY, project_id="LAB", seed=1))

    dc_ids = {item.work_package_id for item in data_center.work_packages}
    hospital_ids = {item.work_package_id for item in hospital.work_packages}
    lab_ids = {item.work_package_id for item in lab.work_packages}

    assert {"generator_plant", "ups_switchgear", "redundancy_test"} <= dc_ids
    assert {"medical_gas", "infection_control_hvac", "regulatory_survey"} <= hospital_ids
    assert {"containment_envelope", "specialty_gases", "certification"} <= lab_ids
    assert dc_ids != hospital_ids != lab_ids


def test_projectworld_v2_identity_is_environment_bound():
    world = _world(ProjectType.COMMERCIAL)
    builder = world.bind("builder")

    transition = builder.step(V2Action(kind=V2ActionKind.APPROVE, target_id="authority_submission"))

    assert transition.accepted is False
    assert transition.observation.role_id == "builder"
    assert world.state.authority_violations == 1


def test_persistent_po_progresses_order_acknowledge_ship_arrive():
    grammar = default_project_grammar(ProjectType.COMMERCIAL, project_id="PO", seed=4)
    grammar = grammar.model_copy(update={"disturbance_process": []})
    world = OperationalProjectWorldV2(compile_project_grammar(grammar))
    supplier = next(item for item in world.spec.suppliers if item.resource_id == "concrete")

    placed = world.step(
        "procurement",
        V2Action(
            kind=V2ActionKind.PLACE_PO,
            target_id="concrete",
            parameters={"supplier_id": supplier.supplier_id, "quantity": 600},
        ),
    )
    assert placed.accepted
    order = world.state.procurement_orders["PO-00001"]
    assert order.status.value == "ordered"

    world.step("project_manager", V2Action(kind=V2ActionKind.ADVANCE_TIME, parameters={"days": 1}))
    assert order.status.value == "acknowledged"
    world.step(
        "project_manager",
        V2Action(kind=V2ActionKind.ADVANCE_TIME, parameters={"days": max(1, order.expected_day - world.state.day)}),
    )
    assert order.status.value == "arrived"
    assert world.state.resource_available["concrete"] == 600


def test_expedite_changes_eta_and_committed_cost():
    grammar = default_project_grammar(ProjectType.DATA_CENTER, project_id="EXP", seed=2)
    grammar = grammar.model_copy(update={"disturbance_process": []})
    world = OperationalProjectWorldV2(compile_project_grammar(grammar))
    supplier = next(
        item for item in world.spec.suppliers if item.resource_id == "generator_sets" and item.expedite_days > 0
    )
    world.step(
        "procurement",
        V2Action(
            kind=V2ActionKind.PLACE_PO,
            target_id="generator_sets",
            parameters={"supplier_id": supplier.supplier_id, "quantity": 4},
        ),
    )
    order = world.state.procurement_orders["PO-00001"]
    before_eta = order.expected_day
    before_cost = world.state.cost_spent

    result = world.step("procurement", V2Action(kind=V2ActionKind.EXPEDITE_PO, target_id=order.order_id))

    assert result.accepted
    assert order.expected_day < before_eta
    assert order.expedite_premium > 0
    assert world.state.cost_spent > before_cost


def test_rework_consumes_real_resources_and_cannot_start_without_them():
    grammar = default_project_grammar(ProjectType.COMMERCIAL, project_id="RW", seed=3)
    grammar = grammar.model_copy(
        update={
            "disturbance_process": [
                DisturbanceSpec(
                    disturbance_id="DEFECT",
                    day=1,
                    kind=DisturbanceKind.DEFECT,
                    target_id="foundations",
                    parameters={"severity": 0.8, "rework_days": 2, "rework_cost": 50_000},
                )
            ]
        }
    )
    world = OperationalProjectWorldV2(compile_project_grammar(grammar))
    world.step("project_manager", V2Action(kind=V2ActionKind.ADVANCE_TIME, parameters={"days": 1}))
    # Inject the issue at completion boundary to test rework resource semantics without executing
    # the full upstream project sequence.
    world.state.work_status["foundations"] = V2WorkStatus.IN_PROGRESS
    world.state.work_remaining_days["foundations"] = 0
    world._finish_execution("foundations")
    issue = next(iter(world.state.issues.values()))
    assert issue.rework_resource_demand["concrete"] > 0
    assert world.state.resource_available["concrete"] == 0

    blocked = world.step("builder", V2Action(kind=V2ActionKind.RESOLVE_ISSUE, target_id=issue.issue_id))

    assert blocked.accepted is False
    assert issue.rework_started_day is None


def test_role_scoped_observation_hides_procurement_unrelated_to_visible_work():
    world = _world(ProjectType.DATA_CENTER)
    supplier = next(item for item in world.spec.suppliers if item.resource_id == "generator_sets")
    world.step(
        "procurement",
        V2Action(
            kind=V2ActionKind.PLACE_PO,
            target_id="generator_sets",
            parameters={"supplier_id": supplier.supplier_id, "quantity": 4},
        ),
    )

    # The design lead intentionally sees builder work in the stakeholder graph. The authority role
    # does not, so generator procurement is genuinely outside its role-scoped operational view.
    authority = world.observe("authority")
    procurement = world.observe("procurement")

    assert authority.procurement_orders == []
    assert len(procurement.procurement_orders) == 1


def test_outcome_contracts_are_independent_of_completion():
    grammar = default_project_grammar(ProjectType.COMMERCIAL, project_id="VERIFY", seed=5)
    grammar = grammar.model_copy(update={"disturbance_process": []})
    world = OperationalProjectWorldV2(compile_project_grammar(grammar))
    for work_id in world.state.work_status:
        world.state.work_status[work_id] = V2WorkStatus.COMPLETE
    for work in world.spec.work_packages:
        world.state.completed_deliverables.extend(work.deliverables)
        if work.requires_inspection:
            world.state.inspection_passed.append(work.work_package_id)
        if work.requires_approval:
            world.state.approvals[work.work_package_id] = work.approval_role_ids[0]

    clean = world.verify()
    assert clean.completion == 1.0
    assert clean.quality == 1.0
    assert clean.authority == 1.0

    world.state.authority_violations = 1
    authority_failure = world.verify()
    assert authority_failure.completion == 1.0
    assert authority_failure.technical == 1.0
    assert authority_failure.authority == 0.0
    assert authority_failure.passed is False
