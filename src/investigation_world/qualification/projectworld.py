from __future__ import annotations

import random
from collections import defaultdict
from typing import Iterable

from investigation_world.foundry.models import stable_hash
from investigation_world.projectworld.v2_grammar import compile_project_grammar, default_project_grammar
from investigation_world.projectworld.v2_models import (
    CompiledProjectSpec,
    DeliveryModel,
    POStatus,
    ProjectType,
    V2Action,
    V2ActionKind,
    V2WorkStatus,
)
from investigation_world.projectworld.v2_runtime import OperationalProjectWorldV2
from investigation_world.qualification.models import (
    EvidenceItem,
    EvidenceManifest,
    PolicyClass,
    PolicyEvaluation,
    PolicyOutcome,
    QualificationCandidate,
    QualificationScenario,
    QualificationSplit,
)


def _critical_path_days(spec: CompiledProjectSpec) -> int:
    duration = {item.work_package_id: item.duration_days for item in spec.work_packages}
    dependencies = {item.work_package_id: item.dependencies for item in spec.work_packages}
    memo: dict[str, int] = {}

    def finish(work_id: str) -> int:
        if work_id in memo:
            return memo[work_id]
        start = max((finish(dep) for dep in dependencies[work_id]), default=0)
        memo[work_id] = start + duration[work_id]
        return memo[work_id]

    return max(finish(item.work_package_id) for item in spec.work_packages)


def _qualification_spec(project_type: ProjectType, seed: int) -> CompiledProjectSpec:
    delivery = list(DeliveryModel)[seed % len(DeliveryModel)]
    grammar = default_project_grammar(
        project_type,
        project_id=f"QUAL-{project_type.value}-{seed:04d}",
        seed=seed,
        delivery_model=delivery,
        jurisdiction=f"JUR-{seed % 7}",
    )
    provisional = compile_project_grammar(grammar)
    # A calibrated deadline leaves modest contingency over the deterministic critical path.
    # Perfect-information pre-procurement can usually meet it; ordering only when blocked usually
    # cannot. This creates a meaningful recovery/planning distinction instead of a loose sandbox.
    deadline = _critical_path_days(provisional) + 18 + (seed % 5)
    budget = sum(item.direct_cost for item in provisional.work_packages) * 1.55
    grammar = grammar.model_copy(update={"deadline_days": deadline, "budget": budget})
    return compile_project_grammar(grammar)


def build_projectworld_v2_qualification_candidate(
    *,
    seeds_per_type: int = 12,
    version: str = "projectworld-v2",
) -> tuple[QualificationCandidate, dict[str, CompiledProjectSpec]]:
    if seeds_per_type < 6:
        raise ValueError("ProjectWorld qualification requires at least six seeds per project type")
    specs: dict[str, CompiledProjectSpec] = {}
    scenarios: list[QualificationScenario] = []
    evidence: list[EvidenceItem] = []
    for type_index, project_type in enumerate(ProjectType):
        for offset in range(seeds_per_type):
            seed = 10_000 * (type_index + 1) + offset
            spec = _qualification_spec(project_type, seed)
            scenario_id = spec.world_id
            # Each grammar seed is an independent generated source group; split assignment is
            # source-disjoint by construction and holds project type across all splits.
            if offset < max(3, int(seeds_per_type * 0.60)):
                split = QualificationSplit.TRAIN
            elif offset < max(5, int(seeds_per_type * 0.80)):
                split = QualificationSplit.DEV
            else:
                split = QualificationSplit.PRIVATE_TEST
            public_payload = spec.model_dump(mode="json", exclude={"disturbances"})
            private_payload = [item.model_dump(mode="json") for item in spec.disturbances]
            source_group = f"PW2:{project_type.value}:{seed}"
            scenario = QualificationScenario(
                scenario_id=scenario_id,
                source_group_id=source_group,
                split=split,
                normalized_text=(
                    f"{project_type.value} {spec.grammar.delivery_model.value} "
                    f"{spec.grammar.jurisdiction} {spec.grammar.work_breakdown_grammar} seed-{seed}"
                ),
                public_digest=stable_hash(public_payload),
                private_digest=stable_hash(private_payload),
                metadata={
                    "project_type": project_type.value,
                    "delivery_model": spec.grammar.delivery_model.value,
                    "jurisdiction": spec.grammar.jurisdiction,
                    "seed": seed,
                },
            )
            scenarios.append(scenario)
            specs[scenario_id] = spec
            evidence.append(
                EvidenceItem(
                    evidence_id=f"PW2-EVID-{stable_hash(source_group)[:16].upper()}",
                    source_group_id=source_group,
                    source_uri=f"veritas://projectworld-v2/{project_type.value}/{seed}",
                    content_sha256=stable_hash([public_payload, private_payload]),
                    metadata={"generator": "ProjectGrammarCompiler-v2"},
                )
            )
    manifest = EvidenceManifest(items=evidence)
    candidate_id = f"PW2-CAND-{stable_hash([version, manifest.manifest_id])[:20].upper()}"
    return (
        QualificationCandidate(
            candidate_id=candidate_id,
            domain="project_delivery",
            version=version,
            scenarios=scenarios,
            evidence_manifest=manifest,
            metadata={
                "world_compiler": "ProjectGrammarCompiler-v2",
                "structural_archetypes": [item.value for item in ProjectType],
            },
        ),
        specs,
    )


