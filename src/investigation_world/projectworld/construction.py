from __future__ import annotations

from investigation_world.projectworld.models import (
    ConditionOperator,
    OperationalProjectEpisode,
    ProjectActionPolicy,
    ProjectActionType,
    ProjectActivity,
    ProjectEffectTemplate,
    ProjectEvidenceRecord,
    ProjectExogenousEvent,
    ProjectOutcomeCondition,
    ProjectPhase,
    ProjectResource,
    ProjectRole,
    ProjectRolePolicy,
    ProjectStateValue,
    ProjectTask,
    ProjectOracle,
    VerificationDimension,
)
from investigation_world.projectworld.sources import FusedSourceField, construction_source_manifest


ALL_PHASES = list(ProjectPhase)
DESIGN_PHASES = [ProjectPhase.CONCEPT, ProjectPhase.DESIGN, ProjectPhase.PRECONSTRUCTION]
DELIVERY_PHASES = [
    ProjectPhase.PRECONSTRUCTION,
    ProjectPhase.PROCUREMENT,
    ProjectPhase.CONSTRUCTION,
    ProjectPhase.COMMISSIONING,
    ProjectPhase.HANDOVER,
]


def _role(
    role: ProjectRole,
    read: list[str],
    write: list[str],
    *,
    authority: float = 0.0,
    approve: bool = False,
    delegate: bool = False,
) -> ProjectRolePolicy:
    return ProjectRolePolicy(
        role=role,
        readable_namespaces=read,
        writable_namespaces=write,
        direct_authority_limit=authority,
        can_approve=approve,
        can_delegate=delegate,
    )


def construction_role_policies() -> list[ProjectRolePolicy]:
    common = ["project", "schedule", "evidence"]
    return [
        _role(ProjectRole.OWNER, ["*"], ["project", "commercial", "handover"], authority=5_000_000, approve=True, delegate=True),
        _role(ProjectRole.OWNERS_REP, ["*"], ["project", "commercial", "design", "handover"], authority=1_000_000, approve=True, delegate=True),
        _role(ProjectRole.PROJECT_DIRECTOR, ["*"], ["*"], authority=750_000, approve=True, delegate=True),
        _role(
            ProjectRole.PROJECT_MANAGER,
            ["*"],
            ["project", "schedule", "design", "site", "quality", "safety", "procurement", "commercial", "handover"],
            authority=250_000,
            approve=True,
            delegate=True,
        ),
        _role(ProjectRole.ARCHITECT, common + ["design", "site", "quality"], ["design", "project", "quality"], authority=25_000),
        _role(ProjectRole.STRUCTURAL_ENGINEER, common + ["design", "site", "quality"], ["design", "quality"], authority=25_000),
        _role(ProjectRole.MEP_ENGINEER, common + ["design", "site", "quality", "handover"], ["design", "quality", "handover"], authority=25_000),
        _role(ProjectRole.QUANTITY_SURVEYOR, common + ["commercial", "procurement", "design"], ["commercial", "procurement"], authority=100_000),
        _role(ProjectRole.BIM_COORDINATOR, common + ["design", "site", "quality"], ["design", "quality"], authority=10_000),
        _role(ProjectRole.PROCUREMENT_MANAGER, common + ["commercial", "procurement", "design"], ["procurement", "commercial", "schedule"], authority=150_000),
        _role(ProjectRole.CONTRACT_ADMINISTRATOR, common + ["commercial", "procurement"], ["commercial", "project"], authority=100_000, approve=True),
        _role(ProjectRole.SITE_MANAGER, common + ["site", "design", "quality", "safety", "procurement"], ["project", "site", "schedule", "quality", "safety"], authority=50_000),
        _role(ProjectRole.SUPERINTENDENT, common + ["site", "design", "quality", "safety"], ["site", "schedule", "safety"], authority=25_000),
        _role(ProjectRole.SAFETY_MANAGER, common + ["site", "safety"], ["project", "safety", "site", "schedule"], authority=5_000, approve=True),
        _role(ProjectRole.QA_QC_INSPECTOR, common + ["site", "design", "quality"], ["quality", "site"], authority=5_000, approve=True),
        _role(ProjectRole.SUBCONTRACTOR, common + ["site", "design", "quality", "safety", "procurement"], ["site", "quality", "procurement", "schedule"], authority=10_000),
        _role(ProjectRole.COMMISSIONING_MANAGER, common + ["design", "site", "quality", "handover"], ["quality", "handover", "site", "schedule"], authority=25_000, approve=True),
    ]


