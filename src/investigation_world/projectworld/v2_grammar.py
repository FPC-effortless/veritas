from __future__ import annotations

import random

from investigation_world.foundry.models import stable_hash
from investigation_world.projectworld.v2_models import (
    ApprovalGateSpec,
    CompiledProjectSpec,
    ContractModel,
    DeliveryModel,
    DisturbanceKind,
    DisturbanceSpec,
    OutcomeContract,
    OutcomeDimension,
    ProjectGrammarSpec,
    ProjectType,
    RiskSpec,
    SupplierSpec,
    V2ActionKind,
    V2ContractSpec,
    V2ResourceSpec,
    V2RoleSpec,
    V2WorkPackageSpec,
)


_ALL_ACTIONS = list(V2ActionKind)


def _default_roles() -> list[V2RoleSpec]:
    return [
        V2RoleSpec(
            role_id="project_manager",
            label="Project Manager",
            allowed_actions=_ALL_ACTIONS,
            managed_role_ids=["designer", "builder", "procurement", "commissioning"],
            can_view_all=True,
            approval_limit=20_000_000,
        ),
        V2RoleSpec(
            role_id="designer",
            label="Design Lead",
            allowed_actions=[V2ActionKind.START_WORK, V2ActionKind.ADVANCE_TIME, V2ActionKind.RESEQUENCE_WORK],
            visible_role_ids=["builder"],
        ),
        V2RoleSpec(
            role_id="builder",
            label="Construction Lead",
            allowed_actions=[
                V2ActionKind.START_WORK,
                V2ActionKind.ADVANCE_TIME,
                V2ActionKind.ADD_CREW,
                V2ActionKind.AUTHORIZE_OVERTIME,
                V2ActionKind.RESOLVE_ISSUE,
                V2ActionKind.RESEQUENCE_WORK,
            ],
            visible_role_ids=["designer", "commissioning"],
        ),
        V2RoleSpec(
            role_id="procurement",
            label="Procurement Manager",
            allowed_actions=[
                V2ActionKind.PLACE_PO,
                V2ActionKind.EXPEDITE_PO,
                V2ActionKind.SUBSTITUTE_SUPPLIER,
                V2ActionKind.ADVANCE_TIME,
            ],
            visible_role_ids=["builder"],
            approval_limit=5_000_000,
        ),
        V2RoleSpec(
            role_id="inspector",
            label="Independent Inspector",
            allowed_actions=[V2ActionKind.INSPECT, V2ActionKind.ADVANCE_TIME],
            visible_role_ids=["builder", "commissioning"],
        ),
        V2RoleSpec(
            role_id="authority",
            label="Authority Having Jurisdiction",
            allowed_actions=[V2ActionKind.APPROVE, V2ActionKind.ADVANCE_TIME],
            visible_role_ids=["designer", "commissioning"],
            approval_limit=100_000_000,
        ),
        V2RoleSpec(
            role_id="commissioning",
            label="Commissioning Authority",
            allowed_actions=[
                V2ActionKind.START_WORK,
                V2ActionKind.INSPECT,
                V2ActionKind.ADVANCE_TIME,
                V2ActionKind.RESOLVE_ISSUE,
            ],
            visible_role_ids=["builder"],
        ),
    ]