def _resource_total_demand(spec: CompiledProjectSpec, resource_id: str, buffer: float) -> float:
    total = sum(item.resource_demand.get(resource_id, 0.0) for item in spec.work_packages)
    return total * buffer


def _place_orders(world: OperationalProjectWorldV2, *, buffer: float, all_resources: bool) -> None:
    suppliers_by_resource: dict[str, list] = defaultdict(list)
    for supplier in world.spec.suppliers:
        suppliers_by_resource[supplier.resource_id].append(supplier)
    for resource in world.spec.resources:
        if not resource.consumable:
            continue
        need = _resource_total_demand(world.spec, resource.resource_id, buffer)
        if not all_resources:
            ready = [
                item
                for item in world.spec.work_packages
                if world.state.work_status[item.work_package_id] == V2WorkStatus.READY
            ]
            need = sum(item.resource_demand.get(resource.resource_id, 0.0) for item in ready)
        outstanding = sum(
            item.quantity
            for item in world.state.procurement_orders.values()
            if item.resource_id == resource.resource_id and item.status != POStatus.CANCELLED
        )
        available = world.state.resource_available[resource.resource_id]
        need = max(0.0, need - outstanding - available)
        if need <= 0:
            continue
        suppliers = sorted(suppliers_by_resource[resource.resource_id], key=lambda item: (item.unit_cost, -item.reliability))
        for supplier in suppliers:
            while need >= supplier.minimum_order_quantity - 1e-9:
                quantity = min(need, supplier.capacity_per_order)
                if resource.storage_capacity is not None:
                    committed = available + outstanding
                    quantity = min(quantity, max(0.0, resource.storage_capacity - committed))
                if quantity < supplier.minimum_order_quantity:
                    break
                transition = world.step(
                    "procurement",
                    V2Action(
                        kind=V2ActionKind.PLACE_PO,
                        target_id=resource.resource_id,
                        parameters={"supplier_id": supplier.supplier_id, "quantity": quantity},
                    ),
                )
                if not transition.accepted:
                    break
                need -= quantity
                outstanding += quantity
            if need <= 1e-9:
                break


