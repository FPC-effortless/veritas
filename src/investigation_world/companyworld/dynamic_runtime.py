from __future__ import annotations

from typing import Any

from investigation_world.companyworld.dynamic_models import (
    DynamicCompanyWorldScenario,
    DynamicCompanyWorldVerificationResult,
    DynamicConsequenceEvent,
    DynamicFailureMode,
    DynamicHandoff,
    DynamicResourceEvent,
    DynamicToolObservation,
)
from investigation_world.companyworld.interactive_models import (
    OperationalAction,
    OperationalActionType,
)
from investigation_world.companyworld.models import CompanySystem
from investigation_world.companyworld.runtime import SYSTEM_TOOL_COSTS
from investigation_world.companyworld.sequential_models import (
    SequentialActionExecution,
    SequentialActionPolicy,
)
from investigation_world.companyworld.sequential_runtime import SequentialCompanyWorldRuntime
from investigation_world.companyworld.sequential_verifier import verify_sequential_companyworld
from investigation_world.companyworld.dynamic_verifier import verify_dynamic_companyworld
from investigation_world.core.models import InvestigationBudget, InvestigationResult


class _DynamicCaseRuntime(SequentialCompanyWorldRuntime):
    def __init__(
        self,
        episode,
        *,
        approval_outcome: str,
        irreversible_remediation: bool,
    ):
        super().__init__(episode, total_cost=1000, max_tool_calls=1000)
        self.current_actor_role = episode.task.actor_role
        self.approval_outcome = approval_outcome
        self.irreversible_remediation = irreversible_remediation
        self.irreversible_compensation_attempts = 0

    def _authorized(self, policy: SequentialActionPolicy, action: OperationalAction) -> bool:
        if self.current_actor_role in policy.allowed_roles:
            return True
        if not policy.delegatable_with_approval:
            return False
        return (
            self._state_value("approval_status") == "APPROVED"
            and self._state_value("approval_scope") == action.action_type.value
        )

    def _execution(self, **kwargs) -> SequentialActionExecution:
        execution = super()._execution(**kwargs)
        execution.actor_role = self.current_actor_role
        return execution

    def handoff(self, new_role: str) -> None:
        self.current_actor_role = new_role

    def act(self, action: OperationalAction) -> SequentialActionExecution:
        if action.action_type == OperationalActionType.COMPENSATE_LAST_ACTION:
            has_uncompensated = any(
                sequence not in self._compensated_sequences
                for sequence, _ in self._remediation_history
            )
            if self.irreversible_remediation and has_uncompensated:
                policy = self._policies[action.action_type]
                self.budget.charge(policy.cost)
                self.irreversible_compensation_attempts += 1
                return self._execution(
                    action=action,
                    policy=policy,
                    authorized=True,
                    prerequisites_met=True,
                    applied=False,
                    cost=policy.cost,
                    reason="the applied remediation is irreversible",
                )

        execution = super().act(action)
        if (
            action.action_type == OperationalActionType.REQUEST_OPERATIONAL_APPROVAL
            and execution.applied
        ):
            for scheduled in self._scheduled:
                if (
                    scheduled.source_sequence == execution.sequence
                    and scheduled.state.field_name == "approval_status"
                ):
                    scheduled.state.value = self.approval_outcome
        return execution