def _default_resources(project_type: ProjectType) -> list[V2ResourceSpec]:
    resources = [
        V2ResourceSpec(resource_id="design_capacity", label="Design capacity", unit="team-day", initial_available=1000, consumable=False),
        V2ResourceSpec(resource_id="site_labor", label="Site labor", unit="crew", initial_available=20, consumable=False),
        V2ResourceSpec(resource_id="concrete", label="Concrete", unit="m3", initial_available=0, storage_capacity=2500),
        V2ResourceSpec(resource_id="structural_material", label="Structural material", unit="tonne", initial_available=0, storage_capacity=1500),
        V2ResourceSpec(resource_id="mep_equipment", label="MEP equipment", unit="lot", initial_available=0, storage_capacity=50),
        V2ResourceSpec(resource_id="commissioning_capacity", label="Commissioning capacity", unit="team", initial_available=4, consumable=False),
    ]
    specialized = {
        ProjectType.DATA_CENTER: [
            V2ResourceSpec(resource_id="electrical_gear", label="MV/LV electrical gear", unit="lot", storage_capacity=20),
            V2ResourceSpec(resource_id="generator_sets", label="Generator sets", unit="set", storage_capacity=8),
            V2ResourceSpec(resource_id="ups_modules", label="UPS modules", unit="module", storage_capacity=32),
            V2ResourceSpec(resource_id="cooling_units", label="Cooling units", unit="unit", storage_capacity=24),
        ],
        ProjectType.HOSPITAL: [
            V2ResourceSpec(resource_id="medical_gas_equipment", label="Medical gas equipment", unit="lot", storage_capacity=12),
            V2ResourceSpec(resource_id="clinical_equipment", label="Clinical equipment", unit="lot", storage_capacity=30),
            V2ResourceSpec(resource_id="infection_control_units", label="Infection-control HVAC", unit="unit", storage_capacity=24),
        ],
        ProjectType.LABORATORY: [
            V2ResourceSpec(resource_id="containment_equipment", label="Containment equipment", unit="lot", storage_capacity=12),
            V2ResourceSpec(resource_id="specialty_gas_equipment", label="Specialty gas equipment", unit="lot", storage_capacity=12),
            V2ResourceSpec(resource_id="vibration_isolators", label="Vibration isolators", unit="unit", storage_capacity=100),
        ],
        ProjectType.EDUCATION: [
            V2ResourceSpec(resource_id="ict_equipment", label="ICT equipment", unit="lot", storage_capacity=20),
            V2ResourceSpec(resource_id="sports_equipment", label="Sports equipment", unit="lot", storage_capacity=20),
        ],
        ProjectType.COMMERCIAL: [],
    }
    return [*resources, *specialized[project_type]]


def _default_suppliers(resources: list[V2ResourceSpec]) -> list[SupplierSpec]:
    suppliers: list[SupplierSpec] = []
    for index, resource in enumerate(resources):
        if not resource.consumable:
            continue
        suppliers.extend(
            [
                SupplierSpec(
                    supplier_id=f"{resource.resource_id}-primary",
                    resource_id=resource.resource_id,
                    capacity_per_order=max(10, (resource.storage_capacity or 100) * 0.8),
                    minimum_order_quantity=1,
                    lead_days=7 + (index % 5) * 7,
                    unit_cost=1000 + index * 250,
                    reliability=0.92,
                    expedite_days=5,
                    expedite_premium_pct=15,
                ),
                SupplierSpec(
                    supplier_id=f"{resource.resource_id}-alternate",
                    resource_id=resource.resource_id,
                    capacity_per_order=max(8, (resource.storage_capacity or 100) * 0.6),
                    minimum_order_quantity=1,
                    lead_days=10 + (index % 4) * 5,
                    unit_cost=1100 + index * 275,
                    reliability=0.97,
                    expedite_days=3,
                    expedite_premium_pct=20,
                ),
            ]
        )
    return suppliers


def _wp(
    work_id: str,
    name: str,
    phase: str,
    owner: str,
    duration: int,
    deps: list[str],
    demand: dict[str, float] | None = None,
    *,
    cost: float = 100_000,
    inspect: bool = False,
    approve: bool = False,
    approvers: list[str] | None = None,
    deliverables: list[str] | None = None,
    tags: list[str] | None = None,
    safety: bool = False,
) -> V2WorkPackageSpec:
    return V2WorkPackageSpec(
        work_package_id=work_id,
        name=name,
        phase=phase,
        owner_role_id=owner,
        dependencies=deps,
        duration_days=duration,
        direct_cost=cost,
        resource_demand=demand or {},
        requires_inspection=inspect,
        requires_approval=approve,
        approval_role_ids=approvers or [],
        deliverables=deliverables or [f"{work_id}_deliverable"],
        technical_tags=tags or [],
        safety_critical=safety,
    )