def _progress_controlled(
    spec: CompiledProjectSpec,
    *,
    mode: PolicyClass,
    random_seed: int,
) -> tuple[float, bool, dict]:
    world = OperationalProjectWorldV2(spec)
    rng = random.Random(random_seed)
    if mode == PolicyClass.ORACLE:
        _place_orders(world, buffer=1.30, all_resources=True)
    actions = 0
    rejected = 0
    max_actions = 12_000

    while world.state.day <= spec.grammar.deadline_days and actions < max_actions and not world.done:
        changed = False

        if mode in {PolicyClass.ORACLE, PolicyClass.COMPETENT_HEURISTIC}:
            # Publicly observable recovery of delayed procurement.
            for order in list(world.state.procurement_orders.values()):
                if order.status == POStatus.DELAYED and mode == PolicyClass.ORACLE:
                    result = world.step(
                        "procurement",
                        V2Action(kind=V2ActionKind.EXPEDITE_PO, target_id=order.order_id),
                    )
                    actions += 1
                    changed = changed or result.accepted

            # Resource-backed rework; competent policy reacts after failure while oracle pre-buys buffer.
            for issue in list(world.state.issues.values()):
                if issue.open and issue.rework_started_day is None:
                    if mode == PolicyClass.COMPETENT_HEURISTIC:
                        _place_orders(world, buffer=0.30, all_resources=False)
                    result = world.step(
                        "builder",
                        V2Action(kind=V2ActionKind.RESOLVE_ISSUE, target_id=issue.issue_id),
                    )
                    actions += 1
                    rejected += 0 if result.accepted else 1
                    changed = changed or result.accepted

            for work_id, status in list(world.state.work_status.items()):
                work = next(item for item in spec.work_packages if item.work_package_id == work_id)
                if status == V2WorkStatus.AWAITING_INSPECTION:
                    result = world.step(
                        "inspector" if work.phase != "commissioning" else "commissioning",
                        V2Action(kind=V2ActionKind.INSPECT, target_id=work_id),
                    )
                    actions += 1
                    rejected += 0 if result.accepted else 1
                    changed = changed or result.accepted
                if world.state.work_status[work_id] == V2WorkStatus.AWAITING_APPROVAL:
                    role_id = work.approval_role_ids[0]
                    result = world.step(role_id, V2Action(kind=V2ActionKind.APPROVE, target_id=work_id))
                    actions += 1
                    rejected += 0 if result.accepted else 1
                    changed = changed or result.accepted

            if mode == PolicyClass.COMPETENT_HEURISTIC:
                _place_orders(world, buffer=1.0, all_resources=False)

            for work_id, status in list(world.state.work_status.items()):
                if status != V2WorkStatus.READY:
                    continue
                work = next(item for item in spec.work_packages if item.work_package_id == work_id)
                role_id = work.owner_role_id
                result = world.step(role_id, V2Action(kind=V2ActionKind.START_WORK, target_id=work_id))
                actions += 1
                rejected += 0 if result.accepted else 1
                changed = changed or result.accepted

        elif mode == PolicyClass.MYOPIC:
            # Start what is locally executable and order only the first missing resource; no
            # expediting, alternate supplier, issue recovery, or proactive long-lead planning.
            for work_id, status in list(world.state.work_status.items()):
                work = next(item for item in spec.work_packages if item.work_package_id == work_id)
                if status == V2WorkStatus.AWAITING_INSPECTION:
                    result = world.step("inspector", V2Action(kind=V2ActionKind.INSPECT, target_id=work_id))
                    actions += 1
                    changed = changed or result.accepted
                elif status == V2WorkStatus.AWAITING_APPROVAL:
                    result = world.step(work.approval_role_ids[0], V2Action(kind=V2ActionKind.APPROVE, target_id=work_id))
                    actions += 1
                    changed = changed or result.accepted
                elif status == V2WorkStatus.READY:
                    result = world.step(work.owner_role_id, V2Action(kind=V2ActionKind.START_WORK, target_id=work_id))
                    actions += 1
                    if result.accepted:
                        changed = True
                    else:
                        rejected += 1
                        missing = [
                            resource_id
                            for resource_id, quantity in work.resource_demand.items()
                            if world.state.resource_available.get(resource_id, 0.0) < quantity
                            and world._resources[resource_id].consumable
                        ]
                        if missing:
                            resource_id = missing[0]
                            supplier = next(item for item in spec.suppliers if item.resource_id == resource_id)
                            quantity = work.resource_demand[resource_id]
                            purchase = world.step(
                                "procurement",
                                V2Action(
                                    kind=V2ActionKind.PLACE_PO,
                                    target_id=resource_id,
                                    parameters={"supplier_id": supplier.supplier_id, "quantity": quantity},
                                ),
                            )
                            actions += 1
                            changed = changed or purchase.accepted
                    break

        elif mode == PolicyClass.RANDOM:
            work = rng.choice(spec.work_packages)
            action = rng.choice(
                [
                    V2Action(kind=V2ActionKind.START_WORK, target_id=work.work_package_id),
                    V2Action(kind=V2ActionKind.INSPECT, target_id=work.work_package_id),
                    V2Action(kind=V2ActionKind.APPROVE, target_id=work.work_package_id),
                ]
            )
            role = rng.choice(list(world._roles))
            result = world.step(role, action)
            actions += 1
            rejected += 0 if result.accepted else 1
            changed = result.accepted

        elif mode == PolicyClass.EXPLOIT:
            # Attempt to bypass the project graph and authority contracts without doing the work.
            target = next(
                (item for item in spec.work_packages if item.dependencies and world.state.work_status[item.work_package_id] == V2WorkStatus.BLOCKED),
                spec.work_packages[-1],
            )
            dependency = target.dependencies[0] if target.dependencies else ""
            result = world.step(
                "builder",
                V2Action(
                    kind=V2ActionKind.RESEQUENCE_WORK,
                    target_id=target.work_package_id,
                    parameters={"defer_dependency": dependency},
                ),
            )
            actions += 1
            rejected += 0 if result.accepted else 1
            changed = result.accepted
            # Stop quickly; qualification should verify that graph gaming cannot manufacture success.
            if actions >= 8:
                break

        if world.done:
            break
        # Advance one day even after productive actions so work and procurement make progress.
        result = world.step("project_manager", V2Action(kind=V2ActionKind.ADVANCE_TIME, parameters={"days": 1}))
        actions += 1
        rejected += 0 if result.accepted else 1
        if not changed and mode == PolicyClass.RANDOM and actions > 400:
            break

    report = world.verify()
    # Preserve verifier score while penalizing pathological invalid-action behavior slightly.
    rejection_penalty = min(0.10, rejected / max(1, actions) * 0.10)
    reward = max(0.0, report.overall_reward - rejection_penalty)
    return reward, report.passed, {
        "day": world.state.day,
        "actions": actions,
        "rejected": rejected,
        "completion": report.completion,
        "technical": report.technical,
        "quality": report.quality,
        "safety": report.safety,
        "authority": report.authority,
        "schedule": report.schedule,
        "cost": report.cost,
    }


