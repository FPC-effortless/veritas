from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.operational.models import OperationalEpisode, OperationalRecord, WorldDomain


class OperationalStateEvent(BaseModel):
    """Append-only state transition in the persistent operational substrate."""

    model_config = ConfigDict(extra="forbid")
    sequence: int
    world_id: str
    domain: WorldDomain
    actor: str
    action_name: str
    before: dict[str, Any] = Field(default_factory=dict)
    changes: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)


class OperationalSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: str
    sequence: int
    state: dict[str, Any]
    mounted_world_ids: list[str]
    domains: list[WorldDomain]


class PersistentOperationalSubstrate:
    """Shared event-sourced state for multiple Veritas operational worlds.

    The substrate is intentionally learner-agnostic. It owns operational state,
    records, and transition history; runtimes and verifiers consume it without
    allowing a model or training algorithm to redefine truth.
    """

    def __init__(self, organization_id: str = "ORG-VERITAS-001", *, seed: int = 42):
        self.organization_id = organization_id
        self.seed = seed
        self._state: dict[str, Any] = {
            "organization.id": organization_id,
            "organization.seed": seed,
        }
        self._events: list[OperationalStateEvent] = []
        self._episodes: dict[str, OperationalEpisode] = {}
        self._records: dict[str, OperationalRecord] = {}

    @property
    def sequence(self) -> int:
        return len(self._events)

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    @property
    def mounted_world_ids(self) -> list[str]:
        return sorted(self._episodes)

    @property
    def domains(self) -> list[WorldDomain]:
        return sorted(
            {episode.task.domain for episode in self._episodes.values()},
            key=lambda domain: domain.value,
        )

    def mount_episode(self, episode: OperationalEpisode) -> None:
        """Mount one domain world without resetting already-persistent state."""
        existing_episode = self._episodes.get(episode.world_id)
        if existing_episode is not None:
            if existing_episode != episode:
                raise ValueError(
                    f"world ID {episode.world_id} is already mounted with different content"
                )
            return
        collisions = {
            key: (self._state[key], value)
            for key, value in episode.oracle.initial_state.items()
            if key in self._state and self._state[key] != value
        }
        if collisions:
            raise ValueError(
                f"state collision while mounting {episode.world_id}: {sorted(collisions)}"
            )
        changes = {
            key: value
            for key, value in episode.oracle.initial_state.items()
            if key not in self._state
        }
        self._episodes[episode.world_id] = episode
        for record in episode.records:
            existing = self._records.get(record.record_id)
            if existing is not None and existing != record:
                raise ValueError(f"record ID collision: {record.record_id}")
            self._records[record.record_id] = record
        if changes:
            self._append_event(
                world_id=episode.world_id,
                domain=episode.task.domain,
                actor="substrate",
                action_name="mount_world",
                changes=changes,
            )

    def mount_suite(self, episodes: list[OperationalEpisode]) -> None:
        for episode in episodes:
            self.mount_episode(episode)

    def episode(self, world_id: str) -> OperationalEpisode:
        try:
            return self._episodes[world_id]
        except KeyError as exc:
            raise KeyError(f"world not mounted: {world_id}") from exc

    def records(self, *, domain: WorldDomain | None = None) -> list[OperationalRecord]:
        if domain is None:
            return sorted(self._records.values(), key=lambda record: record.record_id)
        record_ids = {
            record.record_id
            for episode in self._episodes.values()
            if episode.task.domain == domain
            for record in episode.records
        }
        return sorted(
            [self._records[record_id] for record_id in record_ids],
            key=lambda record: record.record_id,
        )

    def _append_event(
        self,
        *,
        world_id: str,
        domain: WorldDomain,
        actor: str,
        action_name: str,
        changes: dict[str, Any],
        evidence_ids: list[str] | None = None,
        side_effects: list[str] | None = None,
    ) -> OperationalStateEvent:
        before = {key: self._state.get(key) for key in changes}
        self._state.update(changes)
        event = OperationalStateEvent(
            sequence=self.sequence + 1,
            world_id=world_id,
            domain=domain,
            actor=actor,
            action_name=action_name,
            before=before,
            changes=dict(changes),
            evidence_ids=list(evidence_ids or []),
            side_effects=list(side_effects or []),
        )
        self._events.append(event)
        return event

    def apply_changes(
        self,
        *,
        world_id: str,
        domain: WorldDomain,
        action_name: str,
        changes: dict[str, Any],
        actor: str = "agent",
        evidence_ids: list[str] | None = None,
        side_effects: list[str] | None = None,
    ) -> OperationalStateEvent | None:
        episode = self._episodes.get(world_id)
        if episode is None:
            raise ValueError(f"world not mounted: {world_id}")
        if episode.task.domain != domain:
            raise ValueError(
                f"domain mismatch for {world_id}: expected {episode.task.domain.value}, got {domain.value}"
            )
        if not changes and not side_effects:
            return None
        return self._append_event(
            world_id=world_id,
            domain=domain,
            actor=actor,
            action_name=action_name,
            changes=changes,
            evidence_ids=evidence_ids,
            side_effects=side_effects,
        )

    def history(
        self,
        *,
        domain: WorldDomain | None = None,
        world_id: str | None = None,
    ) -> list[OperationalStateEvent]:
        events = self._events
        if domain is not None:
            events = [event for event in events if event.domain == domain]
        if world_id is not None:
            events = [event for event in events if event.world_id == world_id]
        return [event.model_copy(deep=True) for event in events]

    def state_at(self, sequence: int) -> dict[str, Any]:
        if sequence < 0 or sequence > self.sequence:
            raise ValueError(f"sequence must be between 0 and {self.sequence}")
        state: dict[str, Any] = {
            "organization.id": self.organization_id,
            "organization.seed": self.seed,
        }
        for event in self._events[:sequence]:
            state.update(event.changes)
        return state

    def snapshot(self, sequence: int | None = None) -> OperationalSnapshot:
        resolved_sequence = self.sequence if sequence is None else sequence
        return OperationalSnapshot(
            organization_id=self.organization_id,
            sequence=resolved_sequence,
            state=self.state_at(resolved_sequence),
            mounted_world_ids=self.mounted_world_ids,
            domains=self.domains,
        )

    def fork_at(self, sequence: int | None = None) -> "PersistentOperationalSubstrate":
        """Create a deterministic replay/counterfactual branch at one event boundary."""
        resolved_sequence = self.sequence if sequence is None else sequence
        if resolved_sequence < 0 or resolved_sequence > self.sequence:
            raise ValueError(f"sequence must be between 0 and {self.sequence}")
        fork = PersistentOperationalSubstrate(self.organization_id, seed=self.seed)
        fork._episodes = dict(self._episodes)
        fork._records = dict(self._records)
        fork._events = [event.model_copy(deep=True) for event in self._events[:resolved_sequence]]
        fork._state = deepcopy(self.state_at(resolved_sequence))
        return fork

    def validate_integrity(self) -> bool:
        assert [event.sequence for event in self._events] == list(range(1, self.sequence + 1))
        assert self.state_at(self.sequence) == self._state
        assert set(self._episodes) == set(self.mounted_world_ids)
        return True