def _base_work() -> list[V2WorkPackageSpec]:
    return [
        _wp("concept_design", "Concept and basis of design", "design", "designer", 20, [], {"design_capacity": 1}, cost=200_000, deliverables=["basis_of_design"]),
        _wp("authority_submission", "Planning and authority submission", "design", "designer", 15, ["concept_design"], {"design_capacity": 1}, cost=100_000, approve=True, approvers=["authority"], deliverables=["planning_approval"]),
        _wp("site_mobilization", "Site mobilization", "execution", "builder", 10, ["authority_submission"], {"site_labor": 4}, cost=250_000, safety=True),
        _wp("foundations", "Foundations", "execution", "builder", 25, ["site_mobilization"], {"site_labor": 8, "concrete": 600}, cost=1_000_000, inspect=True, safety=True, tags=["structure"]),
    ]


def _type_work(project_type: ProjectType) -> list[V2WorkPackageSpec]:
    if project_type == ProjectType.DATA_CENTER:
        return [
            _wp("superstructure", "Data hall superstructure", "execution", "builder", 35, ["foundations"], {"site_labor": 10, "structural_material": 450}, cost=2_000_000, inspect=True, tags=["structure"]),
            _wp("utility_interconnect", "Utility interconnect", "execution", "builder", 30, ["foundations"], {"site_labor": 5, "electrical_gear": 2}, cost=2_500_000, approve=True, approvers=["authority"], safety=True, tags=["electrical"]),
            _wp("electrical_rooms", "MV/LV electrical rooms", "execution", "builder", 28, ["superstructure"], {"site_labor": 6, "electrical_gear": 6}, cost=3_000_000, inspect=True, safety=True, tags=["electrical"]),
            _wp("generator_plant", "Generator plant", "execution", "builder", 24, ["electrical_rooms"], {"site_labor": 5, "generator_sets": 4}, cost=4_000_000, inspect=True, safety=True, tags=["backup_power"]),
            _wp("ups_switchgear", "UPS and switchgear", "execution", "builder", 24, ["electrical_rooms"], {"site_labor": 5, "ups_modules": 12}, cost=4_500_000, inspect=True, safety=True, tags=["critical_power"]),
            _wp("cooling_plant", "Cooling plant", "execution", "builder", 30, ["superstructure"], {"site_labor": 6, "cooling_units": 8}, cost=3_500_000, inspect=True, tags=["cooling"]),
            _wp("network_rooms", "Network and meet-me rooms", "execution", "builder", 18, ["superstructure"], {"site_labor": 4, "mep_equipment": 4}, cost=1_500_000, inspect=True, tags=["network"]),
            _wp("integrated_systems_test", "Integrated systems test", "commissioning", "commissioning", 14, ["generator_plant", "ups_switchgear", "cooling_plant", "network_rooms", "utility_interconnect"], {"commissioning_capacity": 2}, cost=800_000, inspect=True, tags=["commissioning"]),
            _wp("redundancy_test", "N+1 redundancy test", "commissioning", "commissioning", 7, ["integrated_systems_test"], {"commissioning_capacity": 2}, cost=400_000, inspect=True, approve=True, approvers=["authority"], deliverables=["redundancy_certificate"]),
            _wp("handover", "Data center handover", "handover", "project_manager", 5, ["redundancy_test"], {}, cost=100_000, deliverables=["handover_package"]),
        ]
    if project_type == ProjectType.HOSPITAL:
        return [
            _wp("superstructure", "Hospital superstructure", "execution", "builder", 45, ["foundations"], {"site_labor": 12, "structural_material": 500}, cost=3_000_000, inspect=True, tags=["structure"]),
            _wp("envelope", "Clinical envelope", "execution", "builder", 30, ["superstructure"], {"site_labor": 8, "structural_material": 100}, cost=1_500_000, inspect=True, tags=["weather_tight"]),
            _wp("medical_gas", "Medical gas systems", "execution", "builder", 25, ["envelope"], {"site_labor": 5, "medical_gas_equipment": 4}, cost=2_000_000, inspect=True, safety=True, tags=["medical_gas"]),
            _wp("infection_control_hvac", "Infection-control HVAC", "execution", "builder", 32, ["envelope"], {"site_labor": 6, "infection_control_units": 10}, cost=3_500_000, inspect=True, safety=True, tags=["infection_control"]),
            _wp("emergency_power", "Emergency power", "execution", "builder", 24, ["envelope"], {"site_labor": 5, "mep_equipment": 6}, cost=2_500_000, inspect=True, safety=True, tags=["life_safety"]),
            _wp("clinical_equipment", "Clinical equipment installation", "execution", "builder", 28, ["medical_gas", "infection_control_hvac"], {"site_labor": 4, "clinical_equipment": 12}, cost=4_000_000, inspect=True, tags=["clinical"]),
            _wp("life_safety", "Life-safety validation", "commissioning", "commissioning", 12, ["emergency_power", "clinical_equipment"], {"commissioning_capacity": 2}, cost=600_000, inspect=True, safety=True, tags=["life_safety"]),
            _wp("regulatory_survey", "Health authority survey", "commissioning", "authority", 10, ["life_safety"], {}, cost=250_000, approve=True, approvers=["authority"], deliverables=["occupancy_license"]),
            _wp("handover", "Hospital handover", "handover", "project_manager", 7, ["regulatory_survey"], {}, cost=150_000, deliverables=["handover_package"]),
        ]
    if project_type == ProjectType.LABORATORY:
        return [
            _wp("vibration_foundation", "Vibration-controlled foundation", "execution", "builder", 30, ["foundations"], {"site_labor": 8, "vibration_isolators": 40}, cost=1_800_000, inspect=True, tags=["vibration"]),
            _wp("containment_envelope", "Containment envelope", "execution", "builder", 28, ["vibration_foundation"], {"site_labor": 7, "containment_equipment": 4}, cost=2_200_000, inspect=True, safety=True, tags=["containment"]),
            _wp("lab_hvac", "Laboratory pressure-control HVAC", "execution", "builder", 30, ["containment_envelope"], {"site_labor": 6, "mep_equipment": 8}, cost=2_800_000, inspect=True, safety=True, tags=["pressure_cascade"]),
            _wp("specialty_gases", "Specialty gas distribution", "execution", "builder", 20, ["containment_envelope"], {"site_labor": 4, "specialty_gas_equipment": 5}, cost=1_700_000, inspect=True, safety=True, tags=["specialty_gas"]),
            _wp("process_utilities", "Process water and utilities", "execution", "builder", 18, ["containment_envelope"], {"site_labor": 4, "mep_equipment": 4}, cost=1_200_000, inspect=True),
            _wp("containment_commissioning", "Containment commissioning", "commissioning", "commissioning", 12, ["lab_hvac", "specialty_gases", "process_utilities"], {"commissioning_capacity": 2}, cost=600_000, inspect=True, safety=True, tags=["containment"]),
            _wp("certification", "Laboratory certification", "commissioning", "authority", 8, ["containment_commissioning"], {}, cost=250_000, approve=True, approvers=["authority"], deliverables=["lab_certificate"]),
            _wp("handover", "Laboratory handover", "handover", "project_manager", 5, ["certification"], {}, cost=100_000, deliverables=["handover_package"]),
        ]
    if project_type == ProjectType.EDUCATION:
        return [
            _wp("superstructure", "Education building structure", "execution", "builder", 35, ["foundations"], {"site_labor": 10, "structural_material": 350}, cost=2_000_000, inspect=True),
            _wp("classroom_fitout", "Classroom fit-out", "execution", "builder", 28, ["superstructure"], {"site_labor": 8, "mep_equipment": 5}, cost=1_800_000, inspect=True),
            _wp("auditorium", "Auditorium systems", "execution", "builder", 22, ["superstructure"], {"site_labor": 5, "mep_equipment": 3}, cost=1_000_000, inspect=True),
            _wp("sports_facilities", "Sports facilities", "execution", "builder", 25, ["superstructure"], {"site_labor": 5, "sports_equipment": 5}, cost=900_000, inspect=True),
            _wp("ict", "Campus ICT", "execution", "builder", 18, ["classroom_fitout"], {"site_labor": 3, "ict_equipment": 6}, cost=800_000, inspect=True),
            _wp("life_safety", "Fire and life-safety validation", "commissioning", "commissioning", 10, ["classroom_fitout", "auditorium", "sports_facilities"], {"commissioning_capacity": 1}, cost=300_000, inspect=True, safety=True),
            _wp("occupancy", "Occupancy approval", "commissioning", "authority", 7, ["ict", "life_safety"], {}, cost=150_000, approve=True, approvers=["authority"], deliverables=["occupancy_certificate"]),
            _wp("handover", "Education facility handover", "handover", "project_manager", 5, ["occupancy"], {}, cost=100_000, deliverables=["handover_package"]),
        ]
    return [
        _wp("superstructure", "Commercial superstructure", "execution", "builder", 35, ["foundations"], {"site_labor": 10, "structural_material": 400}, cost=2_000_000, inspect=True),
        _wp("envelope", "Building envelope", "execution", "builder", 25, ["superstructure"], {"site_labor": 6, "structural_material": 80}, cost=1_200_000, inspect=True),
        _wp("mep_roughin", "MEP rough-in", "execution", "builder", 28, ["envelope"], {"site_labor": 6, "mep_equipment": 6}, cost=1_800_000, inspect=True),
        _wp("interiors", "Interior fit-out", "execution", "builder", 30, ["mep_roughin"], {"site_labor": 8}, cost=1_500_000, inspect=True),
        _wp("commissioning", "Building commissioning", "commissioning", "commissioning", 12, ["interiors"], {"commissioning_capacity": 1}, cost=400_000, inspect=True),
        _wp("occupancy", "Occupancy approval", "commissioning", "authority", 7, ["commissioning"], {}, cost=150_000, approve=True, approvers=["authority"], deliverables=["occupancy_certificate"]),
        _wp("handover", "Commercial handover", "handover", "project_manager", 5, ["occupancy"], {}, cost=100_000, deliverables=["handover_package"]),
    ]


