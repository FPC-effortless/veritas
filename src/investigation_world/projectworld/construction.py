from __future__ import annotations

from investigation_world.projectworld.models import (
    HiddenDefect,
    OperationalProjectWorldSpec,
    ProjectActionKind,
    ProjectDecisionOption,
    ProjectDecisionSpec,
    ProjectDomain,
    ProjectOracle,
    ProjectPhase,
    ProjectRequirement,
    ProjectResourceSpec,
    ProjectRoleSpec,
    ProjectScenario,
    ProjectWorkPackageSpec,
    ResourceKind,
)


def _role(
    role_id: str,
    label: str,
    actions: list[ProjectActionKind],
    *,
    managed: list[str] | None = None,
    visible: list[str] | None = None,
    view_all: bool = False,
    approval_limit: float | None = None,
) -> ProjectRoleSpec:
    return ProjectRoleSpec(
        role_id=role_id,
        label=label,
        allowed_actions=actions,
        managed_role_ids=list(managed or []),
        visible_role_ids=list(visible or []),
        can_view_all=view_all,
        approval_limit=approval_limit,
    )


def build_construction_project_world(seed: int = 42) -> ProjectScenario:
    """Build a deterministic design-to-handover mixed-use construction project."""

    common = [ProjectActionKind.ADVANCE_TIME]
    specialist = [ProjectActionKind.START_WORK, ProjectActionKind.RESOLVE_ISSUE, *common]
    roles = [
        _role(
            "project_director",
            "Project Director",
            list(ProjectActionKind),
            managed=[
                "architect",
                "structural_engineer",
                "mep_engineer",
                "project_manager",
                "procurement_manager",
                "site_manager",
                "commissioning_manager",
            ],
            view_all=True,
            approval_limit=100_000_000,
        ),
        _role(
            "project_manager",
            "Project Manager",
            [
                ProjectActionKind.START_WORK,
                ProjectActionKind.ADVANCE_TIME,
                ProjectActionKind.PROCURE,
                ProjectActionKind.RESOLVE_ISSUE,
            ],
            managed=["site_manager", "procurement_manager"],
            view_all=True,
        ),
        _role(
            "architect",
            "Architect",
            [ProjectActionKind.START_WORK, ProjectActionKind.CHOOSE_OPTION, *common],
            visible=["structural_engineer", "mep_engineer"],
        ),
        _role("structural_engineer", "Structural Engineer", specialist, visible=["architect"]),
        _role("mep_engineer", "MEP Engineer", specialist, visible=["architect"]),
        _role(
            "procurement_manager",
            "Procurement Manager",
            [ProjectActionKind.PROCURE, *common],
            visible=["site_manager", "project_manager"],
        ),
        _role(
            "site_manager",
            "Site Manager",
            specialist,
            visible=["project_manager", "procurement_manager"],
        ),
        _role(
            "quality_inspector",
            "Quality Inspector",
            [ProjectActionKind.INSPECT, *common],
            view_all=True,
        ),
        _role(
            "commissioning_manager",
            "Commissioning Manager",
            specialist,
            visible=["site_manager"],
        ),
        _role(
            "owner_representative",
            "Owner Representative",
            [ProjectActionKind.APPROVE, *common],
            view_all=True,
            approval_limit=100_000_000,
        ),
    ]

    resources = [
        ProjectResourceSpec(
            resource_id="site_labor",
            label="Site labor capacity",
            kind=ResourceKind.LABOR,
            unit="crew-days",
            initial_available=120,
            consumable=False,
        ),
        ProjectResourceSpec(
            resource_id="concrete",
            label="Ready-mix concrete",
            kind=ResourceKind.MATERIAL,
            unit="m3",
            unit_cost=155,
            procurement_lead_days=7,
        ),
        ProjectResourceSpec(
            resource_id="rebar",
            label="Reinforcing steel",
            kind=ResourceKind.MATERIAL,
            unit="tonnes",
            unit_cost=980,
            procurement_lead_days=14,
        ),
        ProjectResourceSpec(
            resource_id="structural_steel",
            label="Structural steel",
            kind=ResourceKind.MATERIAL,
            unit="tonnes",
            unit_cost=1650,
            procurement_lead_days=35,
        ),
        ProjectResourceSpec(
            resource_id="facade_units",
            label="Facade units",
            kind=ResourceKind.MATERIAL,
            unit="units",
            unit_cost=4200,
            procurement_lead_days=50,
        ),
        ProjectResourceSpec(
            resource_id="mep_equipment",
            label="MEP equipment packages",
            kind=ResourceKind.MATERIAL,
            unit="packages",
            unit_cost=180_000,
            procurement_lead_days=70,
        ),
    ]

    work_packages = [
        ProjectWorkPackageSpec(
            work_package_id="concept_design",
            name="Concept design and client brief reconciliation",
            phase=ProjectPhase.DESIGN,
            owner_role_id="architect",
            duration_days=12,
            direct_cost=180_000,
            deliverables=["approved_concept_design"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="structural_design",
            name="Structural design",
            phase=ProjectPhase.DESIGN,
            owner_role_id="structural_engineer",
            dependencies=["concept_design"],
            duration_days=18,
            direct_cost=240_000,
            deliverables=["structural_design_package"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="mep_design",
            name="MEP design",
            phase=ProjectPhase.DESIGN,
            owner_role_id="mep_engineer",
            dependencies=["concept_design"],
            duration_days=20,
            direct_cost=260_000,
            deliverables=["mep_design_package"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="design_coordination",
            name="Federated design coordination and clash closure",
            phase=ProjectPhase.DESIGN,
            owner_role_id="architect",
            dependencies=["structural_design", "mep_design"],
            duration_days=10,
            direct_cost=160_000,
            requires_approval=True,
            approval_role_ids=["owner_representative"],
            deliverables=["coordinated_design_release"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="permit_release",
            name="Permit and issued-for-construction release",
            phase=ProjectPhase.PLANNING,
            owner_role_id="project_manager",
            dependencies=["design_coordination"],
            duration_days=20,
            direct_cost=120_000,
            deliverables=["ifc_release"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="foundations",
            name="Foundations and substructure",
            phase=ProjectPhase.EXECUTION,
            owner_role_id="site_manager",
            dependencies=["permit_release"],
            duration_days=35,
            direct_cost=2_100_000,
            required_resources={"site_labor": 35, "concrete": 1800, "rebar": 190},
            requires_inspection=True,
            deliverables=["foundation_completion_record"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="superstructure",
            name="Primary superstructure",
            phase=ProjectPhase.EXECUTION,
            owner_role_id="site_manager",
            dependencies=["foundations"],
            duration_days=60,
            direct_cost=5_800_000,
            required_resources={"site_labor": 45, "concrete": 4200, "rebar": 520},
            requires_inspection=True,
            deliverables=["structure_completion_record"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="envelope",
            name="Building envelope",
            phase=ProjectPhase.EXECUTION,
            owner_role_id="site_manager",
            dependencies=["superstructure"],
            duration_days=48,
            direct_cost=3_900_000,
            required_resources={"site_labor": 28, "facade_units": 720},
            requires_inspection=True,
            deliverables=["weather_tight_certificate"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="mep_roughin",
            name="MEP first fix and major equipment installation",
            phase=ProjectPhase.EXECUTION,
            owner_role_id="site_manager",
            dependencies=["superstructure"],
            duration_days=52,
            direct_cost=3_400_000,
            required_resources={"site_labor": 32, "mep_equipment": 8},
            requires_inspection=True,
            deliverables=["mep_first_fix_record"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="interiors",
            name="Interior fit-out",
            phase=ProjectPhase.EXECUTION,
            owner_role_id="site_manager",
            dependencies=["envelope", "mep_roughin"],
            duration_days=50,
            direct_cost=4_200_000,
            required_resources={"site_labor": 40},
            requires_inspection=True,
            deliverables=["fitout_completion_record"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="commissioning",
            name="Integrated systems commissioning",
            phase=ProjectPhase.COMMISSIONING,
            owner_role_id="commissioning_manager",
            dependencies=["interiors"],
            duration_days=16,
            direct_cost=850_000,
            requires_inspection=True,
            requires_approval=True,
            approval_role_ids=["owner_representative"],
            deliverables=["commissioning_certificate"],
        ),
        ProjectWorkPackageSpec(
            work_package_id="handover",
            name="Client handover and closeout",
            phase=ProjectPhase.HANDOVER,
            owner_role_id="project_manager",
            dependencies=["commissioning"],
            duration_days=7,
            direct_cost=250_000,
            requires_approval=True,
            approval_role_ids=["owner_representative"],
            deliverables=["handover_package"],
        ),
    ]

    decisions = [
        ProjectDecisionSpec(
            decision_id="structural_system",
            name="Select primary structural system",
            owner_role_id="architect",
            required_before_work_packages=["structural_design", "foundations", "superstructure"],
            options=[
                ProjectDecisionOption(
                    option_id="reinforced_concrete",
                    label="Reinforced concrete frame",
                ),
                ProjectDecisionOption(
                    option_id="structural_steel",
                    label="Structural steel frame",
                    cost_delta_by_work_package={"superstructure": 1_350_000},
                    duration_delta_by_work_package={"superstructure": -16, "foundations": -4},
                    resource_requirements_by_work_package={
                        "superstructure": {"site_labor": 34, "structural_steel": 620},
                        "foundations": {"site_labor": 28, "concrete": 1350, "rebar": 145},
                    },
                ),
            ],
        ),
        ProjectDecisionSpec(
            decision_id="facade_system",
            name="Select facade delivery system",
            owner_role_id="architect",
            required_before_work_packages=["envelope"],
            options=[
                ProjectDecisionOption(
                    option_id="standard_unitized",
                    label="Standard unitized facade",
                ),
                ProjectDecisionOption(
                    option_id="accelerated_unitized",
                    label="Accelerated prefabricated unitized facade",
                    cost_delta_by_work_package={"envelope": 480_000},
                    duration_delta_by_work_package={"envelope": -12},
                    resource_requirements_by_work_package={
                        "envelope": {"site_labor": 22, "facade_units": 760}
                    },
                ),
            ],
        ),
    ]

    requirements = [
        ProjectRequirement(
            requirement_id="req-coordinated-design",
            description="Construction must proceed from a coordinated approved design release.",
            satisfied_by_work_packages=["design_coordination"],
        ),
        ProjectRequirement(
            requirement_id="req-structure",
            description="Primary structure must pass quality inspection.",
            satisfied_by_work_packages=["superstructure"],
        ),
        ProjectRequirement(
            requirement_id="req-weather-tight",
            description="Building envelope must be complete and inspected.",
            satisfied_by_work_packages=["envelope"],
        ),
        ProjectRequirement(
            requirement_id="req-commissioned",
            description="Building systems must be commissioned and owner-approved.",
            satisfied_by_work_packages=["commissioning"],
        ),
        ProjectRequirement(
            requirement_id="req-handover",
            description="The client must receive an approved handover package.",
            satisfied_by_work_packages=["handover"],
        ),
    ]

    spec = OperationalProjectWorldSpec(
        world_id=f"construction-project-{seed:06d}",
        project_id=f"BLDG-{seed:06d}",
        name="12-storey mixed-use development",
        domain=ProjectDomain.CONSTRUCTION,
        budget=38_000_000,
        deadline_days=420,
        roles=roles,
        resources=resources,
        work_packages=work_packages,
        requirements=requirements,
        decisions=decisions,
        metadata={
            "project_type": "mixed_use_building",
            "storeys": 12,
            "delivery_model": "design_bid_build",
            "currency": "USD",
            "simulation": "event_driven",
        },
    )

    defect_target = "mep_roughin" if seed % 2 == 0 else "envelope"
    oracle = ProjectOracle(
        work_package_delay_days={
            "permit_release": 6 + seed % 5,
        },
        resource_delay_days={
            "mep_equipment": 9 + seed % 8,
        },
        latent_defects={
            defect_target: HiddenDefect(
                issue_id=f"NCR-{seed:06d}",
                description=(
                    "Commissioning-critical installation defect requires verified rework "
                    "before acceptance."
                ),
                severity=0.8,
                rework_cost=180_000 + (seed % 4) * 25_000,
                rework_days=6 + seed % 5,
            )
        },
        metadata={"private_ground_truth": True},
    )
    return ProjectScenario(spec=spec, oracle=oracle, seed=seed)
