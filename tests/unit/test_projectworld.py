import pytest

from investigation_world.projectworld import (
    OperationalProjectWorld,
    OperationalProjectWorldSpec,
    ProjectAction,
    ProjectActionError,
    ProjectActionKind,
    ProjectDomain,
    ProjectOracle,
    ProjectPhase,
    ProjectRequirement,
    ProjectResourceSpec,
    ProjectRoleSpec,
    ProjectScenario,
    ProjectWorkPackageSpec,
    ProjectWorldSession,
    ResourceKind,
    WorkPackageStatus,
    build_construction_project_world,
)


def _minimal_world() -> ProjectScenario:
    roles = [
        ProjectRoleSpec(
            role_id="builder",
            label="Builder",
            allowed_actions=[ProjectActionKind.START_WORK, ProjectActionKind.ADVANCE_TIME],
            can_view_all=True,
        ),
        ProjectRoleSpec(
            role_id="inspector",
            label="Inspector",
            allowed_actions=[ProjectActionKind.INSPECT, ProjectActionKind.ADVANCE_TIME],
            can_view_all=True,
        ),
    ]
    resources = [
        ProjectResourceSpec(
            resource_id="crew",
            label="Crew",
            kind=ResourceKind.LABOR,
            unit="crew",
            initial_available=1,
            consumable=False,
        )
    ]
    work = [
        ProjectWorkPackageSpec(
            work_package_id="a",
            name="A",
            phase=ProjectPhase.EXECUTION,
            owner_role_id="builder",
            duration_days=2,
            direct_cost=10,
            required_resources={"crew": 1},
            requires_inspection=True,
            deliverables=["a_artifact"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="b",
            name="B",
            phase=ProjectPhase.HANDOVER,
            owner_role_id="builder",
            dependencies=["a"],
            duration_days=1,
            direct_cost=5,
        ),
    ]
    return ProjectScenario(
        spec=OperationalProjectWorldSpec(
            world_id="world",
            project_id="project",
            name="Minimal",
            domain=ProjectDomain.GENERIC,
            budget=100,
            deadline_days=10,
            roles=roles,
            resources=resources,
            work_packages=work,
            requirements=[
                ProjectRequirement(
                    requirement_id="done",
                    description="Project delivered",
                    satisfied_by_work_packages=["b"],
                )
            ],
        ),
        oracle=ProjectOracle(),
    )


def test_public_payload_hides_private_oracle():
    scenario = build_construction_project_world(seed=42)
    payload = scenario.public_payload()
    text = str(payload)
    assert "oracle" not in payload
    assert "latent_defects" not in text
    assert "resource_delay_days" not in text
    assert payload["seed"] is None


def test_identity_bound_session_rejects_role_impersonation():
    world = OperationalProjectWorld(_minimal_world())
    session = ProjectWorldSession(world, "builder")

    with pytest.raises(ProjectActionError, match="cannot submit action as inspector"):
        session.step(
            ProjectAction(
                actor_role_id="inspector",
                kind=ProjectActionKind.ADVANCE_TIME,
                parameters={"days": 1},
            )
        )

    transition = session.act(ProjectActionKind.START_WORK, target_id="a")
    assert transition.accepted is True
    assert transition.observation.role_id == "builder"
    assert world.trace()[-1]["actor_role_id"] == "builder"


def test_identity_bound_session_validates_role_at_binding_time():
    with pytest.raises(ProjectActionError, match="unknown role"):
        ProjectWorldSession(OperationalProjectWorld(_minimal_world()), "owner")


def test_dependency_and_role_preconditions_are_enforced_without_crashing_episode():
    world = OperationalProjectWorld(_minimal_world())
    blocked = world.step(
        ProjectAction(actor_role_id="builder", kind=ProjectActionKind.START_WORK, target_id="b")
    )
    assert blocked.accepted is False
    assert blocked.reward < 0
    assert world.state.work_package_status["b"] == WorkPackageStatus.BLOCKED

    wrong_role = world.step(
        ProjectAction(actor_role_id="inspector", kind=ProjectActionKind.START_WORK, target_id="a")
    )
    assert wrong_role.accepted is False
    assert world.rejected_actions == 2


def test_event_driven_completion_requires_inspection_before_unlocking_dependency():
    world = OperationalProjectWorld(_minimal_world())
    assert world.step(
        ProjectAction(actor_role_id="builder", kind=ProjectActionKind.START_WORK, target_id="a")
    ).accepted
    world.step(
        ProjectAction(
            actor_role_id="builder",
            kind=ProjectActionKind.ADVANCE_TIME,
            parameters={"days": 2},
        )
    )
    assert world.state.work_package_status["a"] == WorkPackageStatus.AWAITING_INSPECTION
    assert world.state.work_package_status["b"] == WorkPackageStatus.BLOCKED
    assert "a_artifact" not in world.state.completed_deliverables

    result = world.step(
        ProjectAction(actor_role_id="inspector", kind=ProjectActionKind.INSPECT, target_id="a")
    )
    assert result.accepted
    assert world.state.work_package_status["a"] == WorkPackageStatus.COMPLETE
    assert world.state.work_package_status["b"] == WorkPackageStatus.READY
    assert world.state.resource_available["crew"] == 1
    assert "a_artifact" in world.state.completed_deliverables


def test_construction_design_decision_changes_downstream_execution_state():
    world = OperationalProjectWorld(build_construction_project_world(seed=42))
    baseline_duration = world.state.effective_duration_days["superstructure"]
    baseline_cost = world.state.effective_direct_cost["superstructure"]

    result = world.step(
        ProjectAction(
            actor_role_id="architect",
            kind=ProjectActionKind.CHOOSE_OPTION,
            target_id="structural_system",
            parameters={"option_id": "structural_steel"},
        )
    )
    assert result.accepted
    assert world.state.effective_duration_days["superstructure"] == baseline_duration - 16
    assert world.state.effective_direct_cost["superstructure"] == baseline_cost + 1_350_000
    assert world.state.effective_required_resources["superstructure"] == {
        "site_labor": 34,
        "structural_steel": 620,
    }


def test_construction_resource_delay_is_hidden_until_expected_delivery_is_missed():
    world = OperationalProjectWorld(build_construction_project_world(seed=42))
    result = world.step(
        ProjectAction(
            actor_role_id="procurement_manager",
            kind=ProjectActionKind.PROCURE,
            target_id="mep_equipment",
            parameters={"quantity": 8},
        )
    )
    assert result.accepted
    expected_day = world.state.procurement_orders["PO-00001"].expected_day
    world.step(
        ProjectAction(
            actor_role_id="procurement_manager",
            kind=ProjectActionKind.ADVANCE_TIME,
            parameters={"days": expected_day},
        )
    )
    assert world.state.resource_available["mep_equipment"] == 0
    assert world.state.procurement_orders["PO-00001"].status == "ordered"


def test_verifier_accepts_completed_minimal_project():
    world = OperationalProjectWorld(_minimal_world())
    world.step(
        ProjectAction(actor_role_id="builder", kind=ProjectActionKind.START_WORK, target_id="a")
    )
    world.step(
        ProjectAction(
            actor_role_id="builder",
            kind=ProjectActionKind.ADVANCE_TIME,
            parameters={"days": 2},
        )
    )
    world.step(
        ProjectAction(actor_role_id="inspector", kind=ProjectActionKind.INSPECT, target_id="a")
    )
    world.step(
        ProjectAction(actor_role_id="builder", kind=ProjectActionKind.START_WORK, target_id="b")
    )
    world.step(
        ProjectAction(
            actor_role_id="builder",
            kind=ProjectActionKind.ADVANCE_TIME,
            parameters={"days": 1},
        )
    )

    report = world.verify()
    assert report.passed is True
    assert report.completion == 1.0
    assert report.requirements == 1.0
    assert report.overall_reward == 1.0