def _default_outcomes(work: list[V2WorkPackageSpec]) -> list[OutcomeContract]:
    ids = [item.work_package_id for item in work]
    safety_ids = [item.work_package_id for item in work if item.safety_critical]
    technical_deliverables = [deliverable for item in work for deliverable in item.deliverables]
    approval_ids = [item.work_package_id for item in work if item.requires_approval]
    inspection_ids = [item.work_package_id for item in work if item.requires_inspection]
    return [
        OutcomeContract(contract_id="technical_completion", dimension=OutcomeDimension.TECHNICAL, description="All specified technical deliverables complete", work_package_ids=ids, required_deliverables=technical_deliverables, hard=True),
        OutcomeContract(contract_id="quality_acceptance", dimension=OutcomeDimension.QUALITY, description="Inspection-required work accepted without open rework", work_package_ids=inspection_ids, hard=True),
        OutcomeContract(contract_id="safety_acceptance", dimension=OutcomeDimension.SAFETY, description="Safety-critical packages complete without unresolved safety issues", work_package_ids=safety_ids, hard=True),
        OutcomeContract(contract_id="authority_acceptance", dimension=OutcomeDimension.AUTHORITY, description="Authority-gated packages carry valid approvals", work_package_ids=approval_ids, hard=True),
    ]


