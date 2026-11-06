from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.companyworld.models import CompanySystem, CompanyWorldEpisode
from investigation_world.companyworld.runtime import SYSTEM_TOOL_COSTS, CompanyWorldRuntime


class ScheduledToolFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    system: CompanySystem | None = None
    at_step: int = Field(default=0, ge=0)
    persistent: bool = False
    scope: Literal["system", "aggregator", "global"] = "system"

    @model_validator(mode="after")
    def validate_scope(self) -> "ScheduledToolFailure":
        if self.scope == "system" and self.system is None:
            raise ValueError("system-scoped tool failure requires a system")
        return self


class ScheduledPermissionChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    system: CompanySystem
    at_step: int = Field(default=0, ge=0)
    action: Literal["revoke", "restore"] = "revoke"


def _tool_failures(episode: CompanyWorldEpisode) -> list[ScheduledToolFailure]:
    raw = episode.task.constraints.get("foundry_tool_failures", [])
    if not isinstance(raw, list):
        raise ValueError("foundry_tool_failures must be a list")
    return [ScheduledToolFailure.model_validate(item) for item in raw]


def _permission_changes(episode: CompanyWorldEpisode) -> list[ScheduledPermissionChange]:
    raw = episode.task.constraints.get("foundry_permission_change")
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    return [ScheduledPermissionChange.model_validate(item) for item in items]


class InterventionAwareCompanyWorldRuntime(CompanyWorldRuntime):
    """CompanyWorld runtime that executes Observatory failure/permission schedules."""

    def __init__(
        self,
        episode: CompanyWorldEpisode,
        *,
        total_cost: int = 40,
        max_tool_calls: int = 30,
    ):
        super().__init__(episode, total_cost=total_cost, max_tool_calls=max_tool_calls)
        self.operation_index = 0
        self.tool_failures = _tool_failures(episode)
        self.permission_changes = sorted(
            _permission_changes(episode),
            key=lambda item: (item.at_step, item.system.value, item.action),
        )
        self.revoked_systems: set[CompanySystem] = set()
        self._applied_permission_changes: set[int] = set()

    def state_snapshot(self) -> dict[str, Any]:
        return {
            "budget": self.budget_snapshot(),
            "operation_index": self.operation_index,
            "revoked_systems": sorted(item.value for item in self.revoked_systems),
            "applied_permission_changes": sorted(self._applied_permission_changes),
        }

    def _apply_permission_changes(self, step: int) -> None:
        for index, change in enumerate(self.permission_changes):
            if index in self._applied_permission_changes or change.at_step > step:
                continue
            if change.action == "revoke":
                self.revoked_systems.add(change.system)
            else:
                self.revoked_systems.discard(change.system)
            self._applied_permission_changes.add(index)

    def _active_failure(
        self,
        step: int,
        system: CompanySystem | None,
        operation_scope: Literal["system", "aggregator"],
    ) -> ScheduledToolFailure | None:
        for failure in self.tool_failures:
            if failure.scope == "global":
                applies = True
            elif operation_scope == "aggregator":
                applies = failure.scope == "aggregator"
            else:
                applies = failure.scope == "system" and failure.system == system
            if not applies:
                continue
            if failure.persistent and step >= failure.at_step:
                return failure
            if not failure.persistent and step == failure.at_step:
                return failure
        return None

    def _before_operation(
        self,
        system: CompanySystem | None,
        *,
        operation_scope: Literal["system", "aggregator"] = "system",
    ) -> int:
        self._ensure_open()
        step = self.operation_index
        self.operation_index += 1
        self._apply_permission_changes(step)
        failure = self._active_failure(step, system, operation_scope)
        if failure is not None:
            target = failure.system.value if failure.system is not None else failure.scope
            raise RuntimeError(
                f"intervention tool failure: {target} unavailable at operation {step}"
            )
        if system is not None and system in self.revoked_systems:
            raise PermissionError(
                f"intervention permission change: access to {system.value} revoked at operation {step}"
            )
        return step

    def search_system(
        self,
        system: CompanySystem,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        self._before_operation(system)
        if system not in self.episode.task.permitted_systems:
            return []
        self._charge(SYSTEM_TOOL_COSTS[system])
        return [
            record.model_dump(mode="json")
            for record in self.index.search(query, system=system, limit=limit)
        ]

    def search_all(self, query: str, limit: int = 10) -> list[dict]:
        # A system-specific outage must not implicitly disable the cross-system aggregator. The
        # aggregator can still search healthy systems and filters any revoked systems below.
        self._before_operation(None, operation_scope="aggregator")
        self._charge(3)
        candidates = self.index.search(query, limit=100)
        return [
            record.model_dump(mode="json")
            for record in candidates
            if record.system not in self.revoked_systems
        ][: max(1, min(limit, 100))]

    def open_record(self, record_id: str) -> dict:
        record = self.index.get(record_id)
        system = record.system if record is not None else None
        self._before_operation(system)
        self._charge(1)
        if record is None:
            raise KeyError(record_id)
        if record.system in self.revoked_systems:
            raise PermissionError(
                f"intervention permission change: access to {record.system.value} revoked"
            )
        return record.model_dump(mode="json")