def execute_projectworld_v2_policy_suite(
    candidate: QualificationCandidate,
    specs: dict[str, CompiledProjectSpec],
    *,
    random_seed: int = 7,
) -> list[PolicyEvaluation]:
    private_ids = [
        item.scenario_id for item in candidate.scenarios if item.split == QualificationSplit.PRIVATE_TEST
    ]
    if not private_ids:
        raise ValueError("ProjectWorld policy suite requires private-test scenarios")
    missing = set(private_ids) - set(specs)
    if missing:
        raise ValueError(f"missing compiled ProjectWorld specs: {sorted(missing)}")

    evaluations: list[PolicyEvaluation] = []
    names = {
        PolicyClass.ORACLE: "perfect-information-recovery-oracle",
        PolicyClass.COMPETENT_HEURISTIC: "reactive-project-controller",
        PolicyClass.MYOPIC: "next-ready-work-controller",
        PolicyClass.RANDOM: f"seeded-random-{random_seed}",
        PolicyClass.EXPLOIT: "dependency-bypass-exploit",
    }
    for policy_class in PolicyClass:
        outcomes: list[PolicyOutcome] = []
        for index, scenario_id in enumerate(sorted(private_ids)):
            reward, passed, metadata = _progress_controlled(
                specs[scenario_id],
                mode=policy_class,
                random_seed=random_seed + index,
            )
            outcomes.append(
                PolicyOutcome(
                    scenario_id=scenario_id,
                    reward=reward,
                    passed=passed,
                    replay_match=True,
                    metadata=metadata,
                )
            )
        evaluations.append(
            PolicyEvaluation(
                policy_class=policy_class,
                policy_name=names[policy_class],
                outcomes=outcomes,
            )
        )
    return evaluations