def _default_contracts(delivery_model: DeliveryModel, work: list[V2WorkPackageSpec]) -> list[V2ContractSpec]:
    model = {
        DeliveryModel.DESIGN_BID_BUILD: ContractModel.LUMP_SUM,
        DeliveryModel.DESIGN_BUILD: ContractModel.GMP,
        DeliveryModel.CM_AT_RISK: ContractModel.GMP,
        DeliveryModel.EPC: ContractModel.LUMP_SUM,
    }[delivery_model]
    design = [item.work_package_id for item in work if item.phase == "design"]
    field = [item.work_package_id for item in work if item.phase != "design"]
    return [
        V2ContractSpec(contract_id="design_contract", counterparty_id="designer", model=ContractModel.COST_PLUS if delivery_model == DeliveryModel.CM_AT_RISK else model, work_package_ids=design),
        V2ContractSpec(contract_id="delivery_contract", counterparty_id="builder", model=model, work_package_ids=field, retainage_pct=5.0),
    ]


def _default_disturbances(project_type: ProjectType, seed: int, suppliers: list[SupplierSpec], work: list[V2WorkPackageSpec]) -> list[DisturbanceSpec]:
    rng = random.Random(seed)
    disturbances: list[DisturbanceSpec] = []
    consumable_suppliers = [item for item in suppliers if item.lead_days > 0]
    if consumable_suppliers:
        supplier = rng.choice(consumable_suppliers)
        disturbances.append(DisturbanceSpec(disturbance_id="D-SUPPLY-1", day=30 + rng.randrange(20), kind=DisturbanceKind.RESOURCE_DELAY, target_id=supplier.resource_id, parameters={"delay_days": 10 + rng.randrange(10)}))
    defect_candidates = [item for item in work if item.requires_inspection]
    if defect_candidates:
        defect = rng.choice(defect_candidates)
        disturbances.append(DisturbanceSpec(disturbance_id="D-DEFECT-1", day=60 + rng.randrange(30), kind=DisturbanceKind.DEFECT, target_id=defect.work_package_id, parameters={"severity": 0.6, "rework_days": 5, "rework_cost": 100_000}))
    if project_type in {ProjectType.COMMERCIAL, ProjectType.EDUCATION, ProjectType.HOSPITAL}:
        disturbances.append(DisturbanceSpec(disturbance_id="D-WEATHER-1", day=45, kind=DisturbanceKind.WEATHER_STOP, target_id="site", parameters={"duration_days": 3}))
    return disturbances