def _policy(
    action: ProjectActionType,
    roles: list[ProjectRole],
    phases: list[ProjectPhase],
    object_types: list[str],
    *,
    effects: list[ProjectEffectTemplate] | None = None,
    evidence: list[str] | None = None,
    financial_parameter: str | None = None,
    irreversible: bool = False,
    resource_gated: bool = False,
    description: str = "",
) -> ProjectActionPolicy:
    return ProjectActionPolicy(
        action_type=action,
        allowed_roles=roles,
        allowed_phases=phases,
        allowed_object_types=object_types,
        effects=effects or [],
        required_evidence_types=evidence or [],
        financial_parameter=financial_parameter,
        irreversible=irreversible,
        resource_gated=resource_gated,
        description=description,
    )


def construction_action_policies() -> list[ProjectActionPolicy]:
    designers = [ProjectRole.ARCHITECT, ProjectRole.STRUCTURAL_ENGINEER, ProjectRole.MEP_ENGINEER]
    managers = [ProjectRole.PROJECT_MANAGER, ProjectRole.PROJECT_DIRECTOR, ProjectRole.OWNERS_REP]
    site_leads = [ProjectRole.SITE_MANAGER, ProjectRole.SUPERINTENDENT, ProjectRole.SUBCONTRACTOR]
    effect = ProjectEffectTemplate
    return [
        _policy(ProjectActionType.SUBMIT_DESIGN, designers, DESIGN_PHASES, ["design"], effects=[effect(field_name="status", constant_value="SUBMITTED", namespace="design"), effect(field_name="revision", parameter_name="revision", namespace="design")], description="Submit a coordinated discipline design revision."),
        _policy(ProjectActionType.REVIEW_DESIGN, [ProjectRole.BIM_COORDINATOR, *managers], DESIGN_PHASES, ["design"], effects=[effect(field_name="status", constant_value="UNDER_REVIEW", namespace="design")]),
        _policy(ProjectActionType.APPROVE_DESIGN, managers, DESIGN_PHASES, ["design"], effects=[effect(field_name="status", constant_value="APPROVED", namespace="design")], evidence=["design_review"]),
        _policy(ProjectActionType.REJECT_DESIGN, [ProjectRole.BIM_COORDINATOR, *managers], DESIGN_PHASES, ["design"], effects=[effect(field_name="status", constant_value="REJECTED", namespace="design")]),
        _policy(ProjectActionType.ISSUE_RFI, [*site_leads, ProjectRole.BIM_COORDINATOR, ProjectRole.PROCUREMENT_MANAGER], DELIVERY_PHASES, ["rfi"], effects=[effect(field_name="status", constant_value="OPEN", namespace="project"), effect(field_name="question", parameter_name="question", namespace="project")]),
        _policy(ProjectActionType.RESPOND_RFI, [*designers, *managers], DELIVERY_PHASES, ["rfi"], effects=[effect(field_name="status", constant_value="ANSWERED", namespace="project"), effect(field_name="answer", parameter_name="answer", namespace="project")]),
        _policy(ProjectActionType.SUBMIT_SUBMITTAL, [ProjectRole.SUBCONTRACTOR, ProjectRole.PROCUREMENT_MANAGER], DELIVERY_PHASES, ["submittal"], effects=[effect(field_name="status", constant_value="SUBMITTED", namespace="procurement")]),
        _policy(ProjectActionType.APPROVE_SUBMITTAL, [*designers, ProjectRole.QA_QC_INSPECTOR, *managers], DELIVERY_PHASES, ["submittal"], effects=[effect(field_name="status", constant_value="APPROVED", namespace="procurement")]),
        _policy(ProjectActionType.CREATE_WORK_PACKAGE, [ProjectRole.PROJECT_MANAGER, ProjectRole.QUANTITY_SURVEYOR, ProjectRole.PROCUREMENT_MANAGER], [ProjectPhase.PRECONSTRUCTION, ProjectPhase.PROCUREMENT], ["work_package"], effects=[effect(field_name="status", constant_value="PLANNED", namespace="procurement"), effect(field_name="scope", parameter_name="scope", namespace="procurement")]),
        _policy(ProjectActionType.RELEASE_WORK_PACKAGE, [ProjectRole.PROJECT_MANAGER, ProjectRole.PROJECT_DIRECTOR, ProjectRole.OWNERS_REP], [ProjectPhase.PRECONSTRUCTION, ProjectPhase.PROCUREMENT], ["work_package"], effects=[effect(field_name="status", constant_value="RELEASED", namespace="procurement")], evidence=["phase_gate"]),
        _policy(ProjectActionType.PROCURE_PACKAGE, [ProjectRole.PROCUREMENT_MANAGER, ProjectRole.QUANTITY_SURVEYOR, *managers], [ProjectPhase.PROCUREMENT, ProjectPhase.CONSTRUCTION], ["work_package"], effects=[effect(field_name="status", constant_value="ORDERED", namespace="procurement")], financial_parameter="committed_cost"),
        _policy(ProjectActionType.EXPEDITE_PACKAGE, [ProjectRole.PROCUREMENT_MANAGER, *managers], [ProjectPhase.PROCUREMENT, ProjectPhase.CONSTRUCTION], ["work_package", "activity"], effects=[effect(field_name="blocked", constant_value=False, namespace="schedule")], financial_parameter="expedite_cost"),
        _policy(ProjectActionType.START_ACTIVITY, site_leads + [ProjectRole.COMMISSIONING_MANAGER], [ProjectPhase.CONSTRUCTION, ProjectPhase.COMMISSIONING, ProjectPhase.HANDOVER], ["activity"], effects=[effect(field_name="status", constant_value="IN_PROGRESS", namespace="schedule")], resource_gated=True),
        _policy(ProjectActionType.COMPLETE_ACTIVITY, site_leads + [ProjectRole.COMMISSIONING_MANAGER], [ProjectPhase.CONSTRUCTION, ProjectPhase.COMMISSIONING, ProjectPhase.HANDOVER], ["activity"], effects=[effect(field_name="status", constant_value="COMPLETED", namespace="schedule")]),
        _policy(ProjectActionType.PAUSE_ACTIVITY, [ProjectRole.SITE_MANAGER, ProjectRole.SUPERINTENDENT, ProjectRole.SAFETY_MANAGER, *managers], [ProjectPhase.CONSTRUCTION, ProjectPhase.COMMISSIONING], ["activity"], effects=[effect(field_name="status", constant_value="PAUSED", namespace="schedule")]),
        _policy(ProjectActionType.UPDATE_SCHEDULE, [ProjectRole.PROJECT_MANAGER, ProjectRole.SITE_MANAGER, ProjectRole.SUPERINTENDENT], DELIVERY_PHASES, ["activity", "project"], effects=[effect(field_name="forecast_finish_tick", parameter_name="forecast_finish_tick", namespace="schedule")]),
        _policy(ProjectActionType.RECORD_PROGRESS, [ProjectRole.SITE_MANAGER, ProjectRole.SUPERINTENDENT, ProjectRole.SUBCONTRACTOR, ProjectRole.PROJECT_MANAGER], [ProjectPhase.CONSTRUCTION, ProjectPhase.COMMISSIONING], ["activity"], effects=[effect(field_name="percent_complete", parameter_name="percent_complete", namespace="schedule")]),
        _policy(ProjectActionType.RAISE_RISK, [ProjectRole.SAFETY_MANAGER, ProjectRole.SITE_MANAGER, ProjectRole.PROJECT_MANAGER, ProjectRole.PROCUREMENT_MANAGER], DELIVERY_PHASES, ["risk", "activity", "work_package"], effects=[effect(field_name="risk_status", constant_value="OPEN", namespace="project")]),
        _policy(ProjectActionType.MITIGATE_RISK, [ProjectRole.SAFETY_MANAGER, ProjectRole.SITE_MANAGER, ProjectRole.PROJECT_MANAGER, ProjectRole.PROCUREMENT_MANAGER], DELIVERY_PHASES, ["risk", "activity", "work_package"], effects=[effect(field_name="risk_status", constant_value="MITIGATED", namespace="project"), effect(field_name="blocked", constant_value=False, namespace="schedule"), effect(field_name="safety_hold", constant_value=False, namespace="safety")], evidence=["mitigation_plan"]),
        _policy(ProjectActionType.RECORD_SAFETY_OBSERVATION, [ProjectRole.SAFETY_MANAGER, ProjectRole.SITE_MANAGER, ProjectRole.SUPERINTENDENT], [ProjectPhase.CONSTRUCTION, ProjectPhase.COMMISSIONING], ["activity", "safety_event"], effects=[effect(field_name="safety_observation", parameter_name="observation", namespace="safety")]),
        _policy(ProjectActionType.STOP_WORK, [ProjectRole.SAFETY_MANAGER, ProjectRole.SITE_MANAGER, ProjectRole.PROJECT_MANAGER], [ProjectPhase.CONSTRUCTION, ProjectPhase.COMMISSIONING], ["activity"], effects=[effect(field_name="safety_hold", constant_value=True, namespace="safety")]),
        _policy(ProjectActionType.INSPECT_WORK, [ProjectRole.QA_QC_INSPECTOR, ProjectRole.COMMISSIONING_MANAGER], [ProjectPhase.CONSTRUCTION, ProjectPhase.COMMISSIONING], ["activity", "inspection"], effects=[effect(field_name="inspection_status", constant_value="INSPECTED", namespace="quality"), effect(field_name="inspection_result", parameter_name="result", namespace="quality")], evidence=["inspection_record"]),
        _policy(ProjectActionType.ACCEPT_WORK, [ProjectRole.QA_QC_INSPECTOR, ProjectRole.PROJECT_MANAGER, ProjectRole.COMMISSIONING_MANAGER], [ProjectPhase.CONSTRUCTION, ProjectPhase.COMMISSIONING], ["activity", "inspection"], effects=[effect(field_name="quality_status", constant_value="ACCEPTED", namespace="quality")], evidence=["inspection_record"]),
        _policy(ProjectActionType.REJECT_WORK, [ProjectRole.QA_QC_INSPECTOR, ProjectRole.PROJECT_MANAGER, ProjectRole.COMMISSIONING_MANAGER], [ProjectPhase.CONSTRUCTION, ProjectPhase.COMMISSIONING], ["activity", "inspection"], effects=[effect(field_name="quality_status", constant_value="REWORK_REQUIRED", namespace="quality")], evidence=["inspection_record"]),
        _policy(ProjectActionType.CREATE_CHANGE_ORDER, [ProjectRole.CONTRACT_ADMINISTRATOR, ProjectRole.QUANTITY_SURVEYOR, *managers], DELIVERY_PHASES, ["change_order"], effects=[effect(field_name="status", constant_value="PROPOSED", namespace="commercial")]),
        _policy(ProjectActionType.APPROVE_CHANGE_ORDER, [ProjectRole.CONTRACT_ADMINISTRATOR, *managers, ProjectRole.OWNER], DELIVERY_PHASES, ["change_order"], effects=[effect(field_name="status", constant_value="APPROVED", namespace="commercial")], financial_parameter="change_value"),
        _policy(ProjectActionType.REJECT_CHANGE_ORDER, [ProjectRole.CONTRACT_ADMINISTRATOR, *managers, ProjectRole.OWNER], DELIVERY_PHASES, ["change_order"], effects=[effect(field_name="status", constant_value="REJECTED", namespace="commercial")]),
        _policy(ProjectActionType.CERTIFY_PAYMENT, [ProjectRole.QUANTITY_SURVEYOR, ProjectRole.CONTRACT_ADMINISTRATOR, ProjectRole.PROJECT_MANAGER], DELIVERY_PHASES, ["payment"], effects=[effect(field_name="status", constant_value="CERTIFIED", namespace="commercial")], financial_parameter="amount", evidence=["payment_evidence"]),
        _policy(ProjectActionType.COMMISSION_SYSTEM, [ProjectRole.COMMISSIONING_MANAGER, ProjectRole.MEP_ENGINEER], [ProjectPhase.COMMISSIONING, ProjectPhase.HANDOVER], ["system", "activity"], effects=[effect(field_name="commissioning_status", constant_value="COMPLETE", namespace="handover"), effect(field_name="test_result", parameter_name="result", namespace="handover")], evidence=["commissioning_test"]),
        _policy(ProjectActionType.ISSUE_HANDOFF, [ProjectRole.PROJECT_MANAGER, ProjectRole.COMMISSIONING_MANAGER], [ProjectPhase.COMMISSIONING, ProjectPhase.HANDOVER], ["project", "work_package"], effects=[effect(field_name="handoff_status", constant_value="ISSUED", namespace="handover")]),
        _policy(ProjectActionType.ACCEPT_HANDOFF, [ProjectRole.OWNER, ProjectRole.OWNERS_REP], [ProjectPhase.HANDOVER], ["project", "work_package"], effects=[effect(field_name="handoff_status", constant_value="ACCEPTED", namespace="handover")], evidence=["handover_package"]),
        _policy(ProjectActionType.ACCEPT_PROJECT, [ProjectRole.OWNER, ProjectRole.OWNERS_REP], [ProjectPhase.HANDOVER], ["project"], effects=[effect(field_name="acceptance_status", constant_value="ACCEPTED", namespace="handover")], evidence=["handover_package"], irreversible=True),
        _policy(ProjectActionType.ADVANCE_PHASE, [ProjectRole.PROJECT_MANAGER, ProjectRole.PROJECT_DIRECTOR, ProjectRole.OWNERS_REP], ALL_PHASES[:-1], ["project"], effects=[effect(field_name="phase", parameter_name="phase", namespace="project")], evidence=["phase_gate"]),
        _policy(ProjectActionType.COMPENSATE_ACTION, [ProjectRole.PROJECT_MANAGER, ProjectRole.PROJECT_DIRECTOR], DELIVERY_PHASES, ["project", "activity", "work_package", "change_order"]),
    ]


