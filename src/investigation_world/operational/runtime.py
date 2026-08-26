from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from investigation_world.core.models import InvestigationBudget
from investigation_world.operational.models import (
    ActionEvent,
    EpisodeSubmission,
    HiddenActionEffect,
    OperationalEpisode,
    OperationalRecord,
    PublicActionSpec,
    VerificationBreakdown,
)
from investigation_world.operational.substrate import PersistentOperationalSubstrate
from investigation_world.operational.verifier import verify_operational_episode


class OperationalRecordIndex:
    def __init__(self, records: list[OperationalRecord]):
        self._records = {record.record_id: record for record in records}
        self._by_system: dict[str, list[OperationalRecord]] = defaultdict(list)
        self._text: dict[str, str] = {}
        for record in records:
            self._by_system[record.system].append(record)
            self._text[record.record_id] = " ".join(
                [
                    record.record_type,
                    record.object_id,
                    record.searchable_text,
                    *record.related_object_ids,
                    json.dumps(record.fields, sort_keys=True, default=str),
                ]
            ).casefold()

    def get(self, record_id: str) -> OperationalRecord | None:
        return self._records.get(record_id)

    def search(
        self,
        query: str,
        *,
        system: str | None = None,
        limit: int = 10,
    ) -> list[OperationalRecord]:
        terms = [term.casefold() for term in query.split() if term.strip()]
        if not terms:
            return []
        candidates = self._by_system.get(system, []) if system else list(self._records.values())
        scored: list[tuple[int, str, OperationalRecord]] = []
        for record in candidates:
            text = self._text[record.record_id]
            if not all(term in text for term in terms):
                continue
            score = sum(text.count(term) for term in terms)
            scored.append((score, record.record_id, record))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored[: max(1, min(limit, 100))]]


class OperationalRuntime:
    """Capability-neutral executable runtime used by every Veritas operational world."""

    def __init__(
        self,
        episode: OperationalEpisode,
        *,
        substrate: PersistentOperationalSubstrate | None = None,
    ):
        self.episode = episode
        self.index = OperationalRecordIndex(episode.records)
        self.substrate = substrate
        if substrate is not None:
            substrate.mount_episode(episode)
            self.state = substrate.state
        else:
            self.state = dict(episode.oracle.initial_state)
        self.events: list[ActionEvent] = []
        self.budget = InvestigationBudget(
            total_cost=episode.oracle.max_cost,
            max_tool_calls=episode.oracle.max_tool_calls,
        )
        self.closed = False
        self._actions = {action.name: action for action in episode.task.available_actions}

    def _ensure_open(self) -> None:
        if self.closed:
            raise ValueError("episode already submitted")

    def _charge(self, cost: int) -> None:
        self._ensure_open()
        self.budget.charge(cost)

    def public_payload(self) -> dict[str, Any]:
        return self.episode.public_payload()

    def search(self, system: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
        if system not in self.episode.task.permitted_systems:
            return []
        self._charge(1)
        return [
            record.model_dump(mode="json")
            for record in self.index.search(query, system=system, limit=limit)
        ]

    def search_all(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        self._charge(2)
        return [record.model_dump(mode="json") for record in self.index.search(query, limit=limit)]

    def open_record(self, record_id: str) -> dict[str, Any]:
        self._charge(1)
        record = self.index.get(record_id)
        if record is None:
            raise KeyError(record_id)
        return record.model_dump(mode="json")

    def state_snapshot(self) -> dict[str, Any]:
        """Harness-visible state snapshot; callers decide whether to expose it to an agent."""
        if self.substrate is not None:
            return self.substrate.state
        return dict(self.state)

    def budget_snapshot(self) -> dict[str, Any]:
        return self.budget.model_dump()

    def _matching_effect(
        self,
        action: PublicActionSpec,
        parameters: dict[str, Any],
    ) -> HiddenActionEffect | None:
        for effect in self.episode.oracle.action_effects:
            if effect.action_name != action.name:
                continue
            if all(parameters.get(key) == value for key, value in effect.required_parameters.items()):
                return effect
        return None

    def act(self, action_name: str, **parameters: Any) -> dict[str, Any]:
        self._ensure_open()
        action = self._actions.get(action_name)
        if action is None:
            raise KeyError(action_name)
        missing = [name for name in action.parameter_names if name not in parameters]
        if missing:
            raise ValueError(f"missing parameters for {action_name}: {missing}")
        self._charge(action.cost)
        effect = self._matching_effect(action, parameters)
        state_changes: dict[str, Any] = {}
        side_effects: list[str] = []
        forbidden = action_name in self.episode.oracle.forbidden_actions
        severity = 0.0
        if effect is not None:
            state_changes = dict(effect.set_state)
            self.state.update(state_changes)
            side_effects = list(effect.emitted_side_effects)
            forbidden = forbidden or effect.forbidden
            severity = effect.consequence_severity
        if self.substrate is not None:
            self.substrate.apply_changes(
                world_id=self.episode.world_id,
                domain=self.episode.task.domain,
                action_name=action.name,
                changes=state_changes,
                side_effects=side_effects,
            )
        event = ActionEvent(
            sequence=len(self.events) + 1,
            action_name=action.name,
            kind=action.kind,
            system=action.system,
            parameters=parameters,
            cost=action.cost,
            state_changes=state_changes,
            side_effects=side_effects,
            forbidden=forbidden,
            consequence_severity=severity,
        )
        self.events.append(event)
        return {
            "accepted": not forbidden,
            "action": action.name,
            "state_changes": state_changes,
            "side_effects": side_effects,
        }

    def trace(self) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in self.events]

    def submit(self, submission: EpisodeSubmission) -> VerificationBreakdown:
        self._ensure_open()
        current_state = self.substrate.state if self.substrate is not None else self.state
        result = verify_operational_episode(
            oracle=self.episode.oracle,
            state=current_state,
            events=self.events,
            submission=submission,
            tool_calls=self.budget.calls,
            cost_spent=self.budget.spent,
        )
        self.closed = True
        return result
