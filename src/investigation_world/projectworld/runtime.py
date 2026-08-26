from __future__ import annotations

from copy import deepcopy
from typing import Any

from investigation_world.projectworld.models import (
    OperationalProjectWorldSpec,
    ProcurementOrder,
    ProjectAction,
    ProjectActionKind,
    ProjectIssue,
    ProjectJournalEvent,
    ProjectObservation,
    ProjectOracle,
    ProjectPhase,
    ProjectScenario,
    ProjectTransition,
    ProjectWorldState,
    ScheduledProjectEvent,
    WorkPackageStatus,
)


_PHASE_ORDER = {
    ProjectPhase.INITIATION: 0,
    ProjectPhase.DESIGN: 1,
    ProjectPhase.PLANNING: 2,
    ProjectPhase.PROCUREMENT: 3,
    ProjectPhase.EXECUTION: 4,
    ProjectPhase.COMMISSIONING: 5,
    ProjectPhase.HANDOVER: 6,
    ProjectPhase.CLOSED: 7,
}


class ProjectActionError(ValueError):
    pass


class OperationalProjectWorld:
    """Deterministic, event-driven project-delivery environment.

    The public specification contains roles, resources, dependencies, requirements and
    design decisions. The private oracle contains delays and latent defects. All project
    consequences are produced by state transitions rather than natural-language judging.
    """

    def __init__(self, scenario: ProjectScenario):
        self.scenario = scenario.model_copy(deep=True)
        self.spec: OperationalProjectWorldSpec = self.scenario.spec
        self._oracle: ProjectOracle = self.scenario.oracle
        self._roles = {role.role_id: role for role in self.spec.roles}
        self._resources = {resource.resource_id: resource for resource in self.spec.resources}
        self._work = {work.work_package_id: work for work in self.spec.work_packages}
        self._decisions = {decision.decision_id: decision for decision in self.spec.decisions}
        self._latent_defects = deepcopy(self._oracle.latent_defects)
        self._scheduled: list[ScheduledProjectEvent] = []
        self._journal: list[ProjectJournalEvent] = []
        self._event_counter = 0
        self._rejected_actions = 0

        status = {
            work.work_package_id: (
                WorkPackageStatus.READY if not work.dependencies else WorkPackageStatus.BLOCKED
            )
            for work in self.spec.work_packages
        }
        self.state = ProjectWorldState(
            phase=self._initial_phase(status),
            work_package_status=status,
            effective_duration_days={
                work.work_package_id: work.duration_days for work in self.spec.work_packages
            },
            effective_direct_cost={
                work.work_package_id: work.direct_cost for work in self.spec.work_packages
            },
            effective_required_resources={
                work.work_package_id: dict(work.required_resources)
                for work in self.spec.work_packages
            },
            resource_available={
                resource.resource_id: resource.initial_available for resource in self.spec.resources
            },
        )
        self._refresh_readiness()

    def public_payload(self) -> dict[str, Any]:
        return self.scenario.public_payload()

    def _initial_phase(self, status: dict[str, WorkPackageStatus]) -> ProjectPhase:
        ready = [
            self._work[work_id].phase
            for work_id, value in status.items()
            if value == WorkPackageStatus.READY
        ]
        return min(ready, key=lambda phase: _PHASE_ORDER[phase]) if ready else ProjectPhase.INITIATION

    def _role(self, role_id: str):
        try:
            return self._roles[role_id]
        except KeyError as exc:
            raise ProjectActionError(f"unknown role: {role_id}") from exc

    def _authorize(self, action: ProjectAction) -> None:
        role = self._role(action.actor_role_id)
        if action.kind not in role.allowed_actions:
            raise ProjectActionError(
                f"role {action.actor_role_id} cannot perform {action.kind.value}"
            )

    def _can_act_for(self, actor_role_id: str, owner_role_id: str) -> bool:
        if actor_role_id == owner_role_id:
            return True
        role = self._role(actor_role_id)
        return owner_role_id in role.managed_role_ids

    def _pending_decisions_for_work(self, work_id: str) -> list[str]:
        return [
            decision.decision_id
            for decision in self.spec.decisions
            if work_id in decision.required_before_work_packages
            and decision.decision_id not in self.state.decisions
        ]

    def _refresh_readiness(self) -> None:
        for work in self.spec.work_packages:
            current = self.state.work_package_status[work.work_package_id]
            if current not in {WorkPackageStatus.BLOCKED, WorkPackageStatus.READY}:
                continue
            dependencies_complete = all(
                self.state.work_package_status[dependency] == WorkPackageStatus.COMPLETE
                for dependency in work.dependencies
            )
            decisions_complete = not self._pending_decisions_for_work(work.work_package_id)
            self.state.work_package_status[work.work_package_id] = (
                WorkPackageStatus.READY
                if dependencies_complete and decisions_complete
                else WorkPackageStatus.BLOCKED
            )
        self._refresh_phase()

    def _refresh_phase(self) -> None:
        if self.done:
            self.state.phase = ProjectPhase.CLOSED
            return
        active = [
            work.phase
            for work in self.spec.work_packages
            if self.state.work_package_status[work.work_package_id] != WorkPackageStatus.COMPLETE
        ]
        self.state.phase = min(active, key=lambda phase: _PHASE_ORDER[phase])

    @property
    def done(self) -> bool:
        return all(
            status == WorkPackageStatus.COMPLETE
            for status in self.state.work_package_status.values()
        )

    def _schedule(
        self,
        event_type: str,
        target_id: str,
        due_day: int,
        payload: dict[str, Any] | None = None,
    ) -> ScheduledProjectEvent:
        self._event_counter += 1
        event = ScheduledProjectEvent(
            event_id=f"evt-{self._event_counter:06d}",
            due_day=due_day,
            event_type=event_type,
            target_id=target_id,
            payload=dict(payload or {}),
        )
        self._scheduled.append(event)
        self._scheduled.sort(key=lambda item: (item.due_day, item.event_id))
        return event

    def _release_nonconsumable_resources(self, work_id: str) -> None:
        requirements = self.state.effective_required_resources[work_id]
        for resource_id, amount in requirements.items():
            if not self._resources[resource_id].consumable:
                self.state.resource_available[resource_id] += amount

    def _mark_complete(self, work_id: str) -> None:
        work = self._work[work_id]
        self.state.work_package_status[work_id] = WorkPackageStatus.COMPLETE
        self.state.work_package_completed_day[work_id] = self.state.day
        self.state.completed_deliverables.extend(
            deliverable
            for deliverable in work.deliverables
            if deliverable not in self.state.completed_deliverables
        )
        self._refresh_readiness()

    def _after_work_execution(self, work_id: str) -> None:
        work = self._work[work_id]
        self._release_nonconsumable_resources(work_id)
        if work.requires_inspection:
            self.state.work_package_status[work_id] = WorkPackageStatus.AWAITING_INSPECTION
            self._refresh_readiness()
        elif work.requires_approval:
            self.state.work_package_status[work_id] = WorkPackageStatus.AWAITING_APPROVAL
            self._refresh_readiness()
        else:
            self._mark_complete(work_id)

    def _process_scheduled_until(self, target_day: int) -> tuple[int, int]:
        completed_before = sum(
            status == WorkPackageStatus.COMPLETE
            for status in self.state.work_package_status.values()
        )
        open_issues_before = sum(issue.open for issue in self.state.issues.values())
        while self._scheduled and self._scheduled[0].due_day <= target_day:
            event = self._scheduled.pop(0)
            self.state.day = event.due_day
            if event.event_type in {"work_complete", "rework_complete"}:
                if event.event_type == "rework_complete":
                    self._latent_defects.pop(event.target_id, None)
                self._after_work_execution(event.target_id)
            elif event.event_type == "resource_arrival":
                resource_id = event.target_id
                quantity = float(event.payload["quantity"])
                self.state.resource_available[resource_id] += quantity
                order_id = str(event.payload["order_id"])
                self.state.procurement_orders[order_id].status = "delivered"
        self.state.day = target_day
        self._refresh_readiness()
        completed_after = sum(
            status == WorkPackageStatus.COMPLETE
            for status in self.state.work_package_status.values()
        )
        open_issues_after = sum(issue.open for issue in self.state.issues.values())
        return completed_after - completed_before, open_issues_after - open_issues_before

    def _start_work(self, action: ProjectAction) -> tuple[str, dict[str, Any], list[str], float]:
        if not action.target_id or action.target_id not in self._work:
            raise ProjectActionError("start_work requires a valid work package target")
        work_id = action.target_id
        work = self._work[work_id]
        if not self._can_act_for(action.actor_role_id, work.owner_role_id):
            raise ProjectActionError(
                f"role {action.actor_role_id} cannot start work owned by {work.owner_role_id}"
            )
        if self.state.work_package_status[work_id] != WorkPackageStatus.READY:
            raise ProjectActionError(
                f"work package {work_id} is not ready: "
                f"{self.state.work_package_status[work_id].value}"
            )
        pending_decisions = self._pending_decisions_for_work(work_id)
        if pending_decisions:
            raise ProjectActionError(
                f"work package {work_id} is waiting on decisions: {pending_decisions}"
            )

        requirements = self.state.effective_required_resources[work_id]
        shortages = {
            resource_id: amount - self.state.resource_available.get(resource_id, 0.0)
            for resource_id, amount in requirements.items()
            if self.state.resource_available.get(resource_id, 0.0) < amount
        }
        if shortages:
            raise ProjectActionError(f"insufficient resources for {work_id}: {shortages}")

        direct_cost = self.state.effective_direct_cost[work_id]
        for resource_id, amount in requirements.items():
            self.state.resource_available[resource_id] -= amount
        self.state.cost_spent += direct_cost
        self.state.work_package_status[work_id] = WorkPackageStatus.IN_PROGRESS
        self.state.work_package_started_day[work_id] = self.state.day
        nominal_duration = self.state.effective_duration_days[work_id]
        hidden_delay = self._oracle.work_package_delay_days.get(work_id, 0)
        self._schedule("work_complete", work_id, self.state.day + nominal_duration + hidden_delay)
        return (
            f"started {work_id}; nominal completion day {self.state.day + nominal_duration}",
            {
                f"work.{work_id}.status": WorkPackageStatus.IN_PROGRESS.value,
                "project.cost_spent": self.state.cost_spent,
            },
            [],
            0.01,
        )

    def _advance_time(self, action: ProjectAction) -> tuple[str, dict[str, Any], list[str], float]:
        days = int(action.parameters.get("days", 0))
        if days <= 0:
            raise ProjectActionError("advance_time requires parameters.days > 0")
        if days > 3650:
            raise ProjectActionError("advance_time cannot exceed 3650 days in one action")
        old_day = self.state.day
        completed_delta, issue_delta = self._process_scheduled_until(self.state.day + days)
        reward = completed_delta * 0.05 - max(0, issue_delta) * 0.1
        return (
            f"advanced project clock from day {old_day} to day {self.state.day}",
            {"project.day": self.state.day, "project.phase": self.state.phase.value},
            [],
            reward,
        )

    def _procure(self, action: ProjectAction) -> tuple[str, dict[str, Any], list[str], float]:
        resource_id = action.target_id
        if not resource_id or resource_id not in self._resources:
            raise ProjectActionError("procure requires a valid resource target")
        quantity = float(action.parameters.get("quantity", 0.0))
        if quantity <= 0:
            raise ProjectActionError("procure requires parameters.quantity > 0")
        resource = self._resources[resource_id]
        order_id = f"PO-{len(self.state.procurement_orders) + 1:05d}"
        expected_day = self.state.day + resource.procurement_lead_days
        hidden_delay = self._oracle.resource_delay_days.get(resource_id, 0)
        cost = quantity * resource.unit_cost
        self.state.cost_spent += cost
        order = ProcurementOrder(
            order_id=order_id,
            resource_id=resource_id,
            quantity=quantity,
            ordered_day=self.state.day,
            expected_day=expected_day,
        )
        self.state.procurement_orders[order_id] = order
        self._schedule(
            "resource_arrival",
            resource_id,
            expected_day + hidden_delay,
            {"quantity": quantity, "order_id": order_id},
        )
        return (
            f"ordered {quantity:g} {resource.unit} of {resource_id}; expected day {expected_day}",
            {
                "project.cost_spent": self.state.cost_spent,
                f"procurement.{order_id}.status": "ordered",
            },
            [],
            0.0,
        )

    def _choose_option(self, action: ProjectAction) -> tuple[str, dict[str, Any], list[str], float]:
        decision_id = action.target_id
        if not decision_id or decision_id not in self._decisions:
            raise ProjectActionError("choose_option requires a valid decision target")
        decision = self._decisions[decision_id]
        if not self._can_act_for(action.actor_role_id, decision.owner_role_id):
            raise ProjectActionError(
                f"role {action.actor_role_id} cannot decide {decision_id} owned by "
                f"{decision.owner_role_id}"
            )
        if decision_id in self.state.decisions:
            raise ProjectActionError(f"decision {decision_id} is already resolved")
        option_id = str(action.parameters.get("option_id", ""))
        option = next((item for item in decision.options if item.option_id == option_id), None)
        if option is None:
            raise ProjectActionError(f"unknown option {option_id!r} for {decision_id}")

        self.state.decisions[decision_id] = option_id
        for work_id, delta in option.cost_delta_by_work_package.items():
            self.state.effective_direct_cost[work_id] = max(
                0.0, self.state.effective_direct_cost[work_id] + delta
            )
        for work_id, delta in option.duration_delta_by_work_package.items():
            self.state.effective_duration_days[work_id] = max(
                1, self.state.effective_duration_days[work_id] + delta
            )
        for work_id, resources in option.resource_requirements_by_work_package.items():
            self.state.effective_required_resources[work_id] = dict(resources)
        self._refresh_readiness()
        return (
            f"selected {option_id} for {decision_id}",
            {f"decision.{decision_id}": option_id},
            [],
            0.01,
        )

    def _inspect(self, action: ProjectAction) -> tuple[str, dict[str, Any], list[str], float]:
        work_id = action.target_id
        if not work_id or work_id not in self._work:
            raise ProjectActionError("inspect requires a valid work package target")
        if self.state.work_package_status[work_id] != WorkPackageStatus.AWAITING_INSPECTION:
            raise ProjectActionError(f"work package {work_id} is not awaiting inspection")
        defect = self._latent_defects.get(work_id)
        work = self._work[work_id]
        if defect is not None:
            issue = ProjectIssue(
                issue_id=defect.issue_id,
                work_package_id=work_id,
                description=defect.description,
                severity=defect.severity,
                rework_cost=defect.rework_cost,
                rework_days=defect.rework_days,
            )
            self.state.issues[issue.issue_id] = issue
            self.state.work_package_status[work_id] = WorkPackageStatus.REWORK_REQUIRED
            return (
                f"inspection failed for {work_id}; issue {issue.issue_id} opened",
                {f"work.{work_id}.status": WorkPackageStatus.REWORK_REQUIRED.value},
                ["quality_defect_detected"],
                -0.1 * defect.severity,
            )
        for issue in self.state.issues.values():
            if issue.work_package_id == work_id and issue.open:
                issue.open = False
        if work.requires_approval:
            self.state.work_package_status[work_id] = WorkPackageStatus.AWAITING_APPROVAL
            self._refresh_readiness()
        else:
            self._mark_complete(work_id)
        return (
            f"inspection passed for {work_id}",
            {f"work.{work_id}.status": self.state.work_package_status[work_id].value},
            [],
            0.04,
        )

    def _resolve_issue(self, action: ProjectAction) -> tuple[str, dict[str, Any], list[str], float]:
        issue_id = action.target_id
        if not issue_id or issue_id not in self.state.issues:
            raise ProjectActionError("resolve_issue requires a valid issue target")
        issue = self.state.issues[issue_id]
        if not issue.open:
            raise ProjectActionError(f"issue {issue_id} is already closed")
        work = self._work[issue.work_package_id]
        if not self._can_act_for(action.actor_role_id, work.owner_role_id):
            raise ProjectActionError(
                f"role {action.actor_role_id} cannot rework package owned by {work.owner_role_id}"
            )
        self.state.cost_spent += issue.rework_cost
        self.state.work_package_status[issue.work_package_id] = WorkPackageStatus.IN_PROGRESS
        self._schedule(
            "rework_complete",
            issue.work_package_id,
            self.state.day + issue.rework_days,
            {"issue_id": issue.issue_id},
        )
        return (
            f"rework started for issue {issue_id}",
            {
                f"work.{issue.work_package_id}.status": WorkPackageStatus.IN_PROGRESS.value,
                "project.cost_spent": self.state.cost_spent,
            },
            [],
            0.0,
        )

    def _approve(self, action: ProjectAction) -> tuple[str, dict[str, Any], list[str], float]:
        work_id = action.target_id
        if not work_id or work_id not in self._work:
            raise ProjectActionError("approve requires a valid work package target")
        work = self._work[work_id]
        if self.state.work_package_status[work_id] != WorkPackageStatus.AWAITING_APPROVAL:
            raise ProjectActionError(f"work package {work_id} is not awaiting approval")
        if action.actor_role_id not in work.approval_role_ids:
            raise ProjectActionError(
                f"role {action.actor_role_id} is not an approver for {work_id}"
            )
        role = self._role(action.actor_role_id)
        amount = self.state.effective_direct_cost[work_id]
        if role.approval_limit is not None and amount > role.approval_limit:
            raise ProjectActionError(
                f"approval value {amount} exceeds {action.actor_role_id} limit {role.approval_limit}"
            )
        self.state.approvals[work_id] = action.actor_role_id
        self._mark_complete(work_id)
        return (
            f"approved {work_id}",
            {f"work.{work_id}.status": WorkPackageStatus.COMPLETE.value},
            [],
            0.04,
        )

    def _apply(self, action: ProjectAction) -> tuple[str, dict[str, Any], list[str], float]:
        self._authorize(action)
        handlers = {
            ProjectActionKind.START_WORK: self._start_work,
            ProjectActionKind.ADVANCE_TIME: self._advance_time,
            ProjectActionKind.PROCURE: self._procure,
            ProjectActionKind.CHOOSE_OPTION: self._choose_option,
            ProjectActionKind.INSPECT: self._inspect,
            ProjectActionKind.RESOLVE_ISSUE: self._resolve_issue,
            ProjectActionKind.APPROVE: self._approve,
        }
        return handlers[action.kind](action)

    def step(self, action: ProjectAction) -> ProjectTransition:
        try:
            message, state_changes, side_effects, reward = self._apply(action)
            accepted = True
        except ProjectActionError as exc:
            accepted = False
            message = str(exc)
            state_changes = {}
            side_effects = ["authority_or_precondition_violation"]
            reward = -0.1
            self._rejected_actions += 1

        event = ProjectJournalEvent(
            sequence=len(self._journal) + 1,
            day=self.state.day,
            actor_role_id=action.actor_role_id,
            action=action.kind,
            target_id=action.target_id,
            accepted=accepted,
            message=message,
            state_changes=state_changes,
            side_effects=side_effects,
        )
        self._journal.append(event)
        return ProjectTransition(
            accepted=accepted,
            reward=reward,
            done=self.done,
            message=message,
            observation=self.observe(action.actor_role_id),
            info={
                "sequence": event.sequence,
                "budget_remaining": self.spec.budget - self.state.cost_spent,
                "deadline_remaining_days": self.spec.deadline_days - self.state.day,
            },
        )

    def observe(self, role_id: str) -> ProjectObservation:
        role = self._role(role_id)
        visible_roles = set(role.visible_role_ids) | {role_id} | set(role.managed_role_ids)
        work_packages: list[dict[str, Any]] = []
        for work in self.spec.work_packages:
            if not role.can_view_all and work.owner_role_id not in visible_roles:
                continue
            work_packages.append(
                {
                    "work_package_id": work.work_package_id,
                    "name": work.name,
                    "phase": work.phase.value,
                    "owner_role_id": work.owner_role_id,
                    "dependencies": list(work.dependencies),
                    "status": self.state.work_package_status[work.work_package_id].value,
                    "duration_days": self.state.effective_duration_days[work.work_package_id],
                    "direct_cost": self.state.effective_direct_cost[work.work_package_id],
                    "required_resources": dict(
                        self.state.effective_required_resources[work.work_package_id]
                    ),
                    "requires_inspection": work.requires_inspection,
                    "requires_approval": work.requires_approval,
                    "deliverables": list(work.deliverables),
                }
            )
        pending_approvals = [
            work.work_package_id
            for work in self.spec.work_packages
            if self.state.work_package_status[work.work_package_id]
            == WorkPackageStatus.AWAITING_APPROVAL
            and role_id in work.approval_role_ids
        ]
        visible_issues = [
            issue.model_dump(mode="json")
            for issue in self.state.issues.values()
            if issue.open
            and (
                role.can_view_all
                or self._work[issue.work_package_id].owner_role_id in visible_roles
            )
        ]
        recent_events = [
            {
                "sequence": event.sequence,
                "day": event.day,
                "actor_role_id": event.actor_role_id,
                "action": event.action.value,
                "target_id": event.target_id,
                "accepted": event.accepted,
                "message": event.message,
            }
            for event in self._journal[-10:]
            if role.can_view_all or event.actor_role_id in visible_roles
        ]
        return ProjectObservation(
            world_id=self.spec.world_id,
            project_id=self.spec.project_id,
            role_id=role_id,
            day=self.state.day,
            phase=self.state.phase,
            budget=self.spec.budget,
            cost_spent=self.state.cost_spent,
            deadline_days=self.spec.deadline_days,
            work_packages=work_packages,
            resources=dict(self.state.resource_available),
            decisions=dict(self.state.decisions),
            pending_decisions=[
                decision.decision_id
                for decision in self.spec.decisions
                if decision.decision_id not in self.state.decisions
                and (role.can_view_all or decision.owner_role_id in visible_roles)
            ],
            pending_approvals=pending_approvals,
            issues=visible_issues,
            recent_events=recent_events,
        )

    def state_snapshot(self) -> dict[str, Any]:
        """Harness-visible state; evaluated agents should receive observe(role_id) instead."""
        return self.state.model_dump(mode="json")

    def trace(self) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in self._journal]

    def verify(self):
        from investigation_world.projectworld.verifier import verify_project_world

        return verify_project_world(
            self.spec,
            self.state,
            rejected_actions=self._rejected_actions,
        )

    @property
    def rejected_actions(self) -> int:
        return self._rejected_actions