def _activity(
    activity_id: str,
    name: str,
    phase: ProjectPhase,
    predecessors: list[str],
    duration: int,
    resources: dict[str, int],
    cost: float,
    *,
    critical: bool = True,
) -> ProjectActivity:
    return ProjectActivity(
        activity_id=activity_id,
        name=name,
        phase=phase,
        predecessor_ids=predecessors,
        duration_ticks=duration,
        resource_demands=resources,
        planned_cost=cost,
        critical=critical,
    )


def construction_episode(
    *,
    project_id: str = "CONSTRUCTION-001",
    budget_limit: float = 38_000_000.0,
) -> OperationalProjectEpisode:
    """Reference multi-role project from design approval through owner acceptance."""
    activities = [
        _activity("A100", "Multidiscipline design coordination", ProjectPhase.CONSTRUCTION, [], 2, {"design_team": 2}, 450_000),
        _activity("A200", "Long-lead procurement release", ProjectPhase.CONSTRUCTION, ["A100"], 2, {"procurement_team": 1}, 2_500_000),
        _activity("A300", "Site mobilization", ProjectPhase.CONSTRUCTION, ["A200"], 1, {"site_crew": 2}, 350_000),
        _activity("A400", "Foundations and substructure", ProjectPhase.CONSTRUCTION, ["A300"], 3, {"site_crew": 3, "crane": 1}, 5_000_000),
        _activity("A500", "Superstructure", ProjectPhase.CONSTRUCTION, ["A400"], 4, {"site_crew": 3, "crane": 1}, 8_500_000),
        _activity("A600", "MEP first fix and coordination", ProjectPhase.CONSTRUCTION, ["A500"], 3, {"site_crew": 2}, 5_500_000),
        _activity("A700", "Testing and commissioning", ProjectPhase.COMMISSIONING, ["A600"], 2, {"commissioning_team": 2, "inspector": 1}, 1_200_000),
        _activity("A800", "Handover and owner training", ProjectPhase.HANDOVER, ["A700"], 1, {"commissioning_team": 1}, 300_000),
    ]
    resources = [
        ProjectResource(resource_id="design_team", resource_type="professional_team", capacity=2, unit_cost_per_tick=15_000),
        ProjectResource(resource_id="procurement_team", resource_type="professional_team", capacity=1, unit_cost_per_tick=10_000),
        ProjectResource(resource_id="site_crew", resource_type="labor_crew", capacity=3, unit_cost_per_tick=35_000),
        ProjectResource(resource_id="crane", resource_type="equipment", capacity=1, unit_cost_per_tick=18_000),
        ProjectResource(resource_id="inspector", resource_type="quality", capacity=1, unit_cost_per_tick=8_000),
        ProjectResource(resource_id="commissioning_team", resource_type="professional_team", capacity=2, unit_cost_per_tick=12_000),
    ]
    initial_state = [
        ProjectStateValue(object_type="project", object_id=project_id, field_name="phase", value=ProjectPhase.DESIGN.value),
        ProjectStateValue(object_type="project", object_id=project_id, field_name="acceptance_status", value="NOT_ACCEPTED", namespace="handover"),
        ProjectStateValue(object_type="project", object_id=project_id, field_name="handoff_status", value="NOT_ISSUED", namespace="handover"),
        ProjectStateValue(object_type="project", object_id=project_id, field_name="safety_incidents", value=0, namespace="safety", source_ids=["osha-severe-injury"]),
        ProjectStateValue(object_type="design", object_id="D-001", field_name="status", value="SUBMITTED", namespace="design", source_ids=["gni-bim-2026"]),
        ProjectStateValue(object_type="design", object_id="D-001", field_name="revision", value="P01", namespace="design", source_ids=["gni-bim-2026"]),
    ]
    for activity in activities:
        initial_state.extend(
            [
                ProjectStateValue(object_type="activity", object_id=activity.activity_id, field_name="status", value="PLANNED", namespace="schedule"),
                ProjectStateValue(object_type="activity", object_id=activity.activity_id, field_name="blocked", value=False, namespace="schedule"),
                ProjectStateValue(object_type="activity", object_id=activity.activity_id, field_name="safety_hold", value=False, namespace="safety"),
            ]
        )

    evidence = [
        ProjectEvidenceRecord(evidence_id="EV-DESIGN-REVIEW", evidence_type="design_review", title="Federated BIM coordination review", text="Coordination review completed against the current architectural, structural and MEP federation.", namespace="design", authoritative=True, source_ids=["gni-bim-2026", "buildingsmart-official-samples", "ifc-bench-v1"]),
        ProjectEvidenceRecord(evidence_id="EV-PHASE-GATE", evidence_type="phase_gate", title="Project phase-gate checklist", text="Phase transition requires accepted deliverables, open-risk review and authority sign-off.", namespace="project", authoritative=True, source_ids=["yt-construction-management-2026-simplilearn", "yt-preconstruction-costs-sto"]),
        ProjectEvidenceRecord(evidence_id="EV-MITIGATION", evidence_type="mitigation_plan", title="Weather, logistics and safety mitigation plan", text="Resequence work, protect critical materials, validate access and release safety holds only after controls are verified.", namespace="safety", authoritative=True, source_ids=["osha-severe-injury", "noaa-ghcnh", "yt-preconstruction-costs-sto"]),
        ProjectEvidenceRecord(evidence_id="EV-INSPECTION", evidence_type="inspection_record", title="QA/QC inspection record", text="Inspection evidence records acceptance criteria, observed condition, nonconformities and disposition.", namespace="quality", authoritative=True, source_ids=["buildingsmart-official-samples"]),
        ProjectEvidenceRecord(evidence_id="EV-COMMISSION", evidence_type="commissioning_test", title="Commissioning functional test", text="Functional verification record for installed systems and handover readiness.", namespace="handover", authoritative=True, source_ids=["yt-construction-management-2026-simplilearn"]),
        ProjectEvidenceRecord(evidence_id="EV-HANDOVER", evidence_type="handover_package", title="Owner handover package", text="As-built information, commissioning evidence, training, warranties and outstanding-item status.", namespace="handover", authoritative=True, source_ids=["yt-construction-management-2026-simplilearn"]),
        ProjectEvidenceRecord(evidence_id="EV-PAYMENT", evidence_type="payment_evidence", title="Measured work and payment evidence", text="Certified quantities and approved commercial records supporting payment.", namespace="commercial", authoritative=True, source_ids=["usaspending-contracts", "yt-quantity-surveying-evolving-skills"]),
    ]

    hidden_events = [
        ProjectExogenousEvent(
            event_id="WX-HEAVY-RAIN",
            due_tick=4,
            label="Heavy rainfall makes excavation unsafe until mitigation is applied.",
            effects=[
                ProjectStateValue(object_type="activity", object_id="A400", field_name="blocked", value=True, namespace="schedule", source_ids=["noaa-ghcnh"]),
                ProjectStateValue(object_type="site", object_id=project_id, field_name="weather", value="HEAVY_RAIN", namespace="site", source_ids=["noaa-ghcnh"]),
            ],
        ),
        ProjectExogenousEvent(
            event_id="PROC-LONG-LEAD-DELAY",
            due_tick=9,
            label="A long-lead MEP package slips unless procurement is expedited or work is resequenced.",
            effects=[ProjectStateValue(object_type="activity", object_id="A600", field_name="blocked", value=True, namespace="schedule", source_ids=["usaspending-contracts"])],
        ),
        ProjectExogenousEvent(
            event_id="SAFE-WORK-HOLD",
            due_tick=12,
            label="A high-risk site condition triggers a temporary safety hold on superstructure work.",
            effects=[ProjectStateValue(object_type="activity", object_id="A500", field_name="safety_hold", value=True, namespace="safety", source_ids=["osha-severe-injury"])],
        ),
    ]

    outcomes = [
        ProjectOutcomeCondition(object_type="design", object_id="D-001", field_name="status", expected_value="APPROVED", dimension=VerificationDimension.REQUIREMENTS, weight=2.0, critical=True),
        *[
            ProjectOutcomeCondition(object_type="activity", object_id=item.activity_id, field_name="status", expected_value="COMPLETED", dimension=VerificationDimension.SCHEDULE, weight=2.0 if item.critical else 1.0, critical=item.critical)
            for item in activities
        ],
        ProjectOutcomeCondition(object_type="project", object_id=project_id, field_name="safety_incidents", operator=ConditionOperator.LTE, expected_value=0, dimension=VerificationDimension.SAFETY, weight=3.0, critical=True),
        ProjectOutcomeCondition(object_type="project", object_id=project_id, field_name="handoff_status", expected_value="ACCEPTED", dimension=VerificationDimension.HANDOVER, weight=2.0, critical=True),
        ProjectOutcomeCondition(object_type="project", object_id=project_id, field_name="acceptance_status", expected_value="ACCEPTED", dimension=VerificationDimension.HANDOVER, weight=3.0, critical=True),
    ]

    roles = construction_role_policies()
    task = ProjectTask(
        task_id=f"{project_id}-DELIVERY",
        world_id=f"WORLD-{project_id}",
        objective=(
            "Coordinate and deliver the project from approved design through procurement, construction, "
            "commissioning and owner acceptance while respecting authority, safety, resource, evidence, "
            "schedule and budget constraints."
        ),
        initial_phase=ProjectPhase.DESIGN,
        available_roles=[item.role for item in roles],
        role_policies=roles,
        action_policies=construction_action_policies(),
        max_actions=160,
        max_ticks=40,
        budget_limit=budget_limit,
        metadata={
            "environment_family": "OperationalProjectWorld",
            "domain_pack": "construction",
            "source_manifest_id": "construction-projectworld-public-corpus",
        },
    )
    oracle = ProjectOracle(
        task_id=task.task_id,
        outcome_conditions=outcomes,
        hidden_events=hidden_events,
        dimension_weights={
            VerificationDimension.REQUIREMENTS: 1.2,
            VerificationDimension.QUALITY: 1.2,
            VerificationDimension.SCHEDULE: 1.4,
            VerificationDimension.COST: 1.2,
            VerificationDimension.SAFETY: 1.6,
            VerificationDimension.COORDINATION: 1.1,
            VerificationDimension.AUTHORITY: 1.0,
            VerificationDimension.PROCESS: 1.0,
            VerificationDimension.EVIDENCE: 1.0,
            VerificationDimension.HANDOVER: 1.5,
        },
        maximum_rework_events=2,
    )
    manifest = construction_source_manifest()
    return OperationalProjectEpisode(
        episode_id=f"EP-{project_id}",
        world_id=task.world_id,
        domain="construction",
        task=task,
        initial_state=initial_state,
        activities=activities,
        resources=resources,
        evidence=evidence,
        oracle=oracle,
        metadata={
            "source_manifest": manifest.model_dump(mode="json"),
            "causal_chain": "design -> quantities -> work packages -> procurement -> resources -> schedule -> execution -> verification -> handover",
        },
    )


def fused_fields_to_project_state(fields: list[FusedSourceField]) -> list[ProjectStateValue]:
    """Materialize normalized source-fusion output as executable project-state facts."""
    return [
        ProjectStateValue(
            object_type=item.canonical_type.value,
            object_id=item.canonical_id,
            field_name=item.field_name,
            value=item.value,
            namespace=item.canonical_type.value,
            source_ids=[row["source_id"] for row in item.provenance if "source_id" in row],
        )
        for item in fields
    ]