def default_project_grammar(
    project_type: ProjectType,
    *,
    project_id: str,
    seed: int = 42,
    delivery_model: DeliveryModel = DeliveryModel.DESIGN_BUILD,
    jurisdiction: str = "generic-jurisdiction",
) -> ProjectGrammarSpec:
    resources = _default_resources(project_type)
    suppliers = _default_suppliers(resources)
    return ProjectGrammarSpec(
        project_id=project_id,
        project_type=project_type,
        delivery_model=delivery_model,
        jurisdiction=jurisdiction,
        site_conditions={"access": "constrained" if seed % 3 == 0 else "normal", "ground": "variable" if seed % 5 == 0 else "normal"},
        building_systems=[project_type.value],
        stakeholder_graph=_default_roles(),
        resource_network=resources,
        supplier_network=suppliers,
        work_breakdown_grammar=f"{project_type.value}-v2",
        budget=50_000_000,
        deadline_days=420,
        seed=seed,
    )


def compile_project_grammar(grammar: ProjectGrammarSpec) -> CompiledProjectSpec:
    roles = list(grammar.stakeholder_graph) or _default_roles()
    resources = list(grammar.resource_network) or _default_resources(grammar.project_type)
    suppliers = list(grammar.supplier_network) or _default_suppliers(resources)
    work = [*_base_work(), *_type_work(grammar.project_type)]
    contracts = list(grammar.contract_structure) or _default_contracts(grammar.delivery_model, work)
    outcomes = list(grammar.requirement_graph) or _default_outcomes(work)
    approvals = list(grammar.approval_graph) or [
        ApprovalGateSpec(
            gate_id=f"GATE-{item.work_package_id}",
            work_package_id=item.work_package_id,
            authorized_role_ids=item.approval_role_ids,
        )
        for item in work
        if item.requires_approval
    ]
    risks = list(grammar.risk_model) or [
        RiskSpec(risk_id="risk-long-lead", target_id=suppliers[-1].resource_id if suppliers else "site", probability=0.25, cost_impact=250_000, schedule_impact_days=14, mitigation_action=V2ActionKind.EXPEDITE_PO),
        RiskSpec(risk_id="risk-rework", target_id="foundations", probability=0.15, cost_impact=150_000, schedule_impact_days=7, mitigation_action=V2ActionKind.ADD_CREW),
    ]
    disturbances = list(grammar.disturbance_process) or _default_disturbances(grammar.project_type, grammar.seed, suppliers, work)
    world_id = f"PW2-{stable_hash([grammar.model_dump(mode='json'), [item.model_dump(mode='json') for item in work]])[:20].upper()}"
    return CompiledProjectSpec(
        world_id=world_id,
        grammar=grammar,
        roles=roles,
        resources=resources,
        suppliers=suppliers,
        work_packages=work,
        contracts=contracts,
        approval_gates=approvals,
        risks=risks,
        outcome_contracts=outcomes,
        disturbances=disturbances,
    )
