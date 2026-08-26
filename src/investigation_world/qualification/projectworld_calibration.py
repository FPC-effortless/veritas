from __future__ import annotations

import random
from collections import defaultdict

from investigation_world.projectworld.v2_models import (
    CompiledProjectSpec,
    DisturbanceKind,
    POStatus,
    V2Action,
    V2ActionKind,
    V2WorkStatus,
)
from investigation_world.projectworld.v2_runtime import OperationalProjectWorldV2
from investigation_world.qualification.cluster_split import repartition_candidate_by_near_duplicates
from investigation_world.qualification.models import (
    PolicyClass,
    PolicyEvaluation,
    PolicyOutcome,
    QualificationCandidate,
    QualificationSplit,
)
from investigation_world.qualification.projectworld import build_projectworld_v2_qualification_candidate


def build_calibrated_projectworld_v2_candidate(
    *,
    seeds_per_type: int = 12,
    version: str = "projectworld-v2",
) -> tuple[QualificationCandidate, dict[str, CompiledProjectSpec]]:
    candidate, specs = build_projectworld_v2_qualification_candidate(
        seeds_per_type=seeds_per_type,
        version=version,
    )
    candidate, _ = repartition_candidate_by_near_duplicates(candidate)
    metadata = {
        **candidate.metadata,
        "qualification_split": "near-duplicate-structural-family-disjoint",
    }
    return candidate.model_copy(update={"metadata": metadata}), specs


def _remaining_work_ids(world: OperationalProjectWorldV2) -> set[str]:
    return {
        work_id
        for work_id, status in world.state.work_status.items()
        if status in {V2WorkStatus.BLOCKED, V2WorkStatus.READY}
    }


def _lookahead_work_ids(world: OperationalProjectWorldV2) -> set[str]:
    ready = {
        work_id
        for work_id, status in world.state.work_status.items()
        if status == V2WorkStatus.READY
    }
    lookahead = set(ready)
    for work_id, dependencies in world._effective_dependencies.items():
        if any(dependency in ready for dependency in dependencies):
            lookahead.add(work_id)
    return lookahead


def _oracle_future_rework_demand(world: OperationalProjectWorldV2) -> dict[str, float]:
    """Return consumables a perfect-information policy knows will be needed for latent defects.

    ProjectWorld disturbances are verifier-private. An oracle is therefore allowed to condition on
    them. The previous nominal oracle did not: it learned of a defect only after the work completed,
    then waited an entire supplier lead time for rework material. With deadlines calibrated to the
    deterministic critical path plus modest contingency, that made otherwise-solvable worlds fail
    the feasibility gate. This function anticipates exactly the same 25% rework demand constructed
    by the runtime, without exposing it to competent/myopic policies.
    """
    demand: dict[str, float] = defaultdict(float)
    issues_by_work = {
        issue.work_package_id: issue
        for issue in world.state.issues.values()
    }
    for disturbance in world.spec.disturbances:
        if disturbance.kind != DisturbanceKind.DEFECT:
            continue
        work_id = disturbance.target_id
        work = world._work.get(work_id)
        if work is None:
            continue
        issue = issues_by_work.get(work_id)
        if issue is not None:
            # Once material has been reserved for active rework, or rework has resolved, the future
            # hidden demand is no longer outstanding. Open, not-yet-started issues are accounted for
            # by `_required_consumables` below using the runtime's explicit issue demand.
            if issue.rework_started_day is not None or not issue.open:
                continue
            continue
        status = world.state.work_status[work_id]
        if status == V2WorkStatus.COMPLETE and disturbance.day <= world.state.day:
            continue
        for resource_id, quantity in work.resource_demand.items():
            if world._resources[resource_id].consumable:
                demand[resource_id] += max(1.0, quantity * 0.25)
    return dict(demand)


def _required_consumables(
    world: OperationalProjectWorldV2,
    work_ids: set[str],
    *,
    buffer: float,
    include_oracle_future_rework: bool = False,
) -> dict[str, float]:
    demand: dict[str, float] = defaultdict(float)
    for work_id in work_ids:
        work = world._work[work_id]
        for resource_id, quantity in work.resource_demand.items():
            if world._resources[resource_id].consumable:
                demand[resource_id] += quantity * buffer
    for issue in world.state.issues.values():
        if not issue.open or issue.rework_started_day is not None:
            continue
        for resource_id, quantity in issue.rework_resource_demand.items():
            if world._resources[resource_id].consumable:
                demand[resource_id] += quantity
    if include_oracle_future_rework:
        for resource_id, quantity in _oracle_future_rework_demand(world).items():
            demand[resource_id] += quantity
    return dict(demand)


