from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.models import RolloutTrace, stable_hash
from investigation_world.observatory.analysis import capability_run_from_trace
from investigation_world.observatory.models import CapabilityRun, LongitudinalCell, ModelSpec
from investigation_world.observatory.store import ObservatoryStore


class ProviderUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost: float = Field(default=0.0, ge=0.0)


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str
    cell_id: str
    model: ModelSpec
    call_index: int = Field(ge=0)
    payload: Any = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str
    output: Any = None
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    latency_s: float = Field(default=0.0, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str
    call_index: int = Field(ge=0)
    latency_s: float = Field(ge=0.0)
    usage: ProviderUsage


class ProviderSessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider_id: str
    model_id: str
    model_snapshot: str
    calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost: float = Field(ge=0.0)
    latency_s: float = Field(ge=0.0)
    call_records: list[ProviderCallRecord] = Field(default_factory=list)


@runtime_checkable
class ModelProviderAdapter(Protocol):
    provider_id: str

    def invoke(self, request: ModelRequest) -> ModelResponse:
        ...


ProviderCallable = Callable[[ModelRequest], ModelResponse | Any]


class CallableModelProvider:
    """Adapter for SDK clients, local models, HTTP clients, or deterministic test doubles."""

    def __init__(self, provider_id: str, function: ProviderCallable):
        self.provider_id = provider_id
        self.function = function

    def invoke(self, request: ModelRequest) -> ModelResponse:
        started = time.perf_counter()
        result = self.function(request)
        elapsed = max(0.0, time.perf_counter() - started)
        if isinstance(result, ModelResponse):
            if result.request_id != request.request_id:
                raise ValueError("provider response request_id does not match request")
            if result.latency_s > 0.0:
                return result
            return result.model_copy(update={"latency_s": elapsed})
        return ModelResponse(request_id=request.request_id, output=result, latency_s=elapsed)


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, ModelProviderAdapter] = {}

    def register(self, adapter: ModelProviderAdapter) -> None:
        if not adapter.provider_id:
            raise ValueError("provider_id must be non-empty")
        if adapter.provider_id in self._providers:
            raise ValueError(f"provider already registered: {adapter.provider_id}")
        self._providers[adapter.provider_id] = adapter

    def resolve(self, provider_id: str) -> ModelProviderAdapter:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"no provider adapter registered for {provider_id!r}") from exc


class ProviderSession:
    """Per-cell model session that instruments calls without exposing provider secrets to traces."""

    def __init__(self, cell: LongitudinalCell, adapter: ModelProviderAdapter):
        if adapter.provider_id != cell.model.provider:
            raise ValueError(
                f"provider adapter {adapter.provider_id!r} cannot execute model provider "
                f"{cell.model.provider!r}"
            )
        self.cell = cell
        self.adapter = adapter
        self._records: list[ProviderCallRecord] = []

    def generate(
        self,
        payload: Any,
        *,
        parameters: dict[str, Any] | None = None,
    ) -> ModelResponse:
        call_index = len(self._records)
        request_id = f"REQ-{stable_hash([self.cell.cell_id, call_index])[:20].upper()}"
        request = ModelRequest(
            request_id=request_id,
            cell_id=self.cell.cell_id,
            model=self.cell.model,
            call_index=call_index,
            payload=payload,
            parameters=parameters or {},
        )
        response = self.adapter.invoke(request)
        if response.request_id != request_id:
            raise ValueError("provider response request_id does not match session request")
        self._records.append(
            ProviderCallRecord(
                request_id=request_id,
                call_index=call_index,
                latency_s=response.latency_s,
                usage=response.usage,
            )
        )
        return response

    def summary(self) -> ProviderSessionSummary:
        records = list(self._records)
        return ProviderSessionSummary(
            provider_id=self.adapter.provider_id,
            model_id=self.cell.model.model_id,
            model_snapshot=self.cell.model.snapshot,
            calls=len(records),
            input_tokens=sum(item.usage.input_tokens for item in records),
            output_tokens=sum(item.usage.output_tokens for item in records),
            total_tokens=sum(item.usage.total_tokens for item in records),
            cost=sum(item.usage.cost for item in records),
            latency_s=sum(item.latency_s for item in records),
            call_records=records,
        )


class HarnessRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace: RolloutTrace
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class HarnessAdapter(Protocol):
    harness_id: str
    version: str

    def run(
        self,
        cell: LongitudinalCell,
        provider: ProviderSession,
        runtime: Any,
    ) -> HarnessRunResult | RolloutTrace:
        ...


