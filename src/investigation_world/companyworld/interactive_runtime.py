from __future__ import annotations

from investigation_world.companyworld.interactive_models import (
    ActionExecution,
    InteractiveCompanyWorldEpisode,
    InteractiveCompanyWorldVerificationResult,
    OperationalAction,
    StateValue,
)
from investigation_world.companyworld.interactive_verifier import verify_interactive_companyworld
from investigation_world.companyworld.runtime import CompanyWorldRecordIndex, SYSTEM_TOOL_COSTS
from investigation_world.companyworld.models import CompanySystem
from investigation_world.core.models import InvestigationBudget, InvestigationResult


class InteractiveCompanyWorldRuntime:
    """Isolated investigate → act → verify runtime over an immutable evidence snapshot."""

    def __init__(
        self,
        episode: InteractiveCompanyWorldEpisode,
        *,
        total_cost: int = 50,
        max_tool_calls: int = 40,
    ):
        self.episode = episode
        self.index = CompanyWorldRecordIndex(episode.investigation.records)
        self.budget = InvestigationBudget(total_cost=total_cost, max_tool_calls=max_tool_calls)
        self.closed = False
        self._state = {item.key(): item.model_copy(deep=True) for item in episode.initial_state}
        self.journal: list[ActionExecution] = []
        self._policies = {item.action_type: item for item in episode.task.action_policies}

    def _ensure_open(self) -> None:
        if self.closed:
            raise ValueError("episode already submitted")

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

    def search(
        self,
        query: str,
        *,
        system: CompanySystem,
        limit: int = 10,
    ) -> list[dict]:
        return self.search_system(system, query, limit=limit)

    def search_all(self, query: str, limit: int = 10) -> list[dict]:
        self._ensure_open()
        self.budget.charge(3)
        return [
            record.model_dump(mode="json")
            for record in self.index.search(query, limit=limit)
        ]

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

    def act(self, action: OperationalAction) -> ActionExecution:
        self._ensure_open()
        policy = self._policies.get(action.action_type)
        sequence = len(self.journal) + 1
        if policy is None or action.action_type not in self.episode.task.available_actions:
            self.budget.charge(1)
            execution = ActionExecution(
                sequence=sequence,
                action=action,
                actor_role=self.episode.task.actor_role,
                authorized=False,
                applied=False,
                cost=1,
                reason="action is not available for this task",
            )
            self.journal.append(execution)
            return execution

        self.budget.charge(policy.cost)
        if (
            action.target_object_type != self.episode.task.target_object_type
            or action.target_object_id != self.episode.task.target_object_id
        ):
            execution = ActionExecution(
                sequence=sequence,
                action=action,
                actor_role=self.episode.task.actor_role,
                authorized=False,
                applied=False,
                cost=policy.cost,
                reason="action target is outside the task authority scope",
            )
            self.journal.append(execution)
            return execution

        authorized = self.episode.task.actor_role in policy.allowed_roles
        if not authorized:
            execution = ActionExecution(
                sequence=sequence,
                action=action,
                actor_role=self.episode.task.actor_role,
                authorized=False,
                applied=False,
                cost=policy.cost,
                reason="actor role is not authorized for this action",
            )
            self.journal.append(execution)
            return execution

        missing = [
            effect.parameter_name
            for effect in policy.effects
            if effect.parameter_name is not None
            and effect.parameter_name not in action.parameters
        ]
        if missing:
            execution = ActionExecution(
                sequence=sequence,
                action=action,
                actor_role=self.episode.task.actor_role,
                authorized=True,
                applied=False,
                cost=policy.cost,
                reason="missing required action parameters: " + ", ".join(sorted(set(missing))),
            )
            self.journal.append(execution)
            return execution

        effects: list[StateValue] = []
        for template in policy.effects:
            value = (
                action.parameters[template.parameter_name]
                if template.parameter_name is not None
                else template.constant_value
            )
            state = StateValue(
                object_type=action.target_object_type,
                object_id=action.target_object_id,
                field_name=template.field_name,
                value=value,
            )
            self._state[state.key()] = state
            effects.append(state)

        execution = ActionExecution(
            sequence=sequence,
            action=action,
            actor_role=self.episode.task.actor_role,
            authorized=True,
            applied=True,
            cost=policy.cost,
            effects=effects,
        )
        self.journal.append(execution)
        return execution

    def submit(
        self,
        result: InvestigationResult,
    ) -> InteractiveCompanyWorldVerificationResult:
        self._ensure_open()
        verification = verify_interactive_companyworld(
            result,
            self.episode,
            state=self.state_snapshot(),
            journal=list(self.journal),
            budget_spent=self.budget.spent,
            budget_total=self.budget.total_cost,
        )
        self.closed = True
        return verification