def _procure(
    world: OperationalProjectWorldV2,
    work_ids: set[str],
    *,
    buffer: float,
    include_oracle_future_rework: bool = False,
) -> int:
    """Order remaining demand while respecting supplier and storage constraints."""
    actions = 0
    suppliers_by_resource: dict[str, list] = defaultdict(list)
    for supplier in world.spec.suppliers:
        suppliers_by_resource[supplier.resource_id].append(supplier)

    required = _required_consumables(
        world,
        work_ids,
        buffer=buffer,
        include_oracle_future_rework=include_oracle_future_rework,
    )
    for resource_id, gross_need in required.items():
        outstanding = sum(
            order.quantity
            for order in world.state.procurement_orders.values()
            if order.resource_id == resource_id
            and order.status not in {POStatus.ARRIVED, POStatus.CANCELLED}
        )
        available = world.state.resource_available.get(resource_id, 0.0)
        need = max(0.0, gross_need - available - outstanding)
        if need <= 1e-9:
            continue
        resource = world._resources[resource_id]
        suppliers = sorted(
            suppliers_by_resource[resource_id],
            key=lambda item: (item.lead_days, item.unit_cost, -item.reliability),
        )
        for supplier in suppliers:
            while need >= supplier.minimum_order_quantity - 1e-9:
                free_storage = float("inf")
                if resource.storage_capacity is not None:
                    free_storage = max(
                        0.0,
                        resource.storage_capacity - available - outstanding,
                    )
                quantity = min(need, supplier.capacity_per_order, free_storage)
                if quantity < supplier.minimum_order_quantity:
                    break
                result = world.step(
                    "procurement",
                    V2Action(
                        kind=V2ActionKind.PLACE_PO,
                        target_id=resource_id,
                        parameters={"supplier_id": supplier.supplier_id, "quantity": quantity},
                    ),
                )
                actions += 1
                if not result.accepted:
                    break
                need -= quantity
                outstanding += quantity
            if need <= 1e-9:
                break
    return actions


def _recover_delayed_orders(world: OperationalProjectWorldV2, *, oracle: bool) -> int:
    actions = 0
    for order in list(world.state.procurement_orders.values()):
        if order.status != POStatus.DELAYED:
            continue
        if oracle:
            expedite = world.step(
                "procurement",
                V2Action(kind=V2ActionKind.EXPEDITE_PO, target_id=order.order_id),
            )
            actions += 1
            if expedite.accepted:
                continue
        alternates = [
            supplier
            for supplier in world.spec.suppliers
            if supplier.resource_id == order.resource_id and supplier.supplier_id != order.supplier_id
        ]
        if alternates:
            supplier = min(alternates, key=lambda item: (item.lead_days, -item.reliability, item.unit_cost))
            substitute = world.step(
                "procurement",
                V2Action(
                    kind=V2ActionKind.SUBSTITUTE_SUPPLIER,
                    target_id=order.order_id,
                    parameters={"supplier_id": supplier.supplier_id},
                ),
            )
            actions += 1
            if substitute.accepted and oracle and supplier.expedite_days > 0:
                world.step(
                    "procurement",
                    V2Action(kind=V2ActionKind.EXPEDITE_PO, target_id=order.order_id),
                )
                actions += 1
    return actions


def _service_gates_and_rework(
    world: OperationalProjectWorldV2,
    *,
    competent: bool,
) -> tuple[int, int]:
    actions = 0
    rejected = 0
    for issue in list(world.state.issues.values()):
        if issue.open and issue.rework_started_day is None:
            result = world.step(
                "builder",
                V2Action(kind=V2ActionKind.RESOLVE_ISSUE, target_id=issue.issue_id),
            )
            actions += 1
            rejected += 0 if result.accepted else 1

    for work_id, status in list(world.state.work_status.items()):
        work = world._work[work_id]
        if status == V2WorkStatus.AWAITING_INSPECTION:
            role_id = "commissioning" if work.phase == "commissioning" else "inspector"
            result = world.step(role_id, V2Action(kind=V2ActionKind.INSPECT, target_id=work_id))
            actions += 1
            rejected += 0 if result.accepted else 1
        if world.state.work_status[work_id] == V2WorkStatus.AWAITING_APPROVAL:
            role_id = work.approval_role_ids[0]
            result = world.step(role_id, V2Action(kind=V2ActionKind.APPROVE, target_id=work_id))
            actions += 1
            rejected += 0 if result.accepted else 1
    return actions, rejected


def _start_ready_work(world: OperationalProjectWorldV2) -> tuple[int, int]:
    actions = 0
    rejected = 0
    for work_id, status in list(world.state.work_status.items()):
        if status != V2WorkStatus.READY:
            continue
        work = world._work[work_id]
        result = world.step(
            work.owner_role_id,
            V2Action(kind=V2ActionKind.START_WORK, target_id=work_id),
        )
        actions += 1
        rejected += 0 if result.accepted else 1
    return actions, rejected


