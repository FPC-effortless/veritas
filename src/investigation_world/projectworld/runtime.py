from __future__ import annotations

from collections import defaultdict
from typing import Any

from investigation_world.projectworld.models import (
    ConditionOperator,
    OperationalProjectEpisode,
    OperationalProjectVerificationResult,
    ProjectAction,
    ProjectActionExecution,
    ProjectActionPolicy,
    ProjectActionType,
    ProjectActivity,
    ProjectEffectTemplate,
    ProjectEvidenceRecord,
    ProjectObservation,
    ProjectPhase,
    ProjectResource,
    ProjectRole,
    ProjectRolePolicy,
    ProjectStateValue,
    ProjectSystemEvent,
    ScheduledProjectEffect,
)
from investigation_world.projectworld.verifier import verify_operational_project


_PHASE_ORDER = list(ProjectPhase)


class OperationalProjectWorldRuntime:
    """Event-driven, multi-role project-delivery runtime with hidden world state."""

    def __init__(self, episode: OperationalProjectEpisode):
        self.episode = episode
        self.tick = 0
        self.phase = episode.task.initial_phase
        self.closed = False
        self.committed_cost = 0.0
        self._state = {item.key(): item.model_copy(deep=True) for item in episode.initial_state}
        self._role_policies = {item.role: item for item in episode.task.role_policies}
        self._action_policies = {item.action_type: item for item in episode.task.action_policies}
        self._activities = {item.activity_id: item for item in episode.activities}
        self._resources = {item.resource_id: item for item in episode.resources}
        self._resource_usage: dict[str, int] = defaultdict(int)
        self._activity_claims: dict[str, dict[str, int]] = {}
        self._scheduled: list[ScheduledProjectEffect] = []
        self._hidden_events = sorted(
            [item.model_copy(deep=True) for item in episode.oracle.hidden_events],
            key=lambda item: (item.due_tick, item.event_id),
        )
        self._emitted_hidden_events: set[str] = set()
        self.journal: list[ProjectActionExecution] = []
        self.events: list[ProjectSystemEvent] = []
        self._compensated_sequences: set[int] = set()
        self._state_history: dict[int, dict[tuple[str, str, str], ProjectStateValue | None]] = {}

    def _ensure_open(self) -> None:
        if self.closed:
            raise ValueError("project episode already submitted")

    def _role_policy(self, role: ProjectRole) -> ProjectRolePolicy:
        try:
            return self._role_policies[role]
        except KeyError as exc:
            raise ValueError(f"role {role.value} is not active in this project") from exc

    def _condition_met(self, condition) -> bool:
        item = self._state.get(condition.key())
        value = None if item is None else item.value
        expected = condition.expected_value
        op = condition.operator
        if op == ConditionOperator.EXISTS:
            return item is not None
        if op == ConditionOperator.EQ:
            return value == expected
        if op == ConditionOperator.NE:
            return value != expected
        if op == ConditionOperator.IN:
            return value in expected if expected is not None else False
        if op == ConditionOperator.NOT_IN:
            return value not in expected if expected is not None else True
        if value is None:
            return False
        try:
            if op == ConditionOperator.LTE:
                return value <= expected
            if op == ConditionOperator.GTE:
                return value >= expected
            if op == ConditionOperator.LT:
                return value < expected
            if op == ConditionOperator.GT:
                return value > expected
        except TypeError:
            return False
        return False

    def _render_effect(
        self,
        template: ProjectEffectTemplate,
        action: ProjectAction,
    ) -> ProjectStateValue:
        value = (
            action.parameters[template.parameter_name]
            if template.parameter_name is not None
            else template.constant_value
        )
        return ProjectStateValue(
            object_type=template.object_type or action.target_object_type,
            object_id=template.object_id or action.target_object_id,
            field_name=template.field_name,
            value=value,
            namespace=template.namespace,
            source_ids=list(action.evidence_ids),
        )

    def state_snapshot(self) -> list[ProjectStateValue]:
        return [
            value.model_copy(deep=True)
            for _, value in sorted(self._state.items(), key=lambda item: item[0])
        ]

    def resource_snapshot(self) -> dict[str, int]:
        return dict(sorted(self._resource_usage.items()))

    def observation_for(self, role: ProjectRole) -> ProjectObservation:
        policy = self._role_policy(role)
        allowed = set(policy.readable_namespaces)
        state = [
            item.model_copy(deep=True)
            for item in self.state_snapshot()
            if item.namespace in allowed or "*" in allowed
        ]
        visible_evidence = [
            item.model_copy(deep=True)
            for item in self.episode.evidence
            if item.namespace in allowed or "*" in allowed
        ]
        remaining = None
        if self.episode.task.budget_limit > 0:
            remaining = max(0.0, self.episode.task.budget_limit - self.committed_cost)
        return ProjectObservation(
            role=role,
            tick=self.tick,
            phase=self.phase,
            state=state,
            visible_evidence=visible_evidence,
            resource_usage=self.resource_snapshot(),
            committed_cost=self.committed_cost,
            remaining_budget=remaining,
        )

    def search_evidence(
        self,
        role: ProjectRole,
        query: str,
        *,
        evidence_type: str | None = None,
        limit: int = 10,
    ) -> list[ProjectEvidenceRecord]:
        policy = self._role_policy(role)
        allowed = set(policy.readable_namespaces)
        terms = [term.casefold() for term in query.split() if term.strip()]
        scored: list[tuple[int, str, ProjectEvidenceRecord]] = []
        for item in self.episode.evidence:
            if item.namespace not in allowed and "*" not in allowed:
                continue
            if evidence_type is not None and item.evidence_type != evidence_type:
                continue
            haystack = " ".join(
                [item.title, item.text, str(item.structured_payload)]
            ).casefold()
            score = sum(1 for term in terms if term in haystack)
            if terms and score == 0:
                continue
            scored.append((score, item.evidence_id, item))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [row[2].model_copy(deep=True) for row in scored[:limit]]

    def _record_execution(
        self,
        *,
        role: ProjectRole,
        action: ProjectAction,
        policy: ProjectActionPolicy | None,
        authorized: bool,
        prerequisites_met: bool,
        evidence_sufficient: bool,
        resource_feasible: bool,
        applied: bool,
        reason: str,
        financial_impact: float = 0.0,
        effects: list[ProjectStateValue] | None = None,
        scheduled: list[ScheduledProjectEffect] | None = None,
    ) -> ProjectActionExecution:
        execution = ProjectActionExecution(
            sequence=len(self.journal) + 1,
            tick=self.tick,
            actor_role=role,
            action=action,
            authorized=authorized,
            prerequisites_met=prerequisites_met,
            evidence_sufficient=evidence_sufficient,
            resource_feasible=resource_feasible,
            applied=applied,
            cost=0 if policy is None else policy.cost,
            financial_impact=financial_impact,
            reason=reason,
            irreversible=False if policy is None else policy.irreversible,
            effects=effects or [],
            scheduled_effects=scheduled or [],
        )
        self.journal.append(execution)
        return execution

    def _evidence_sufficient(self, policy: ProjectActionPolicy, action: ProjectAction) -> bool:
        if not policy.required_evidence_types:
            return True
        evidence_by_id = {item.evidence_id: item for item in self.episode.evidence}
        supplied_types = {
            evidence_by_id[eid].evidence_type
            for eid in action.evidence_ids
            if eid in evidence_by_id
        }
        return set(policy.required_evidence_types).issubset(supplied_types)

    def _activity_ready(self, activity: ProjectActivity) -> bool:
        for predecessor_id in activity.predecessor_ids:
            state = self._state.get(("activity", predecessor_id, "status"))
            if state is None or state.value != "COMPLETED":
                return False
        return True

    def _resource_feasible(self, activity: ProjectActivity) -> bool:
        for resource_id, demand in activity.resource_demands.items():
            resource = self._resources.get(resource_id)
            if resource is None:
                return False
            if self._resource_usage[resource_id] + demand > resource.capacity:
                return False
        return True

    def _claim_activity_resources(self, activity: ProjectActivity) -> None:
        claims = dict(activity.resource_demands)
        for resource_id, demand in claims.items():
            self._resource_usage[resource_id] += demand
        self._activity_claims[activity.activity_id] = claims

    def _release_activity_resources(self, activity_id: str) -> None:
        for resource_id, demand in self._activity_claims.pop(activity_id, {}).items():
            self._resource_usage[resource_id] = max(0, self._resource_usage[resource_id] - demand)

    def _financial_impact(
        self,
        role_policy: ProjectRolePolicy,
        action_policy: ProjectActionPolicy,
        action: ProjectAction,
    ) -> tuple[bool, float, str]:
        if action_policy.financial_parameter is None:
            return True, 0.0, ""
        raw = action.parameters.get(action_policy.financial_parameter)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool) or raw < 0:
            return False, 0.0, f"invalid financial parameter: {action_policy.financial_parameter}"
        amount = float(raw)
        if amount > role_policy.direct_authority_limit and not role_policy.can_approve:
            return False, amount, "financial impact exceeds actor direct authority"
        if (
            self.episode.task.budget_limit > 0
            and self.committed_cost + amount > self.episode.task.budget_limit
        ):
            return False, amount, "project budget would be exceeded"
        return True, amount, ""

    def _compensate(
        self,
        role: ProjectRole,
        action: ProjectAction,
        policy: ProjectActionPolicy,
    ) -> ProjectActionExecution:
        candidates = [
            item
            for item in reversed(self.journal)
            if item.applied
            and not item.irreversible
            and item.sequence not in self._compensated_sequences
            and item.action.action_type != ProjectActionType.COMPENSATE_ACTION
        ]
        if not candidates:
            return self._record_execution(
                role=role,
                action=action,
                policy=policy,
                authorized=True,
                prerequisites_met=True,
                evidence_sufficient=True,
                resource_feasible=True,
                applied=False,
                reason="no reversible action is available to compensate",
            )
        requested = action.parameters.get("sequence")
        source = next((item for item in candidates if item.sequence == requested), candidates[0])
        prior = self._state_history.get(source.sequence, {})
        effects: list[ProjectStateValue] = []
        for key, old in prior.items():
            if old is None:
                self._state.pop(key, None)
                effects.append(
                    ProjectStateValue(
                        object_type=key[0], object_id=key[1], field_name=key[2], value=None
                    )
                )
            else:
                self._state[key] = old.model_copy(deep=True)
                effects.append(old.model_copy(deep=True))
        if source.action.action_type == ProjectActionType.START_ACTIVITY:
            self._release_activity_resources(source.action.target_object_id)
        self.committed_cost = max(0.0, self.committed_cost - source.financial_impact)
        self._compensated_sequences.add(source.sequence)
        return self._record_execution(
            role=role,
            action=action,
            policy=policy,
            authorized=True,
            prerequisites_met=True,
            evidence_sufficient=True,
            resource_feasible=True,
            applied=True,
            reason=f"compensated action sequence {source.sequence}",
            financial_impact=-source.financial_impact,
            effects=effects,
        )

    def act(self, role: ProjectRole, action: ProjectAction) -> ProjectActionExecution:
        self._ensure_open()
        if len(self.journal) >= self.episode.task.max_actions:
            raise ValueError("project action limit exhausted")
        role_policy = self._role_policy(role)
        policy = self._action_policies.get(action.action_type)
        if policy is None:
            return self._record_execution(
                role=role,
                action=action,
                policy=None,
                authorized=False,
                prerequisites_met=False,
                evidence_sufficient=False,
                resource_feasible=False,
                applied=False,
                reason="action is not available in this project world",
            )
        authorized = role in policy.allowed_roles and self.phase in policy.allowed_phases
        if policy.allowed_object_types and action.target_object_type not in policy.allowed_object_types:
            authorized = False
        if not authorized:
            return self._record_execution(
                role=role,
                action=action,
                policy=policy,
                authorized=False,
                prerequisites_met=False,
                evidence_sufficient=False,
                resource_feasible=False,
                applied=False,
                reason="actor, phase, or target is outside action authority",
            )

        target_namespace = next(
            (
                item.namespace
                for item in self._state.values()
                if item.object_type == action.target_object_type
                and item.object_id == action.target_object_id
            ),
            "project",
        )
        if (
            target_namespace not in role_policy.writable_namespaces
            and "*" not in role_policy.writable_namespaces
        ):
            return self._record_execution(
                role=role,
                action=action,
                policy=policy,
                authorized=False,
                prerequisites_met=False,
                evidence_sufficient=False,
                resource_feasible=False,
                applied=False,
                reason="actor cannot mutate target namespace",
            )

        missing_parameters = {
            item.parameter_name
            for item in [*policy.effects, *policy.delayed_effects]
            if item.parameter_name is not None and item.parameter_name not in action.parameters
        }
        if policy.financial_parameter and policy.financial_parameter not in action.parameters:
            missing_parameters.add(policy.financial_parameter)
        if missing_parameters:
            return self._record_execution(
                role=role,
                action=action,
                policy=policy,
                authorized=True,
                prerequisites_met=False,
                evidence_sufficient=False,
                resource_feasible=False,
                applied=False,
                reason="missing required action parameters: "
                + ", ".join(sorted(missing_parameters)),
            )

        prerequisites_met = all(self._condition_met(item) for item in policy.prerequisites)
        activity = self._activities.get(action.target_object_id)
        if action.action_type == ProjectActionType.START_ACTIVITY and activity is not None:
            status = self._state.get(("activity", activity.activity_id, "status"))
            blocked = self._state.get(("activity", activity.activity_id, "blocked"))
            safety_hold = self._state.get(("activity", activity.activity_id, "safety_hold"))
            prerequisites_met = (
                prerequisites_met
                and self._activity_ready(activity)
                and (status is None or status.value in {"PLANNED", "PAUSED"})
                and not (blocked is not None and blocked.value is True)
                and not (safety_hold is not None and safety_hold.value is True)
            )
        elif action.action_type == ProjectActionType.COMPLETE_ACTIVITY and activity is not None:
            status = self._state.get(("activity", activity.activity_id, "status"))
            started = self._state.get(("activity", activity.activity_id, "actual_start_tick"))
            duration_met = (
                started is not None
                and isinstance(started.value, int)
                and self.tick - started.value >= activity.duration_ticks
            )
            safety_hold = self._state.get(("activity", activity.activity_id, "safety_hold"))
            prerequisites_met = (
                prerequisites_met
                and status is not None
                and status.value == "IN_PROGRESS"
                and duration_met
                and not (safety_hold is not None and safety_hold.value is True)
            )
        if not prerequisites_met:
            return self._record_execution(
                role=role,
                action=action,
                policy=policy,
                authorized=True,
                prerequisites_met=False,
                evidence_sufficient=False,
                resource_feasible=False,
                applied=False,
                reason="one or more project prerequisites are not satisfied",
            )

        evidence_sufficient = self._evidence_sufficient(policy, action)
        if not evidence_sufficient:
            return self._record_execution(
                role=role,
                action=action,
                policy=policy,
                authorized=True,
                prerequisites_met=True,
                evidence_sufficient=False,
                resource_feasible=False,
                applied=False,
                reason="required evidence is missing",
            )

        resource_feasible = True
        if policy.resource_gated and activity is not None:
            resource_feasible = self._resource_feasible(activity)
        if not resource_feasible:
            return self._record_execution(
                role=role,
                action=action,
                policy=policy,
                authorized=True,
                prerequisites_met=True,
                evidence_sufficient=True,
                resource_feasible=False,
                applied=False,
                reason="shared project resources are unavailable",
            )

        finance_ok, financial_impact, finance_reason = self._financial_impact(
            role_policy, policy, action
        )
        if (
            finance_ok
            and action.action_type == ProjectActionType.START_ACTIVITY
            and activity is not None
        ):
            financial_impact += activity.planned_cost
            if (
                self.episode.task.budget_limit > 0
                and self.committed_cost + financial_impact > self.episode.task.budget_limit
            ):
                finance_ok = False
                finance_reason = "planned activity commitment would exceed project budget"
        if not finance_ok:
            return self._record_execution(
                role=role,
                action=action,
                policy=policy,
                authorized=False,
                prerequisites_met=True,
                evidence_sufficient=True,
                resource_feasible=True,
                applied=False,
                reason=finance_reason,
                financial_impact=financial_impact,
            )

        if action.action_type == ProjectActionType.COMPENSATE_ACTION:
            return self._compensate(role, action, policy)

        sequence = len(self.journal) + 1
        previous: dict[tuple[str, str, str], ProjectStateValue | None] = {}
        effects: list[ProjectStateValue] = []
        for template in policy.effects:
            state = self._render_effect(template, action)
            if state.key() not in previous:
                old = self._state.get(state.key())
                previous[state.key()] = None if old is None else old.model_copy(deep=True)
            self._state[state.key()] = state
            effects.append(state)

        scheduled: list[ScheduledProjectEffect] = []
        for template in policy.delayed_effects:
            state = self._render_effect(template, action)
            scheduled_item = ScheduledProjectEffect(
                due_tick=self.tick + template.delay_ticks,
                source_sequence=sequence,
                state=state,
            )
            self._scheduled.append(scheduled_item)
            scheduled.append(scheduled_item)

        if action.action_type == ProjectActionType.START_ACTIVITY and activity is not None:
            start_state = ProjectStateValue(
                object_type="activity",
                object_id=activity.activity_id,
                field_name="actual_start_tick",
                value=self.tick,
                namespace="schedule",
                source_ids=list(action.evidence_ids),
            )
            old_start = self._state.get(start_state.key())
            if start_state.key() not in previous:
                previous[start_state.key()] = (
                    None if old_start is None else old_start.model_copy(deep=True)
                )
            self._state[start_state.key()] = start_state
            effects.append(start_state)
            self._claim_activity_resources(activity)
        elif action.action_type in {
            ProjectActionType.COMPLETE_ACTIVITY,
            ProjectActionType.PAUSE_ACTIVITY,
        }:
            self._release_activity_resources(action.target_object_id)

        if action.action_type == ProjectActionType.ADVANCE_PHASE:
            requested = action.parameters.get("phase")
            try:
                next_phase = ProjectPhase(requested)
            except (TypeError, ValueError):
                return self._record_execution(
                    role=role,
                    action=action,
                    policy=policy,
                    authorized=True,
                    prerequisites_met=True,
                    evidence_sufficient=True,
                    resource_feasible=True,
                    applied=False,
                    reason="phase parameter is invalid",
                )
            if _PHASE_ORDER.index(next_phase) != _PHASE_ORDER.index(self.phase) + 1:
                return self._record_execution(
                    role=role,
                    action=action,
                    policy=policy,
                    authorized=True,
                    prerequisites_met=True,
                    evidence_sufficient=True,
                    resource_feasible=True,
                    applied=False,
                    reason="project phases may only advance one stage at a time",
                )
            self.phase = next_phase

        self._state_history[sequence] = previous
        self.committed_cost += financial_impact
        return self._record_execution(
            role=role,
            action=action,
            policy=policy,
            authorized=True,
            prerequisites_met=True,
            evidence_sufficient=True,
            resource_feasible=True,
            applied=True,
            reason="",
            financial_impact=financial_impact,
            effects=effects,
            scheduled=scheduled,
        )

    def _apply_state_effects(self, effects: list[ProjectStateValue]) -> None:
        for state in effects:
            self._state[state.key()] = state.model_copy(deep=True)

    def _accrue_resource_cost(self) -> float:
        total = 0.0
        for resource_id, usage in self._resource_usage.items():
            resource: ProjectResource | None = self._resources.get(resource_id)
            if resource is not None:
                total += usage * resource.unit_cost_per_tick
        self.committed_cost += total
        return total

    def advance(self, ticks: int = 1) -> list[ProjectSystemEvent]:
        self._ensure_open()
        if ticks < 1:
            raise ValueError("ticks must be positive")
        if self.tick + ticks > self.episode.task.max_ticks:
            raise ValueError("project tick limit exhausted")
        emitted: list[ProjectSystemEvent] = []
        for _ in range(ticks):
            self.tick += 1
            due = [item for item in self._scheduled if item.due_tick <= self.tick]
            self._scheduled = [item for item in self._scheduled if item.due_tick > self.tick]
            for item in due:
                self._apply_state_effects([item.state])
                event = ProjectSystemEvent(
                    tick=self.tick,
                    event_type="scheduled_effect",
                    event_id=f"action-{item.source_sequence}",
                    effects=[item.state.model_copy(deep=True)],
                )
                self.events.append(event)
                emitted.append(event)

            for hidden in self._hidden_events:
                if hidden.event_id in self._emitted_hidden_events or hidden.due_tick > self.tick:
                    continue
                self._apply_state_effects(hidden.effects)
                self._emitted_hidden_events.add(hidden.event_id)
                event = ProjectSystemEvent(
                    tick=self.tick,
                    event_type="exogenous_event",
                    event_id=hidden.event_id,
                    effects=[item.model_copy(deep=True) for item in hidden.effects],
                    detail=hidden.label,
                )
                self.events.append(event)
                emitted.append(event)

            resource_cost = self._accrue_resource_cost()
            if resource_cost > 0:
                event = ProjectSystemEvent(
                    tick=self.tick,
                    event_type="resource_cost",
                    event_id=f"resource-cost-{self.tick}",
                    detail=f"accrued {resource_cost:.2f} in active resource cost",
                )
                self.events.append(event)
                emitted.append(event)
        return emitted

    def verify(self) -> OperationalProjectVerificationResult:
        return verify_operational_project(
            self.episode,
            state=self.state_snapshot(),
            journal=list(self.journal),
            events=list(self.events),
            ticks_used=self.tick,
            committed_cost=self.committed_cost,
        )

    def submit(self) -> OperationalProjectVerificationResult:
        self._ensure_open()
        result = self.verify()
        self.closed = True
        return result