HarnessCallable = Callable[
    [LongitudinalCell, ProviderSession, Any],
    HarnessRunResult | RolloutTrace,
]


class CallableHarnessAdapter:
    def __init__(self, harness_id: str, version: str, function: HarnessCallable):
        self.harness_id = harness_id
        self.version = version
        self.function = function

    def run(
        self,
        cell: LongitudinalCell,
        provider: ProviderSession,
        runtime: Any,
    ) -> HarnessRunResult | RolloutTrace:
        return self.function(cell, provider, runtime)


class HarnessRegistry:
    def __init__(self):
        self._harnesses: dict[tuple[str, str], HarnessAdapter] = {}

    def register(self, adapter: HarnessAdapter) -> None:
        key = (adapter.harness_id, adapter.version)
        if not all(key):
            raise ValueError("harness id and version must be non-empty")
        if key in self._harnesses:
            raise ValueError(f"harness already registered: {key[0]}@{key[1]}")
        self._harnesses[key] = adapter

    def resolve(self, harness_id: str, version: str) -> HarnessAdapter:
        key = (harness_id, version)
        try:
            return self._harnesses[key]
        except KeyError as exc:
            raise KeyError(f"no harness adapter registered for {harness_id!r}@{version!r}") from exc


@runtime_checkable
class RuntimeFactory(Protocol):
    world_id: str
    world_version: str

    def create(self, cell: LongitudinalCell) -> Any:
        ...


RuntimeCallable = Callable[[LongitudinalCell], Any]


class CallableRuntimeFactory:
    def __init__(self, world_id: str, world_version: str, function: RuntimeCallable):
        self.world_id = world_id
        self.world_version = world_version
        self.function = function

    def create(self, cell: LongitudinalCell) -> Any:
        return self.function(cell)


class RuntimeRegistry:
    def __init__(self):
        self._factories: dict[tuple[str, str], RuntimeFactory] = {}

    def register(self, factory: RuntimeFactory) -> None:
        key = (factory.world_id, factory.world_version)
        if not all(key):
            raise ValueError("world id and version must be non-empty")
        if key in self._factories:
            raise ValueError(f"runtime factory already registered: {key[0]}@{key[1]}")
        self._factories[key] = factory

    def create(self, cell: LongitudinalCell) -> Any:
        key = (cell.world.world_id, cell.world.version)
        try:
            factory = self._factories[key]
        except KeyError as exc:
            raise KeyError(f"no runtime factory registered for {key[0]!r}@{key[1]!r}") from exc
        return factory.create(cell)


@dataclass
class ExecutionRegistry:
    providers: ProviderRegistry = field(default_factory=ProviderRegistry)
    harnesses: HarnessRegistry = field(default_factory=HarnessRegistry)
    runtimes: RuntimeRegistry = field(default_factory=RuntimeRegistry)


class ObservatoryExecutionEngine:
    """Resolve one cell into runtime + provider + harness and produce a CapabilityRun."""

    def __init__(
        self,
        registry: ExecutionRegistry,
        *,
        store: ObservatoryStore | None = None,
    ):
        self.registry = registry
        self.store = store

    def execute_cell(self, cell: LongitudinalCell, *, persist: bool = True) -> CapabilityRun:
        provider_adapter = self.registry.providers.resolve(cell.model.provider)
        harness = self.registry.harnesses.resolve(cell.harness.harness_id, cell.harness.version)
        runtime = self.registry.runtimes.create(cell)
        provider_session = ProviderSession(cell, provider_adapter)

        started = time.time()
        result = harness.run(cell, provider_session, runtime)
        finished = time.time()
        if isinstance(result, RolloutTrace):
            harness_result = HarnessRunResult(trace=result)
        elif isinstance(result, HarnessRunResult):
            harness_result = result
        else:
            raise TypeError("harness must return RolloutTrace or HarnessRunResult")

        metadata = dict(harness_result.metadata)
        metadata["provider_session"] = provider_session.summary().model_dump(mode="json")
        metadata["executor"] = {
            "harness_id": harness.harness_id,
            "harness_version": harness.version,
        }
        run = capability_run_from_trace(
            cell,
            harness_result.trace,
            started_at=datetime.fromtimestamp(started, tz=timezone.utc),
            finished_at=datetime.fromtimestamp(finished, tz=timezone.utc),
            metadata=metadata,
        )
        if persist and self.store is not None:
            self.store.append(run)
        return run