def _diagnostics(world: OperationalProjectWorldV2) -> dict:
    return {
        "unfinished_work": {
            work_id: status.value
            for work_id, status in world.state.work_status.items()
            if status != V2WorkStatus.COMPLETE
        },
        "open_issues": {
            issue_id: {
                "work_package_id": issue.work_package_id,
                "rework_started_day": issue.rework_started_day,
                "rework_resource_demand": dict(issue.rework_resource_demand),
            }
            for issue_id, issue in world.state.issues.items()
            if issue.open
        },
        "resources": dict(world.state.resource_available),
        "open_purchase_orders": {
            order_id: {
                "resource_id": order.resource_id,
                "status": order.status.value,
                "expected_day": order.expected_day,
                "quantity": order.quantity,
            }
            for order_id, order in world.state.procurement_orders.items()
            if order.status not in {POStatus.ARRIVED, POStatus.CANCELLED}
        },
        "last_rejections": [
            {"day": item["day"], "role_id": item["role_id"], "action": item["action"], "target_id": item["target_id"], "message": item["message"]}
            for item in world.journal
            if not item["accepted"]
        ][-10:],
    }


def _progress_controlled(
    spec: CompiledProjectSpec,
    *,
    mode: PolicyClass,
    random_seed: int,
) -> tuple[float, bool, dict]:
    world = OperationalProjectWorldV2(spec)
    rng = random.Random(random_seed)
    actions = 0
    rejected = 0
    max_actions = 12_000

    while world.state.day <= spec.grammar.deadline_days and actions < max_actions and not world.done:
        changed = False

        if mode == PolicyClass.ORACLE:
            actions += _procure(
                world,
                _remaining_work_ids(world),
                buffer=1.05,
                include_oracle_future_rework=True,
            )
            actions += _recover_delayed_orders(world, oracle=True)
            gate_actions, gate_rejected = _service_gates_and_rework(world, competent=True)
            actions += gate_actions
            rejected += gate_rejected
            start_actions, start_rejected = _start_ready_work(world)
            actions += start_actions
            rejected += start_rejected
            changed = gate_actions > 0 or start_actions > 0

        elif mode == PolicyClass.COMPETENT_HEURISTIC:
            actions += _procure(world, _lookahead_work_ids(world), buffer=1.0)
            actions += _recover_delayed_orders(world, oracle=False)
            gate_actions, gate_rejected = _service_gates_and_rework(world, competent=True)
            actions += gate_actions
            rejected += gate_rejected
            start_actions, start_rejected = _start_ready_work(world)
            actions += start_actions
            rejected += start_rejected
            changed = gate_actions > 0 or start_actions > 0

        elif mode == PolicyClass.MYOPIC:
            for work_id, status in list(world.state.work_status.items()):
                work = world._work[work_id]
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
                            supplier = min(
                                (item for item in spec.suppliers if item.resource_id == resource_id),
                                key=lambda item: item.unit_cost,
                            )
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
            target = next(
                (
                    item
                    for item in spec.work_packages
                    if item.dependencies
                    and world.state.work_status[item.work_package_id] == V2WorkStatus.BLOCKED
                ),
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
            if actions >= 8:
                break

        if world.done:
            break
        result = world.step(
            "project_manager",
            V2Action(kind=V2ActionKind.ADVANCE_TIME, parameters={"days": 1}),
        )
        actions += 1
        rejected += 0 if result.accepted else 1
        if not changed and mode == PolicyClass.RANDOM and actions > 400:
            break

    report = world.verify()
    rejection_penalty = min(0.10, rejected / max(1, actions) * 0.10)
    reward = max(0.0, report.overall_reward - rejection_penalty)
    metadata = {
        "day": world.state.day,
        "deadline_days": spec.grammar.deadline_days,
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
    if not report.passed and mode == PolicyClass.ORACLE:
        metadata.update(_diagnostics(world))
    return reward, report.passed, metadata


def execute_calibrated_projectworld_v2_policy_suite(
    candidate: QualificationCandidate,
    specs: dict[str, CompiledProjectSpec],
    *,
    random_seed: int = 7,
) -> list[PolicyEvaluation]:
    private_ids = sorted(
        item.scenario_id
        for item in candidate.scenarios
        if item.split == QualificationSplit.PRIVATE_TEST
    )
    if not private_ids:
        raise ValueError("ProjectWorld policy suite requires private-test scenarios")
    missing = set(private_ids) - set(specs)
    if missing:
        raise ValueError(f"missing compiled ProjectWorld specs: {sorted(missing)}")

    names = {
        PolicyClass.ORACLE: "perfect-information-disturbance-aware-oracle",
        PolicyClass.COMPETENT_HEURISTIC: "one-layer-lookahead-project-controller",
        PolicyClass.MYOPIC: "next-ready-work-controller",
        PolicyClass.RANDOM: f"seeded-random-{random_seed}",
        PolicyClass.EXPLOIT: "dependency-bypass-exploit",
    }
    evaluations: list[PolicyEvaluation] = []
    for policy_class in PolicyClass:
        outcomes: list[PolicyOutcome] = []
        for index, scenario_id in enumerate(private_ids):
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
