from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Literal

from investigation_world.foundry.models import stable_hash
from investigation_world.operational.models import (
    ActionKind,
    AssertionComparison,
    HiddenActionEffect,
    HiddenOracle,
    OperationalEpisode,
    OperationalInvariant,
    OperationalRecord,
    PublicActionSpec,
    StateAssertion,
    TaskContract,
    WorldDomain,
)
from investigation_world.portable_contract import (
    PortableOperationalContract,
    compile_operational_episode,
)


class EnvironmentBuilder:
    """Small fluent façade over the canonical OperationalEpisode model.

    The builder does not implement runtime or verifier semantics. ``build()`` produces the existing
    canonical model and relies on its validation. ``compile()`` delegates to the existing portable
    contract compiler, preserving the same fail-closed semantic boundary as hand-authored episodes.
    """

    def __init__(
        self,
        *,
        name: str,
        domain: WorldDomain,
        objective: str,
        role: str,
        world_id: str | None = None,
        task_id: str | None = None,
        episode_id: str | None = None,
    ) -> None:
        if not name.strip():
            raise ValueError("environment name must not be empty")
        if not objective.strip():
            raise ValueError("environment objective must not be empty")
        if not role.strip():
            raise ValueError("environment role must not be empty")
        self._name = name.strip()
        self._domain = domain
        self._objective = objective.strip()
        self._role = role.strip()
        self._world_id = world_id
        self._task_id = task_id
        self._episode_id = episode_id
        self._systems: list[str] = []
        self._actions: list[PublicActionSpec] = []
        self._records: list[OperationalRecord] = []
        self._effects: list[HiddenActionEffect] = []
        self._initial_state: dict[str, Any] = {}
        self._targets: list[StateAssertion] = []
        self._invariants: list[OperationalInvariant] = []
        self._required_actions: list[str] = []
        self._required_action_order: list[str] = []
        self._required_action_counts: dict[str, int] = {}
        self._forbidden_actions: list[str] = []
        self._required_evidence_ids: list[str] = []
        self._constraints: list[str] = []
        self._success_description = ""
        self._max_cost = 40
        self._max_tool_calls = 30
        self._public_metadata: dict[str, Any] = {}
        self._private_metadata: dict[str, Any] = {}
        self._episode_metadata: dict[str, Any] = {}

    def system(self, name: str) -> "EnvironmentBuilder":
        value = name.strip()
        if not value:
            raise ValueError("system name must not be empty")
        if value in self._systems:
            raise ValueError(f"duplicate system: {value}")
        self._systems.append(value)
        return self

    def action(
        self,
        name: str,
        *,
        kind: ActionKind,
        system: str,
        description: str,
        parameters: Iterable[str] = (),
        cost: int = 1,
    ) -> "EnvironmentBuilder":
        value = name.strip()
        system_value = system.strip()
        parameter_names = list(parameters)
        if not value:
            raise ValueError("action name must not be empty")
        if system_value not in self._systems:
            raise ValueError(f"action references undeclared system: {system_value}")
        if value in {item.name for item in self._actions}:
            raise ValueError(f"duplicate action: {value}")
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError("action parameter names must be unique")
        self._actions.append(
            PublicActionSpec(
                name=value,
                kind=kind,
                system=system_value,
                description=description,
                parameter_names=parameter_names,
                cost=cost,
            )
        )
        return self

    def record(
        self,
        record_id: str,
        *,
        system: str,
        record_type: str,
        object_id: str,
        fields: dict[str, Any] | None = None,
        searchable_text: str = "",
        related_object_ids: Iterable[str] = (),
        observed_at: str | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        source_authority: Literal["low", "medium", "high", "authoritative"] = "medium",
        confidence: float = 1.0,
        freshness: Literal["current", "recent", "stale", "historical", "unknown"] = "unknown",
        provenance_ids: Iterable[str] = (),
    ) -> "EnvironmentBuilder":
        if system not in self._systems:
            raise ValueError(f"record references undeclared system: {system}")
        if record_id in {item.record_id for item in self._records}:
            raise ValueError(f"duplicate record: {record_id}")
        self._records.append(
            OperationalRecord(
                record_id=record_id,
                system=system,
                record_type=record_type,
                object_id=object_id,
                fields=deepcopy(fields or {}),
                related_object_ids=list(related_object_ids),
                searchable_text=searchable_text,
                observed_at=observed_at,
                valid_from=valid_from,
                valid_to=valid_to,
                source_authority=source_authority,
                confidence=confidence,
                freshness=freshness,
                provenance_ids=list(provenance_ids),
            )
        )
        return self

    def initial_state(self, **values: Any) -> "EnvironmentBuilder":
        overlap = set(values).intersection(self._initial_state)
        if overlap:
            raise ValueError(f"initial state keys already declared: {sorted(overlap)}")
        self._initial_state.update(deepcopy(values))
        return self

    def target(
        self,
        object_id: str,
        field_name: str,
        expected_value: Any,
        *,
        comparison: AssertionComparison = AssertionComparison.EQUAL,
        tolerance: float | None = None,
    ) -> "EnvironmentBuilder":
        self._targets.append(
            StateAssertion(
                object_id=object_id,
                field_name=field_name,
                expected_value=deepcopy(expected_value),
                comparison=comparison,
                tolerance=tolerance,
            )
        )
        return self

    def invariant(
        self,
        invariant_id: str,
        *,
        description: str,
        object_id: str,
        field_name: str,
        expected_value: Any,
        comparison: AssertionComparison = AssertionComparison.EQUAL,
        tolerance: float | None = None,
        severity: Literal["low", "medium", "high", "critical"] = "high",
        scope: Literal["final", "always"] = "final",
    ) -> "EnvironmentBuilder":
        self._invariants.append(
            OperationalInvariant(
                invariant_id=invariant_id,
                description=description,
                assertion=StateAssertion(
                    object_id=object_id,
                    field_name=field_name,
                    expected_value=deepcopy(expected_value),
                    comparison=comparison,
                    tolerance=tolerance,
                ),
                severity=severity,
                scope=scope,
            )
        )
        return self

    def transition(
        self,
        action_name: str,
        *,
        required_parameters: dict[str, Any] | None = None,
        required_state: Iterable[StateAssertion] = (),
        required_prior_actions: Iterable[str] = (),
        set_state: dict[str, Any] | None = None,
        observable_result: dict[str, Any] | None = None,
        blocked_observable_result: dict[str, Any] | None = None,
        emitted_side_effects: Iterable[str] = (),
        forbidden: bool = False,
        consequence_severity: float = 0.0,
    ) -> "EnvironmentBuilder":
        if action_name not in {item.name for item in self._actions}:
            raise ValueError(f"transition references undeclared action: {action_name}")
        self._effects.append(
            HiddenActionEffect(
                action_name=action_name,
                required_parameters=deepcopy(required_parameters or {}),
                required_state=list(required_state),
                required_prior_actions=list(required_prior_actions),
                set_state=deepcopy(set_state or {}),
                observable_result=deepcopy(observable_result or {}),
                blocked_observable_result=deepcopy(blocked_observable_result or {}),
                emitted_side_effects=list(emitted_side_effects),
                forbidden=forbidden,
                consequence_severity=consequence_severity,
            )
        )
        return self

    def constraint(self, text: str) -> "EnvironmentBuilder":
        if not text.strip():
            raise ValueError("constraint must not be empty")
        self._constraints.append(text.strip())
        return self

    def success(self, description: str) -> "EnvironmentBuilder":
        if not description.strip():
            raise ValueError("success description must not be empty")
        self._success_description = description.strip()
        return self

    def require_action(self, action_name: str, *, minimum_count: int = 1) -> "EnvironmentBuilder":
        self._require_known_action(action_name)
        if minimum_count < 1:
            raise ValueError("minimum action count must be >= 1")
        if action_name not in self._required_actions:
            self._required_actions.append(action_name)
        if minimum_count > 1:
            self._required_action_counts[action_name] = minimum_count
        return self

    def require_order(self, *action_names: str) -> "EnvironmentBuilder":
        for action_name in action_names:
            self._require_known_action(action_name)
        self._required_action_order = list(action_names)
        return self

    def forbid_action(self, action_name: str) -> "EnvironmentBuilder":
        self._require_known_action(action_name)
        if action_name in self._required_actions or action_name in self._required_action_counts:
            raise ValueError("an action cannot be both required and forbidden")
        if action_name not in self._forbidden_actions:
            self._forbidden_actions.append(action_name)
        return self

    def require_evidence(self, record_id: str) -> "EnvironmentBuilder":
        if record_id not in {item.record_id for item in self._records}:
            raise ValueError(f"required evidence references undeclared record: {record_id}")
        if record_id not in self._required_evidence_ids:
            self._required_evidence_ids.append(record_id)
        return self

    def budgets(self, *, max_cost: int = 40, max_tool_calls: int = 30) -> "EnvironmentBuilder":
        if max_cost < 1 or max_tool_calls < 1:
            raise ValueError("environment budgets must be positive")
        self._max_cost = max_cost
        self._max_tool_calls = max_tool_calls
        return self

    def metadata(
        self,
        *,
        public: dict[str, Any] | None = None,
        private: dict[str, Any] | None = None,
        episode: dict[str, Any] | None = None,
    ) -> "EnvironmentBuilder":
        if public is not None:
            self._public_metadata = deepcopy(public)
        if private is not None:
            self._private_metadata = deepcopy(private)
        if episode is not None:
            self._episode_metadata = deepcopy(episode)
        return self

    def build(self) -> OperationalEpisode:
        if not self._systems:
            raise ValueError("environment requires at least one permitted system")
        if not self._actions:
            raise ValueError("environment requires at least one action")
        public_identity_payload = {
            "name": self._name,
            "domain": self._domain.value,
            "objective": self._objective,
            "role": self._role,
            "systems": self._systems,
            "actions": [item.model_dump(mode="json") for item in self._actions],
            "records": [item.model_dump(mode="json") for item in self._records],
            "constraints": self._constraints,
            "success_description": self._success_description,
            "public_metadata": self._public_metadata,
            "episode_metadata": self._episode_metadata,
        }
        digest = stable_hash(public_identity_payload).upper()
        world_id = self._world_id or f"WORLD-{digest[:20]}"
        task_id = self._task_id or f"TASK-{digest[20:40]}"
        episode_id = self._episode_id or f"EP-{digest[40:60]}"
        task = TaskContract(
            task_id=task_id,
            world_id=world_id,
            domain=self._domain,
            objective=self._objective,
            role=self._role,
            permitted_systems=list(self._systems),
            available_actions=deepcopy(self._actions),
            constraints=list(self._constraints),
            success_description=self._success_description,
            metadata=deepcopy(self._public_metadata),
        )
        oracle = HiddenOracle(
            task_id=task_id,
            initial_state=deepcopy(self._initial_state),
            target_state=deepcopy(self._targets),
            invariants=deepcopy(self._invariants),
            required_actions=list(self._required_actions),
            required_action_order=list(self._required_action_order),
            required_action_counts=dict(self._required_action_counts),
            forbidden_actions=list(self._forbidden_actions),
            required_evidence_ids=list(self._required_evidence_ids),
            action_effects=deepcopy(self._effects),
            max_cost=self._max_cost,
            max_tool_calls=self._max_tool_calls,
            metadata=deepcopy(self._private_metadata),
        )
        return OperationalEpisode(
            episode_id=episode_id,
            world_id=world_id,
            task=task,
            records=deepcopy(self._records),
            oracle=oracle,
            metadata=deepcopy(self._episode_metadata),
        )

    def compile(self) -> PortableOperationalContract:
        return compile_operational_episode(self.build())

    def _require_known_action(self, action_name: str) -> None:
        if action_name not in {item.name for item in self._actions}:
            raise ValueError(f"action constraint references undeclared action: {action_name}")
