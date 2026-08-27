from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash


class PortableMeteringEventKind(StrEnum):
    EPISODE_STARTED = "episode_started"
    EPISODE_GRADED = "episode_graded"


class PortableMeteringEvent(BaseModel):
    """Vendor-neutral usage event emitted by a portable environment runtime.

    The event deliberately contains no customer identity, billing data, prompt text, hidden truth,
    or provider credential. Consumers may attach those concerns outside the portability layer.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = ""
    kind: PortableMeteringEventKind
    run_id: str
    environment_id: str
    environment_version: str
    task_id: str
    seed: int
    state_digest: str
    reward: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_event_id(self) -> "PortableMeteringEvent":
        payload = self.model_dump(mode="json", exclude={"event_id"})
        expected = f"PMETER-{stable_hash(payload)[:24].upper()}"
        if self.event_id and self.event_id != expected:
            raise ValueError("portable metering event ID does not match immutable contents")
        object.__setattr__(self, "event_id", expected)
        return self


class PortableMeteringHook(Protocol):
    def __call__(self, event: PortableMeteringEvent) -> None: ...


class InMemoryPortableMeteringSink:
    """Minimal reference sink for tests, local integrations, and buyer pilots."""

    def __init__(self) -> None:
        self.events: list[PortableMeteringEvent] = []

    def __call__(self, event: PortableMeteringEvent) -> None:
        self.events.append(event)
