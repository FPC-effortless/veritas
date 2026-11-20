"""Native synthetic-life domain types. Only Observation and Receipt cross the port."""
from dataclasses import dataclass, field
from typing import Any

PEOPLE = tuple(f"p{i}" for i in range(8))
LOCATIONS = ("home", "school", "market")
OBJECTS = tuple(f"o{i}" for i in range(6))
MILESTONES = {12: "adolescence", 24: "adult"}

@dataclass(frozen=True, slots=True)
class Action:
    kind: str
    target: str
    value: Any = None
    evidence: tuple[str, ...] = ()
    expected_version: int | None = None
    request_id: str | None = None

@dataclass(frozen=True, slots=True)
class Observation:
    seq: int
    tick: int
    kind: str
    source: str
    scope: str
    payload: dict = field(default_factory=dict)
    parents: tuple[str, ...] = ()
    id: str = ""

@dataclass(frozen=True, slots=True)
class Receipt:
    action: str
    authorized: bool
    applied: bool
    reason: str
    observation_id: str
    cost: int = 1
    replayed: bool = False
