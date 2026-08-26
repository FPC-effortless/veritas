from investigation_world.projectworld import (
    OperationalProjectWorldRuntime,
    ProjectAction,
    ProjectActionType,
    ProjectPhase,
    ProjectRole,
    construction_episode,
)


def act(kind, target, object_id, *, evidence=None, **parameters):
    return ProjectAction(
        action_type=kind,
        target_object_type=target,
        target_object_id=object_id,
        parameters=parameters,
        evidence_ids=evidence or [],
    )


def advance_phase(runtime, phase):
    result = runtime.act(
        ProjectRole.PROJECT_MANAGER,
        act(
            ProjectActionType.ADVANCE_PHASE,
            "project",
            "CONSTRUCTION-001",
            evidence=["EV-PHASE-GATE"],
            phase=phase.value,
        ),
    )
    assert result.applied, result.reason


def complete_after(runtime, activity_id, duration):
    started = runtime.act(
        ProjectRole.SITE_MANAGER,
        act(ProjectActionType.START_ACTIVITY, "activity", activity_id),
    )
    assert started.applied, started.reason
    runtime.advance(duration)
    return runtime.act(
        ProjectRole.SITE_MANAGER,
        act(ProjectActionType.COMPLETE_ACTIVITY, "activity", activity_id),
    )


def test_full_disturbed_project_can_reach_verified_owner_acceptance():
    runtime = OperationalProjectWorldRuntime(construction_episode())
    assert runtime.act(
        ProjectRole.PROJECT_MANAGER,
        act(
            ProjectActionType.APPROVE_DESIGN,
            "design",
            "D-001",
            evidence=["EV-DESIGN-REVIEW"],
        ),
    ).applied
    for phase in [ProjectPhase.PRECONSTRUCTION, ProjectPhase.PROCUREMENT, ProjectPhase.CONSTRUCTION]:
        advance_phase(runtime, phase)

    assert complete_after(runtime, "A100", 2).applied
    assert complete_after(runtime, "A200", 2).applied
    assert complete_after(runtime, "A300", 1).applied

    assert runtime.act(
        ProjectRole.SITE_MANAGER,
        act(
            ProjectActionType.MITIGATE_RISK,
            "activity",
            "A400",
            evidence=["EV-MITIGATION"],
        ),
    ).applied
    assert complete_after(runtime, "A400", 3).applied

    started = runtime.act(
        ProjectRole.SITE_MANAGER,
        act(ProjectActionType.START_ACTIVITY, "activity", "A500"),
    )
    assert started.applied
    runtime.advance(4)
    held = runtime.act(
        ProjectRole.SITE_MANAGER,
        act(ProjectActionType.COMPLETE_ACTIVITY, "activity", "A500"),
    )
    assert not held.applied
    assert runtime.act(
        ProjectRole.SITE_MANAGER,
        act(
            ProjectActionType.MITIGATE_RISK,
            "activity",
            "A500",
            evidence=["EV-MITIGATION"],
        ),
    ).applied
    assert runtime.act(
        ProjectRole.SITE_MANAGER,
        act(ProjectActionType.COMPLETE_ACTIVITY, "activity", "A500"),
    ).applied

    assert runtime.act(
        ProjectRole.SITE_MANAGER,
        act(
            ProjectActionType.MITIGATE_RISK,
            "activity",
            "A600",
            evidence=["EV-MITIGATION"],
        ),
    ).applied
    assert complete_after(runtime, "A600", 3).applied

    advance_phase(runtime, ProjectPhase.COMMISSIONING)
    assert complete_after(runtime, "A700", 2).applied
    advance_phase(runtime, ProjectPhase.HANDOVER)
    assert complete_after(runtime, "A800", 1).applied

    assert runtime.act(
        ProjectRole.PROJECT_MANAGER,
        act(ProjectActionType.ISSUE_HANDOFF, "project", "CONSTRUCTION-001"),
    ).applied
    assert runtime.act(
        ProjectRole.OWNER,
        act(
            ProjectActionType.ACCEPT_HANDOFF,
            "project",
            "CONSTRUCTION-001",
            evidence=["EV-HANDOVER"],
        ),
    ).applied
    assert runtime.act(
        ProjectRole.OWNER,
        act(
            ProjectActionType.ACCEPT_PROJECT,
            "project",
            "CONSTRUCTION-001",
            evidence=["EV-HANDOVER"],
        ),
    ).applied

    result = runtime.submit()
    assert result.outcome_score == 1.0
    assert result.overall_reward > 0.8
    assert result.unauthorized_attempts == 0
    assert result.committed_cost < 38_000_000
