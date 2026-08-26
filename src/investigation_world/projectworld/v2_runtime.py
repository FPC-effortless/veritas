from __future__ import annotations

from copy import deepcopy
from typing import Any

from investigation_world.projectworld.v2_models import (
    CompiledProjectSpec,
    DisturbanceKind,
    POStatus,
    V2Action,
    V2ActionKind,
    V2Issue,
    V2Observation,
    V2OutcomeReport,
    V2ProcurementOrder,
    V2ProjectState,
    V2Transition,
    V2WorkStatus,
)


class ProjectWorldV2Error(ValueError):
    pass


class OperationalProjectWorldV2:
    """Identity-bound, event-driven project runtime with explicit recovery controls."""

    def __init__(self, spec: CompiledProjectSpec):
        self.spec = spec
        self._roles = {item.role_id: item for item in spec.roles}
        self._resources = {item.resource_id: item for item in spec.resources}
        self._suppliers = {item.supplier_id: item for item in spec.suppliers}
        self._work = {item.work_package_id: item for item in spec.work_packages}
        self._effective_dependencies = {
            item.work_package_id: list(item.dependencies) for item in spec.work_packages
        }
        self._reserved: dict[str, dict[str, float]] = {}
        self._rework_remaining: dict[str, int] = {}
        self._pending_defects: dict[str, dict[str, Any]] = {}
        self._approval_block_until: dict[str, int] = {}
        self._weather_stop_until = -1
        self._overtime_once: set[str] = set()
        self._journal: list[dict[str, Any]] = []
        self._po_counter = 0
        self._issue_counter = 0
        status = {
            item.work_package_id: (
                V2WorkStatus.READY if not item.dependencies else V2WorkStatus.BLOCKED
            )
            for item in spec.work_packages
        }
        self.state = V2ProjectState(
            work_status=status,
            work_remaining_days={item.work_package_id: item.duration_days for item in spec.work_packages},
            resource_available={item.resource_id: item.initial_available for item in spec.resources},
        )
        self._refresh_readiness()

    def bind(self, role_id: str) -> "ProjectWorldV2Session":
        self._role(role_id)
        return ProjectWorldV2Session(self, role_id)

    def _role(self, role_id: str):
        try:
            return self._roles[role_id]
        except KeyError as exc:
            raise ProjectWorldV2Error(f"unknown role: {role_id}") from exc

    def _authorize(self, role_id: str, action: V2Action) -> None:
        role = self._role(role_id)
        if action.kind not in role.allowed_actions:
            self.state.authority_violations += 1
            raise ProjectWorldV2Error(f"role {role_id} cannot perform {action.kind.value}")

    def _can_act_for(self, actor: str, owner: str) -> bool:
        role = self._role(actor)
        return actor == owner or owner in role.managed_role_ids

    def _refresh_readiness(self) -> None:
        for work_id, work in self._work.items():
            status = self.state.work_status[work_id]
            if status not in {V2WorkStatus.BLOCKED, V2WorkStatus.READY}:
                continue
            deps = self._effective_dependencies[work_id]
            ready = all(self.state.work_status[item] == V2WorkStatus.COMPLETE for item in deps)
            self.state.work_status[work_id] = V2WorkStatus.READY if ready else V2WorkStatus.BLOCKED

    def _potential(self) -> float:
        complete = sum(value == V2WorkStatus.COMPLETE for value in self.state.work_status.values())
        completion = complete / max(1, len(self.state.work_status))
        open_issues = sum(item.open for item in self.state.issues.values())
        cost_penalty = max(0.0, self.state.cost_spent - self.spec.grammar.budget) / self.spec.grammar.budget
        schedule_penalty = max(0, self.state.day - self.spec.grammar.deadline_days) / self.spec.grammar.deadline_days
        return completion - 0.05 * open_issues - 0.25 * cost_penalty - 0.25 * schedule_penalty

    def _resource_needed(self, role_id: str) -> set[str]:
        role = self._role(role_id)
        if role.can_view_all or role_id == "procurement":
            return set(self._resources)
        visible_roles = {role_id, *role.visible_role_ids, *role.managed_role_ids}
        return {
            resource_id
            for work in self.spec.work_packages
            if work.owner_role_id in visible_roles
            for resource_id in work.resource_demand
        }

    def observe(self, role_id: str) -> V2Observation:
        role = self._role(role_id)
        visible_roles = {role_id, *role.visible_role_ids, *role.managed_role_ids}
        visible_work = [
            work
            for work in self.spec.work_packages
            if role.can_view_all or work.owner_role_id in visible_roles
        ]
        resource_ids = self._resource_needed(role_id)
        po_visible = role.can_view_all or role_id == "procurement"
        if po_visible:
            orders = list(self.state.procurement_orders.values())
        else:
            orders = [
                order
                for order in self.state.procurement_orders.values()
                if order.resource_id in resource_ids
            ]
        visible_work_ids = {item.work_package_id for item in visible_work}
        issues = [
            issue
            for issue in self.state.issues.values()
            if role.can_view_all or issue.work_package_id in visible_work_ids
        ]
        return V2Observation(
            world_id=self.spec.world_id,
            project_id=self.spec.grammar.project_id,
            role_id=role_id,
            day=self.state.day,
            budget=self.spec.grammar.budget,
            cost_spent=self.state.cost_spent,
            deadline_days=self.spec.grammar.deadline_days,
            work_packages=[
                {
                    "work_package_id": item.work_package_id,
                    "name": item.name,
                    "phase": item.phase,
                    "owner_role_id": item.owner_role_id,
                    "dependencies": list(self._effective_dependencies[item.work_package_id]),
                    "status": self.state.work_status[item.work_package_id].value,
                    "remaining_days": self.state.work_remaining_days[item.work_package_id],
                    "resource_demand": dict(item.resource_demand),
                    "requires_inspection": item.requires_inspection,
                    "requires_approval": item.requires_approval,
                    "deliverables": list(item.deliverables),
                }
                for item in visible_work
            ],
            resources={key: self.state.resource_available[key] for key in sorted(resource_ids)},
            procurement_orders=[item.model_dump(mode="json") for item in orders],
            issues=[item.model_dump(mode="json") for item in issues if item.open],
            approvals=dict(self.state.approvals),
            disturbances=list(self.state.disturbance_log[-20:]),
        )

    def _reserve_resources(self, work_id: str, demand: dict[str, float]) -> None:
        for resource_id, quantity in demand.items():
            if self.state.resource_available.get(resource_id, 0.0) < quantity:
                raise ProjectWorldV2Error(
                    f"insufficient {resource_id}: need {quantity}, have {self.state.resource_available.get(resource_id, 0.0)}"
                )
        reserved: dict[str, float] = {}
        for resource_id, quantity in demand.items():
            self.state.resource_available[resource_id] -= quantity
            if not self._resources[resource_id].consumable:
                reserved[resource_id] = quantity
        if reserved:
            self._reserved[work_id] = reserved

    def _release_nonconsumable(self, work_id: str) -> None:
        for resource_id, quantity in self._reserved.pop(work_id, {}).items():
            self.state.resource_available[resource_id] += quantity

    def _mark_complete(self, work_id: str) -> None:
        self.state.work_status[work_id] = V2WorkStatus.COMPLETE
        self._release_nonconsumable(work_id)
        for deliverable in self._work[work_id].deliverables:
            if deliverable not in self.state.completed_deliverables:
                self.state.completed_deliverables.append(deliverable)
        self._refresh_readiness()

    def _finish_execution(self, work_id: str) -> None:
        work = self._work[work_id]
        if any(issue.open and issue.work_package_id == work_id for issue in self.state.issues.values()):
            self.state.work_status[work_id] = V2WorkStatus.REWORK_REQUIRED
            return
        if work_id in self._pending_defects:
            defect = self._pending_defects.pop(work_id)
            self._issue_counter += 1
            issue_id = f"ISSUE-{self._issue_counter:05d}"
            demand = {
                key: max(1.0, value * 0.25)
                for key, value in work.resource_demand.items()
            }
            self.state.issues[issue_id] = V2Issue(
                issue_id=issue_id,
                work_package_id=work_id,
                severity=float(defect.get("severity", 0.5)),
                description=str(defect.get("description", "latent quality defect")),
                rework_days=int(defect.get("rework_days", 3)),
                rework_cost=float(defect.get("rework_cost", 50_000)),
                rework_resource_demand=demand,
            )
            self.state.work_status[work_id] = V2WorkStatus.REWORK_REQUIRED
            return
        if work.requires_inspection:
            self.state.work_status[work_id] = V2WorkStatus.AWAITING_INSPECTION
        elif work.requires_approval:
            self.state.work_status[work_id] = V2WorkStatus.AWAITING_APPROVAL
        else:
            self._mark_complete(work_id)

    def _start_work(self, role_id: str, action: V2Action) -> str:
        work_id = action.target_id or ""
        if work_id not in self._work:
            raise ProjectWorldV2Error("start_work requires a valid work package")
        work = self._work[work_id]
        if not self._can_act_for(role_id, work.owner_role_id):
            self.state.authority_violations += 1
            raise ProjectWorldV2Error(f"role {role_id} cannot act for {work.owner_role_id}")
        if self.state.work_status[work_id] != V2WorkStatus.READY:
            raise ProjectWorldV2Error(f"work package {work_id} is not ready")
        self._reserve_resources(work_id, work.resource_demand)
        self.state.work_status[work_id] = V2WorkStatus.IN_PROGRESS
        self.state.work_started_day[work_id] = self.state.day
        self.state.cost_spent += work.direct_cost
        return f"started {work_id}"

    def _place_po(self, role_id: str, action: V2Action) -> str:
        resource_id = action.target_id or ""
        if resource_id not in self._resources:
            raise ProjectWorldV2Error("place_po requires a valid resource target")
        supplier_id = str(action.parameters.get("supplier_id", ""))
        quantity = float(action.parameters.get("quantity", 0.0))
        supplier = self._suppliers.get(supplier_id)
        if supplier is None or supplier.resource_id != resource_id:
            raise ProjectWorldV2Error("supplier does not supply requested resource")
        if quantity < supplier.minimum_order_quantity or quantity > supplier.capacity_per_order:
            raise ProjectWorldV2Error("purchase quantity violates supplier MOQ/capacity")
        resource = self._resources[resource_id]
        outstanding = sum(
            order.quantity
            for order in self.state.procurement_orders.values()
            if order.resource_id == resource_id and order.status != POStatus.CANCELLED
        )
        if resource.storage_capacity is not None and self.state.resource_available[resource_id] + outstanding + quantity > resource.storage_capacity:
            raise ProjectWorldV2Error("purchase would exceed storage capacity")
        value = quantity * supplier.unit_cost
        role = self._role(role_id)
        if role.approval_limit is not None and value > role.approval_limit:
            self.state.authority_violations += 1
            raise ProjectWorldV2Error("purchase exceeds actor approval authority")
        self._po_counter += 1
        order_id = f"PO-{self._po_counter:05d}"
        self.state.procurement_orders[order_id] = V2ProcurementOrder(
            order_id=order_id,
            resource_id=resource_id,
            supplier_id=supplier_id,
            quantity=quantity,
            ordered_day=self.state.day,
            expected_day=self.state.day + supplier.lead_days,
            unit_cost=supplier.unit_cost,
        )
        self.state.cost_spent += value
        return f"placed {order_id}"

    def _expedite_po(self, action: V2Action) -> str:
        order_id = action.target_id or ""
        order = self.state.procurement_orders.get(order_id)
        if order is None or order.status in {POStatus.ARRIVED, POStatus.CANCELLED}:
            raise ProjectWorldV2Error("expedite_po requires an open purchase order")
        supplier = self._suppliers[order.supplier_id]
        if supplier.expedite_days <= 0:
            raise ProjectWorldV2Error("supplier offers no expedite option")
        original = order.expected_day
        order.expected_day = max(self.state.day + 1, order.expected_day - supplier.expedite_days)
        premium = order.quantity * order.unit_cost * supplier.expedite_premium_pct / 100.0
        order.expedite_premium += premium
        self.state.cost_spent += premium
        return f"expedited {order_id} from day {original} to {order.expected_day}"

    def _substitute_supplier(self, action: V2Action) -> str:
        order_id = action.target_id or ""
        order = self.state.procurement_orders.get(order_id)
        if order is None or order.status == POStatus.ARRIVED:
            raise ProjectWorldV2Error("supplier substitution requires an open purchase order")
        new_supplier_id = str(action.parameters.get("supplier_id", ""))
        supplier = self._suppliers.get(new_supplier_id)
        if supplier is None or supplier.resource_id != order.resource_id:
            raise ProjectWorldV2Error("alternate supplier does not supply purchase-order resource")
        if order.quantity > supplier.capacity_per_order:
            raise ProjectWorldV2Error("alternate supplier lacks order capacity")
        old_value = order.quantity * order.unit_cost
        new_value = order.quantity * supplier.unit_cost
        if new_value > old_value:
            self.state.cost_spent += new_value - old_value
        order.supplier_id = supplier.supplier_id
        order.unit_cost = supplier.unit_cost
        order.expected_day = self.state.day + supplier.lead_days
        order.status = POStatus.ORDERED
        order.acknowledged_day = None
        order.shipped_day = None
        return f"substituted supplier on {order_id}"

    def _add_crew(self, action: V2Action) -> str:
        resource_id = action.target_id or "site_labor"
        resource = self._resources.get(resource_id)
        if resource is None or resource.consumable:
            raise ProjectWorldV2Error("add_crew requires a reusable capacity resource")
        quantity = float(action.parameters.get("quantity", 1.0))
        if quantity <= 0:
            raise ProjectWorldV2Error("crew quantity must be positive")
        self.state.resource_available[resource_id] += quantity
        self.state.cost_spent += quantity * float(action.parameters.get("mobilization_cost", 10_000.0))
        return f"added {quantity} {resource_id}"

    def _authorize_overtime(self, action: V2Action) -> str:
        work_id = action.target_id or ""
        if self.state.work_status.get(work_id) != V2WorkStatus.IN_PROGRESS:
            raise ProjectWorldV2Error("overtime requires an in-progress work package")
        self._overtime_once.add(work_id)
        self.state.overtime_authorized.append(work_id)
        self.state.cost_spent += self._work[work_id].direct_cost * 0.05
        return f"authorized overtime for {work_id}"

    def _inspect(self, role_id: str, action: V2Action) -> str:
        work_id = action.target_id or ""
        if self.state.work_status.get(work_id) != V2WorkStatus.AWAITING_INSPECTION:
            raise ProjectWorldV2Error("inspect requires work awaiting inspection")
        if role_id not in {"inspector", "commissioning", "project_manager"}:
            self.state.authority_violations += 1
            raise ProjectWorldV2Error("role is not an authorized inspector")
        if any(issue.open and issue.work_package_id == work_id for issue in self.state.issues.values()):
            self.state.work_status[work_id] = V2WorkStatus.REWORK_REQUIRED
            raise ProjectWorldV2Error("inspection failed due to open issue")
        if work_id not in self.state.inspection_passed:
            self.state.inspection_passed.append(work_id)
        if self._work[work_id].requires_approval:
            self.state.work_status[work_id] = V2WorkStatus.AWAITING_APPROVAL
        else:
            self._mark_complete(work_id)
        return f"inspection passed for {work_id}"

    def _approve(self, role_id: str, action: V2Action) -> str:
        work_id = action.target_id or ""
        work = self._work.get(work_id)
        if work is None or self.state.work_status.get(work_id) != V2WorkStatus.AWAITING_APPROVAL:
            raise ProjectWorldV2Error("approve requires work awaiting approval")
        if role_id not in work.approval_role_ids:
            self.state.authority_violations += 1
            raise ProjectWorldV2Error("role is not authorized for this approval")
        if self.state.day < self._approval_block_until.get(work_id, -1):
            raise ProjectWorldV2Error("approval authority response is delayed")
        gate = next((item for item in self.spec.approval_gates if item.work_package_id == work_id), None)
        role = self._role(role_id)
        if gate and gate.max_value is not None and work.direct_cost > gate.max_value:
            self.state.authority_violations += 1
            raise ProjectWorldV2Error("approval exceeds gate value")
        if role.approval_limit is not None and work.direct_cost > role.approval_limit:
            self.state.authority_violations += 1
            raise ProjectWorldV2Error("approval exceeds role authority")
        self.state.approvals[work_id] = role_id
        self._mark_complete(work_id)
        return f"approved {work_id}"

    def _resolve_issue(self, action: V2Action) -> str:
        issue_id = action.target_id or ""
        issue = self.state.issues.get(issue_id)
        if issue is None or not issue.open:
            raise ProjectWorldV2Error("resolve_issue requires an open issue")
        if issue.rework_started_day is not None:
            raise ProjectWorldV2Error("rework already in progress")
        self._reserve_resources(f"rework:{issue_id}", issue.rework_resource_demand)
        issue.rework_started_day = self.state.day
        self._rework_remaining[issue_id] = issue.rework_days
        self.state.cost_spent += issue.rework_cost
        self.state.work_status[issue.work_package_id] = V2WorkStatus.IN_PROGRESS
        return f"started resource-backed rework {issue_id}"

    def _resequence(self, action: V2Action) -> str:
        work_id = action.target_id or ""
        dependency = str(action.parameters.get("defer_dependency", ""))
        if work_id not in self._work or dependency not in self._effective_dependencies.get(work_id, []):
            raise ProjectWorldV2Error("resequence requires an existing dependency")
        if self.state.work_status.get(dependency) == V2WorkStatus.COMPLETE:
            raise ProjectWorldV2Error("completed dependency does not need resequencing")
        if self._work[work_id].phase != self._work[dependency].phase:
            raise ProjectWorldV2Error("cannot bypass a cross-phase dependency")
        self._effective_dependencies[work_id].remove(dependency)
        self.state.cost_spent += float(action.parameters.get("coordination_cost", 25_000.0))
        self._refresh_readiness()
        return f"resequence accepted for {work_id}"

    def _apply_disturbance(self, disturbance) -> None:
        if disturbance.kind == DisturbanceKind.RESOURCE_DELAY:
            delay = int(disturbance.parameters.get("delay_days", 7))
            for order in self.state.procurement_orders.values():
                if order.resource_id == disturbance.target_id and order.status not in {POStatus.ARRIVED, POStatus.CANCELLED}:
                    order.expected_day += delay
                    order.status = POStatus.DELAYED
        elif disturbance.kind == DisturbanceKind.SUPPLIER_FAILURE:
            for order in self.state.procurement_orders.values():
                if order.supplier_id == disturbance.target_id and order.status not in {POStatus.ARRIVED, POStatus.CANCELLED}:
                    order.expected_day += int(disturbance.parameters.get("delay_days", 30))
                    order.status = POStatus.DELAYED
        elif disturbance.kind == DisturbanceKind.DEFECT:
            self._pending_defects[disturbance.target_id] = dict(disturbance.parameters)
        elif disturbance.kind == DisturbanceKind.WEATHER_STOP:
            self._weather_stop_until = max(
                self._weather_stop_until,
                self.state.day + int(disturbance.parameters.get("duration_days", 1)),
            )
        elif disturbance.kind == DisturbanceKind.APPROVAL_DELAY:
            self._approval_block_until[disturbance.target_id] = self.state.day + int(
                disturbance.parameters.get("duration_days", 7)
            )
        self.state.disturbance_log.append(
            f"day {self.state.day}: {disturbance.kind.value}:{disturbance.target_id}"
        )

    def _advance_one_day(self) -> None:
        self.state.day += 1
        for disturbance in self.spec.disturbances:
            if disturbance.day == self.state.day:
                self._apply_disturbance(disturbance)

        for order in self.state.procurement_orders.values():
            if order.status == POStatus.ORDERED and self.state.day >= order.ordered_day + 1:
                order.status = POStatus.ACKNOWLEDGED
                order.acknowledged_day = self.state.day
            supplier = self._suppliers[order.supplier_id]
            ship_day = max(order.ordered_day + 1, order.expected_day - max(1, supplier.lead_days // 3))
            if order.status == POStatus.ACKNOWLEDGED and self.state.day >= ship_day:
                order.status = POStatus.SHIPPED
                order.shipped_day = self.state.day
            if order.status in {POStatus.SHIPPED, POStatus.DELAYED, POStatus.ACKNOWLEDGED} and self.state.day >= order.expected_day:
                resource = self._resources[order.resource_id]
                projected = self.state.resource_available[order.resource_id] + order.quantity
                if resource.storage_capacity is not None and projected > resource.storage_capacity:
                    order.status = POStatus.DELAYED
                    order.expected_day += 1
                else:
                    order.status = POStatus.ARRIVED
                    order.arrived_day = self.state.day
                    self.state.resource_available[order.resource_id] = projected

        if self.state.day <= self._weather_stop_until:
            return

        rework_work_ids = {
            self.state.issues[issue_id].work_package_id
            for issue_id in self._rework_remaining
            if issue_id in self.state.issues
        }
        for issue_id in list(self._rework_remaining):
            self._rework_remaining[issue_id] -= 1
            if self._rework_remaining[issue_id] <= 0:
                issue = self.state.issues[issue_id]
                issue.open = False
                self._release_nonconsumable(f"rework:{issue_id}")
                del self._rework_remaining[issue_id]
                work = self._work[issue.work_package_id]
                if work.requires_inspection:
                    self.state.work_status[issue.work_package_id] = V2WorkStatus.AWAITING_INSPECTION
                elif work.requires_approval:
                    self.state.work_status[issue.work_package_id] = V2WorkStatus.AWAITING_APPROVAL
                else:
                    self._mark_complete(issue.work_package_id)

        for work_id, status in list(self.state.work_status.items()):
            if status != V2WorkStatus.IN_PROGRESS or work_id in rework_work_ids:
                continue
            decrement = 1 + (1 if work_id in self._overtime_once else 0)
            self.state.work_remaining_days[work_id] = max(
                0, self.state.work_remaining_days[work_id] - decrement
            )
            self._overtime_once.discard(work_id)
            if self.state.work_remaining_days[work_id] == 0:
                self._finish_execution(work_id)

    def _advance_time(self, action: V2Action) -> str:
        days = int(action.parameters.get("days", 1))
        if days < 1 or days > 365:
            raise ProjectWorldV2Error("advance_time days must be between 1 and 365")
        for _ in range(days):
            self._advance_one_day()
        return f"advanced {days} day(s)"

    def _execute(self, role_id: str, action: V2Action) -> str:
        self._authorize(role_id, action)
        if action.kind == V2ActionKind.START_WORK:
            return self._start_work(role_id, action)
        if action.kind == V2ActionKind.ADVANCE_TIME:
            return self._advance_time(action)
        if action.kind == V2ActionKind.PLACE_PO:
            return self._place_po(role_id, action)
        if action.kind == V2ActionKind.EXPEDITE_PO:
            return self._expedite_po(action)
        if action.kind == V2ActionKind.SUBSTITUTE_SUPPLIER:
            return self._substitute_supplier(action)
        if action.kind == V2ActionKind.ADD_CREW:
            return self._add_crew(action)
        if action.kind == V2ActionKind.AUTHORIZE_OVERTIME:
            return self._authorize_overtime(action)
        if action.kind == V2ActionKind.INSPECT:
            return self._inspect(role_id, action)
        if action.kind == V2ActionKind.APPROVE:
            return self._approve(role_id, action)
        if action.kind == V2ActionKind.RESOLVE_ISSUE:
            return self._resolve_issue(action)
        if action.kind == V2ActionKind.RESEQUENCE_WORK:
            return self._resequence(action)
        raise ProjectWorldV2Error(f"unsupported action {action.kind.value}")

    def step(self, role_id: str, action: V2Action) -> V2Transition:
        before = self._potential()
        try:
            message = self._execute(role_id, action)
            accepted = True
        except ProjectWorldV2Error as exc:
            message = str(exc)
            accepted = False
        after = self._potential()
        reward = (after - before) if accepted else -0.05
        self._journal.append(
            {
                "sequence": len(self._journal) + 1,
                "day": self.state.day,
                "role_id": role_id,
                "action": action.kind.value,
                "target_id": action.target_id,
                "accepted": accepted,
                "message": message,
            }
        )
        return V2Transition(
            accepted=accepted,
            reward=reward,
            message=message,
            observation=self.observe(role_id),
            done=self.done,
            info={
                "budget_remaining": self.spec.grammar.budget - self.state.cost_spent,
                "deadline_remaining_days": self.spec.grammar.deadline_days - self.state.day,
            },
        )

    @property
    def done(self) -> bool:
        return all(value == V2WorkStatus.COMPLETE for value in self.state.work_status.values())

    @property
    def journal(self) -> list[dict[str, Any]]:
        return deepcopy(self._journal)

    def verify(self) -> V2OutcomeReport:
        from investigation_world.projectworld.v2_verifier import verify_project_world_v2

        return verify_project_world_v2(self.spec, self.state)


class ProjectWorldV2Session:
    """Model-facing session with immutable environment-bound role identity."""

    def __init__(self, world: OperationalProjectWorldV2, role_id: str):
        world._role(role_id)
        self._world = world
        self.role_id = role_id

    def observe(self) -> V2Observation:
        return self._world.observe(self.role_id)

    def step(self, action: V2Action) -> V2Transition:
        return self._world.step(self.role_id, action)