class DynamicCompanyWorldRuntime:
    """Concurrent CompanyWorld control runtime with stochastic failures and shared constraints."""

    def __init__(self, scenario: DynamicCompanyWorldScenario):
        self.scenario = scenario
        self.tick = 0
        self.closed = False
        self.budget = InvestigationBudget(
            total_cost=scenario.task.total_budget,
            max_tool_calls=500,
        )
        oracle_by_case = {item.case_id: item for item in scenario.oracle.case_oracles}
        self._cases = {item.case_id: item for item in scenario.cases}
        self._case_oracles = oracle_by_case
        self._runtimes = {
            item.case_id: _DynamicCaseRuntime(
                item.sequential,
                approval_outcome=oracle_by_case[item.case_id].approval_outcome,
                irreversible_remediation=item.irreversible_remediation,
            )
            for item in scenario.cases
        }
        self._resource_owners: dict[str, set[str]] = {
            resource: set() for resource in scenario.task.shared_resource_capacities
        }
        self.tool_observations: list[DynamicToolObservation] = []
        self.handoffs: list[DynamicHandoff] = []
        self.resource_events: list[DynamicResourceEvent] = []
        self.consequences: list[DynamicConsequenceEvent] = []
        self.resource_conflicts = 0
        self._deadline_missed: set[str] = set()
        self._coupled_consequence_applied = False

    def _ensure_open(self) -> None:
        if self.closed:
            raise ValueError("dynamic scenario already submitted")

    def _case(self, case_id: str):
        try:
            return self._cases[case_id], self._runtimes[case_id]
        except KeyError as exc:
            raise KeyError(f"unknown dynamic case: {case_id}") from exc

    def _failure_window(self, case_id: str, system: CompanySystem):
        oracle = self._case_oracles[case_id]
        return next(
            (
                window
                for window in oracle.failure_windows
                if window.system == system and window.active(self.tick)
            ),
            None,
        )

    def public_task(self) -> dict[str, Any]:
        return self.scenario.public_payload()

    def case_status(self, case_id: str) -> dict[str, Any]:
        case, runtime = self._case(case_id)
        state = {item.field_name: item.value for item in runtime.state_snapshot()}
        return {
            "case_id": case_id,
            "tick": self.tick,
            "actor_role": runtime.current_actor_role,
            "deadline_tick": case.deadline_tick,
            "priority_weight": case.priority_weight,
            "shared_resource": case.shared_resource,
            "resource_held": case_id in self._resource_owners.get(case.shared_resource, set()),
            "deadline_missed": case_id in self._deadline_missed,
            "state": state,
        }

    def budget_snapshot(self) -> dict[str, Any]:
        return self.budget.model_dump()

    def search_system(
        self,
        case_id: str,
        system: CompanySystem,
        query: str,
        limit: int = 10,
    ) -> DynamicToolObservation:
        self._ensure_open()
        case, runtime = self._case(case_id)
        cost = SYSTEM_TOOL_COSTS.get(system, 2)
        self.budget.charge(cost)
        if system not in case.sequential.task.permitted_systems:
            observation = DynamicToolObservation(
                case_id=case_id,
                tick=self.tick,
                system=system,
                ok=False,
                error="system is not permitted for this case",
            )
            self.tool_observations.append(observation)
            return observation

        failure = self._failure_window(case_id, system)
        if failure is not None and failure.mode == DynamicFailureMode.UNAVAILABLE:
            observation = DynamicToolObservation(
                case_id=case_id,
                tick=self.tick,
                system=system,
                ok=False,
                error="system temporarily unavailable",
                retry_after_tick=failure.end_tick + 1,
            )
            self.tool_observations.append(observation)
            return observation

        records = runtime.index.search(query, system=system, limit=limit)
        payload = [record.model_dump(mode="json") for record in records]
        degraded = failure is not None and failure.mode == DynamicFailureMode.PARTIAL
        if degraded and len(payload) > 1:
            payload = payload[: max(1, len(payload) // 2)]
        observation = DynamicToolObservation(
            case_id=case_id,
            tick=self.tick,
            system=system,
            ok=True,
            degraded=degraded,
            error="partial results due to transient system degradation" if degraded else "",
            retry_after_tick=(failure.end_tick + 1) if degraded and failure is not None else None,
            records=payload,
        )
        self.tool_observations.append(observation)
        return observation

    def handoff(self, case_id: str, new_role: str) -> DynamicHandoff:
        self._ensure_open()
        case, runtime = self._case(case_id)
        self.budget.charge(1)
        old_role = runtime.current_actor_role
        if new_role not in case.role_roster:
            handoff = DynamicHandoff(
                case_id=case_id,
                tick=self.tick,
                from_role=old_role,
                to_role=new_role,
                applied=False,
                reason="requested role is not in the case role roster",
            )
        else:
            runtime.handoff(new_role)
            handoff = DynamicHandoff(
                case_id=case_id,
                tick=self.tick,
                from_role=old_role,
                to_role=new_role,
                applied=True,
            )
        self.handoffs.append(handoff)
        return handoff

    def _resource_available(self, resource: str, case_id: str) -> bool:
        owners = self._resource_owners.setdefault(resource, set())
        if case_id in owners:
            return True
        capacity = self.scenario.task.shared_resource_capacities.get(resource, 1)
        return len(owners) < capacity

    def _acquire_resource(self, resource: str, case_id: str) -> None:
        owners = self._resource_owners.setdefault(resource, set())
        owners.add(case_id)
        self.resource_events.append(
            DynamicResourceEvent(
                case_id=case_id,
                tick=self.tick,
                resource=resource,
                event="ACQUIRED",
                applied=True,
            )
        )

    def _release_resource(self, case_id: str, *, reason: str) -> None:
        case = self._cases[case_id]
        owners = self._resource_owners.setdefault(case.shared_resource, set())
        if case_id not in owners:
            return
        owners.remove(case_id)
        self.resource_events.append(
            DynamicResourceEvent(
                case_id=case_id,
                tick=self.tick,
                resource=case.shared_resource,
                event="RELEASED",
                applied=True,
                reason=reason,
            )
        )

    def act(self, case_id: str, action: OperationalAction) -> SequentialActionExecution:
        self._ensure_open()
        case, runtime = self._case(case_id)
        policy = runtime._policies.get(action.action_type)
        self.budget.charge(1 if policy is None else policy.cost)

        if policy is not None and policy.stage == "remediation":
            resource = case.shared_resource
            if not self._resource_available(resource, case_id):
                self.resource_conflicts += 1
                self.resource_events.append(
                    DynamicResourceEvent(
                        case_id=case_id,
                        tick=self.tick,
                        resource=resource,
                        event="CONFLICT",
                        applied=False,
                        reason="shared resource capacity exhausted",
                    )
                )
                authorized = runtime._authorized(policy, action)
                prerequisites_met = all(runtime._condition_met(item) for item in policy.prerequisites)
                return runtime._execution(
                    action=action,
                    policy=policy,
                    authorized=authorized,
                    prerequisites_met=prerequisites_met,
                    applied=False,
                    cost=policy.cost,
                    reason="shared resource capacity exhausted",
                )
            self._acquire_resource(resource, case_id)

        execution = runtime.act(action)
        if policy is not None and policy.stage == "remediation" and not execution.applied:
            self._release_resource(case_id, reason="remediation was not applied")
        if action.action_type == OperationalActionType.COMPENSATE_LAST_ACTION and execution.applied:
            self._release_resource(case_id, reason="remediation compensated")
        if action.action_type == OperationalActionType.CLOSE_CONTROL_CASE and execution.applied:
            self._release_resource(case_id, reason="control case closed")
        return execution

    def _case_closed(self, case_id: str) -> bool:
        return self._runtimes[case_id]._state_value("control_case_status") == "CLOSED"

    def _apply_deadline_consequences(self) -> None:
        for case_id, case in self._cases.items():
            if (
                self.tick > case.deadline_tick
                and case_id not in self._deadline_missed
                and not self._case_closed(case_id)
            ):
                self._deadline_missed.add(case_id)
                self.consequences.append(
                    DynamicConsequenceEvent(
                        case_id=case_id,
                        tick=self.tick,
                        event="DEADLINE_MISSED",
                        penalty=case.late_penalty,
                        detail="downstream operational consequence realized after missed deadline",
                    )
                )
        if (
            not self._coupled_consequence_applied
            and len(self._deadline_missed) >= self.scenario.oracle.coupled_deadline_threshold
        ):
            self._coupled_consequence_applied = True
            self.consequences.append(
                DynamicConsequenceEvent(
                    case_id=None,
                    tick=self.tick,
                    event="COUPLED_OPERATIONAL_DISRUPTION",
                    penalty=self.scenario.oracle.coupled_deadline_penalty,
                    detail="multiple unresolved cases produced a coupled downstream disruption",
                )
            )

    def advance(self, ticks: int = 1) -> None:
        self._ensure_open()
        if ticks < 1:
            raise ValueError("ticks must be positive")
        for _ in range(ticks):
            if self.tick + 1 > self.scenario.task.max_ticks:
                raise ValueError("dynamic scenario tick limit exhausted")
            self.budget.charge(1)
            self.tick += 1
            for case_id, runtime in self._runtimes.items():
                if runtime.closed or runtime.tick >= runtime.episode.task.max_ticks:
                    continue
                runtime.advance(1)
                if runtime._state_value("reconciliation_status") == "COMPLETE":
                    self._release_resource(case_id, reason="downstream reconciliation completed")
            self._apply_deadline_consequences()

    def _verification_episode(self, case_id: str, runtime: _DynamicCaseRuntime):
        oracle = self._case_oracles[case_id]
        if oracle.approval_outcome != "DENIED":
            return runtime.episode
        if not any(item.case_id == case_id and item.applied for item in self.handoffs):
            return runtime.episode
        episode = runtime.episode.model_copy(deep=True)
        for condition in episode.oracle.control_outcome_conditions:
            if condition.field_name == "approval_status":
                condition.expected_value = "DENIED"
        return episode

    def submit(
        self,
        results: dict[str, InvestigationResult],
    ) -> DynamicCompanyWorldVerificationResult:
        self._ensure_open()
        sequential_results = {}
        for case_id, runtime in self._runtimes.items():
            result = results.get(case_id, InvestigationResult())
            verification_episode = self._verification_episode(case_id, runtime)
            sequential_results[case_id] = verify_sequential_companyworld(
                result,
                verification_episode,
                state=runtime.state_snapshot(),
                journal=list(runtime.journal),
                ticks_used=runtime.tick,
                budget_spent=runtime.budget.spent,
                budget_total=runtime.budget.total_cost,
            )
            runtime.closed = True
        verification = verify_dynamic_companyworld(
            self.scenario,
            sequential_results=sequential_results,
            deadline_missed=set(self._deadline_missed),
            resource_conflicts=self.resource_conflicts,
            tool_observations=list(self.tool_observations),
            handoffs=list(self.handoffs),
            irreversible_compensation_attempts=sum(
                runtime.irreversible_compensation_attempts for runtime in self._runtimes.values()
            ),
            coupled_consequence_applied=self._coupled_consequence_applied,
            budget_spent=self.budget.spent,
            budget_total=self.budget.total_cost,
        )
        self.closed = True
        return verification
