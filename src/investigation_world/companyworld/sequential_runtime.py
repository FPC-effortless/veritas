from __future__ import annotations

from typing import Any

from investigation_world.companyworld.interactive_models import (
    OperationalAction,
    OperationalActionType,
    StateValue,
)
from investigation_world.companyworld.models import CompanySystem
from investigation_world.companyworld.runtime import CompanyWorldRecordIndex, SYSTEM_TOOL_COSTS
from investigation_world.companyworld.sequential_models import (
    ScheduledStateEffect,
    SequentialActionExecution,
    SequentialActionPolicy,
    SequentialCompanyWorldEpisode,
    SequentialCompanyWorldVerificationResult,
    SequentialSystemEvent,
    StateCondition,
)
from investigation_world.companyworld.sequential_verifier import verify_sequential_companyworld
from investigation_world.core.models import InvestigationBudget, InvestigationResult


class SequentialCompanyWorldRuntime:
    """Long-horizon CompanyWorld runtime with prerequisites, approvals, delayed effects and recovery."""

    def __init__(
        self,
        episode: SequentialCompanyWorldEpisode,
        *,
        total_cost: int = 70,
        max_tool_calls: int = 60,
    ):
        self.episode = episode
        self.index = CompanyWorldRecordIndex(episode.interactive.investigation.records)
        self.budget = InvestigationBudget(total_cost=total_cost, max_tool_calls=max_tool_calls)
        self.closed = False
        self.tick = 0
        self._state = {item.key(): item.model_copy(deep=True) for item in episode.initial_state}
        self._policies = {item.action_type: item for item in episode.task.action_policies}
        self._scheduled: list[ScheduledStateEffect] = []
        self.journal: list[SequentialActionExecution] = []
        self.events: list[SequentialSystemEvent] = []
        self._remediation_history: list[
            tuple[int, dict[tuple[str, str, str], StateValue | None]]
        ] = []
        self._compensated_sequences: set[int] = set()

    def _ensure_open(self) -> None:
        if self.closed:
            raise ValueError("episode already submitted")

    def _target_key(self, field_name: str) -> tuple[str, str, str]:
        return (
            self.episode.task.target_object_type,
            self.episode.task.target_object_id,
            field_name,
        )

    def _state_value(self, field_name: str) -> Any:
        item = self._state.get(self._target_key(field_name))
        return None if item is None else item.value

    def _condition_met(self, condition: StateCondition) -> bool:
        item = self._state.get(condition.key())
        return item is not None and item.value == condition.expected_value

    def _authorized(self, policy: SequentialActionPolicy, action: OperationalAction) -> bool:
        if self.episode.task.actor_role in policy.allowed_roles:
            return True
        if not policy.delegatable_with_approval:
            return False
        return (
            self._state_value("approval_status") == "APPROVED"
            and self._state_value("approval_scope") == action.action_type.value
        )

    def task(self) -> dict:
        return self.episode.task.model_dump(mode="json")

    def search_system(
        self,
        system: CompanySystem,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        self._ensure_open()
        if system not in self.episode.task.permitted_systems:
            return []
        self.budget.charge(SYSTEM_TOOL_COSTS[system])
        return [
            record.model_dump(mode="json")
            for record in self.index.search(query, system=system, limit=limit)
        ]

    def search(self, query: str, *, system: CompanySystem, limit: int = 10) -> list[dict]:
        return self.search_system(system, query, limit=limit)

    def search_all(self, query: str, limit: int = 10) -> list[dict]:
        self._ensure_open()
        self.budget.charge(3)
        return [record.model_dump(mode="json") for record in self.index.search(query, limit=limit)]

    def open_record(self, record_id: str) -> dict:
        self._ensure_open()
        record = self.index.get(record_id)
        if record is None:
            raise KeyError(record_id)
        self.budget.charge(1)
        return record.model_dump(mode="json")

    def state_snapshot(self) -> list[StateValue]:
        return [
            item.model_copy(deep=True)
            for _, item in sorted(self._state.items(), key=lambda pair: pair[0])
        ]

    def budget_snapshot(self) -> dict:
        return self.budget.model_dump()

    def pending_effects(self) -> list[ScheduledStateEffect]:
        return [item.model_copy(deep=True) for item in self._scheduled]

    def _execution(
        self,
        *,
        action: OperationalAction,
        policy: SequentialActionPolicy | None,
        authorized: bool,
        prerequisites_met: bool,
        applied: bool,
        cost: int,
        reason: str,
        effects: list[StateValue] | None = None,
        scheduled: list[ScheduledStateEffect] | None = None,
    ) -> SequentialActionExecution:
        execution = SequentialActionExecution(
            sequence=len(self.journal) + 1,
            tick=self.tick,
            action=action,
            actor_role=self.episode.task.actor_role,
            authorized=authorized,
            prerequisites_met=prerequisites_met,
            applied=applied,
            cost=cost,
            stage="" if policy is None else policy.stage,
            reason=reason,
            effects=effects or [],
            scheduled_effects=scheduled or [],
        )
        self.journal.append(execution)
        return execution

    def _validate_approval_request(self, action: OperationalAction) -> str | None:
        requested = action.parameters.get("requested_action")
        if not isinstance(requested, str) or not requested:
            return "missing required action parameter: requested_action"
        try:
            requested_type = OperationalActionType(requested)
        except ValueError:
            return "requested approval scope is not a known action"
        policy = self._policies.get(requested_type)
        if policy is None or policy.stage != "remediation":
            return "requested approval scope is not an available remediation action"
        return None

    def _compensate(self, action: OperationalAction, policy: SequentialActionPolicy) -> SequentialActionExecution:
        candidate = next(
            (
                item
                for item in reversed(self._remediation_history)
                if item[0] not in self._compensated_sequences
            ),
            None,
        )
        if candidate is None:
            return self._execution(
                action=action,
                policy=policy,
                authorized=True,
                prerequisites_met=True,
                applied=False,
                cost=policy.cost,
                reason="no applied remediation is available to compensate",
            )

        source_sequence, previous = candidate
        effects: list[StateValue] = []
        for key, prior in previous.items():
            if prior is None:
                self._state.pop(key, None)
                effects.append(
                    StateValue(
                        object_type=key[0],
                        object_id=key[1],
                        field_name=key[2],
                        value=None,
                    )
                )
            else:
                self._state[key] = prior.model_copy(deep=True)
                effects.append(prior.model_copy(deep=True))

        for field_name, value in (
            ("control_remediation_status", "NOT_STARTED"),
            ("reconciliation_status", "NOT_STARTED"),
            ("verification_status", "NOT_STARTED"),
        ):
            state = StateValue(
                object_type=self.episode.task.target_object_type,
                object_id=self.episode.task.target_object_id,
                field_name=field_name,
                value=value,
            )
            self._state[state.key()] = state
            effects.append(state)

        self._scheduled = [
            item
            for item in self._scheduled
            if item.state.field_name not in {"reconciliation_status", "verification_status"}
        ]
        self._compensated_sequences.add(source_sequence)
        return self._execution(
            action=action,
            policy=policy,
            authorized=True,
            prerequisites_met=True,
            applied=True,
            cost=policy.cost,
            reason=f"compensated remediation action sequence {source_sequence}",
            effects=effects,
        )

    def act(self, action: OperationalAction) -> SequentialActionExecution:
        self._ensure_open()
        if len(self.journal) >= self.episode.task.max_actions:
            raise ValueError("sequential action limit exhausted")

        policy = self._policies.get(action.action_type)
        if policy is None or action.action_type not in self.episode.task.available_actions:
            self.budget.charge(1)
            return self._execution(
                action=action,
                policy=None,
                authorized=False,
                prerequisites_met=False,
                applied=False,
                cost=1,
                reason="action is not available for this task",
            )

        self.budget.charge(policy.cost)
        if (
            action.target_object_type != self.episode.task.target_object_type
            or action.target_object_id != self.episode.task.target_object_id
        ):
            return self._execution(
                action=action,
                policy=policy,
                authorized=False,
                prerequisites_met=False,
                applied=False,
                cost=policy.cost,
                reason="action target is outside the task authority scope",
            )

        if not self._authorized(policy, action):
            return self._execution(
                action=action,
                policy=policy,
                authorized=False,
                prerequisites_met=False,
                applied=False,
                cost=policy.cost,
                reason="actor lacks direct or delegated authority for this action",
            )

        missing = [
            template.parameter_name
            for template in [*policy.effects, *policy.delayed_effects]
            if template.parameter_name is not None
            and template.parameter_name not in action.parameters
        ]
        if missing:
            return self._execution(
                action=action,
                policy=policy,
                authorized=True,
                prerequisites_met=False,
                applied=False,
                cost=policy.cost,
                reason="missing required action parameters: " + ", ".join(sorted(set(missing))),
            )

        if action.action_type == OperationalActionType.REQUEST_OPERATIONAL_APPROVAL:
            error = self._validate_approval_request(action)
            if error:
                return self._execution(
                    action=action,
                    policy=policy,
                    authorized=True,
                    prerequisites_met=False,
                    applied=False,
                    cost=policy.cost,
                    reason=error,
                )

        prerequisites_met = all(self._condition_met(item) for item in policy.prerequisites)
        if not prerequisites_met:
            return self._execution(
                action=action,
                policy=policy,
                authorized=True,
                prerequisites_met=False,
                applied=False,
                cost=policy.cost,
                reason="one or more action prerequisites are not satisfied",
            )

        if policy.compensation_action:
            return self._compensate(action, policy)

        previous: dict[tuple[str, str, str], StateValue | None] = {}
        effects: list[StateValue] = []
        for template in policy.effects:
            value = (
                action.parameters[template.parameter_name]
                if template.parameter_name is not None
                else template.constant_value
            )
            state = StateValue(
                object_type=self.episode.task.target_object_type,
                object_id=self.episode.task.target_object_id,
                field_name=template.field_name,
                value=value,
            )
            if policy.stage == "remediation" and state.key() not in previous:
                prior = self._state.get(state.key())
                previous[state.key()] = None if prior is None else prior.model_copy(deep=True)
            self._state[state.key()] = state
            effects.append(state)

        sequence = len(self.journal) + 1
        scheduled: list[ScheduledStateEffect] = []
        for template in policy.delayed_effects:
            value = (
                action.parameters[template.parameter_name]
                if template.parameter_name is not None
                else template.constant_value
            )
            item = ScheduledStateEffect(
                due_tick=self.tick + template.delay_ticks,
                source_sequence=sequence,
                state=StateValue(
                    object_type=self.episode.task.target_object_type,
                    object_id=self.episode.task.target_object_id,
                    field_name=template.field_name,
                    value=value,
                ),
            )
            self._scheduled.append(item)
            scheduled.append(item)

        execution = self._execution(
            action=action,
            policy=policy,
            authorized=True,
            prerequisites_met=True,
            applied=True,
            cost=policy.cost,
            reason="",
            effects=effects,
            scheduled=scheduled,
        )
        if policy.stage == "remediation":
            self._remediation_history.append((execution.sequence, previous))
        return execution

    def advance(self, ticks: int = 1) -> list[SequentialSystemEvent]:
        self._ensure_open()
        if ticks < 1:
            raise ValueError("ticks must be positive")
        if self.tick + ticks > self.episode.task.max_ticks:
            raise ValueError("sequential tick limit exhausted")
        self.budget.charge(ticks)
        emitted: list[SequentialSystemEvent] = []
        for _ in range(ticks):
            self.tick += 1
            due = [item for item in self._scheduled if item.due_tick <= self.tick]
            self._scheduled = [item for item in self._scheduled if item.due_tick > self.tick]
            by_source: dict[int, list[StateValue]] = {}
            for item in due:
                self._state[item.state.key()] = item.state.model_copy(deep=True)
                by_source.setdefault(item.source_sequence, []).append(item.state.model_copy(deep=True))
            for source_sequence, effects in sorted(by_source.items()):
                event = SequentialSystemEvent(
                    tick=self.tick,
                    source_sequence=source_sequence,
                    effects=effects,
                )
                self.events.append(event)
                emitted.append(event)
        return emitted

    def submit(self, result: InvestigationResult) -> SequentialCompanyWorldVerificationResult:
        self._ensure_open()
        verification = verify_sequential_companyworld(
            result,
            self.episode,
            state=self.state_snapshot(),
            journal=list(self.journal),
            ticks_used=self.tick,
            budget_spent=self.budget.spent,
            budget_total=self.budget.total_cost,
        )
        self.closed = True
        return verification
