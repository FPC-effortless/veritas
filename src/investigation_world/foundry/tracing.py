from __future__ import annotations

from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel

from investigation_world.foundry.models import FoundryTaskMetadata, RolloutTrace, TraceEvent, stable_hash


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_dump(item) for item in value]
    if isinstance(value, list):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _dump(child) for key, child in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _state_payload(runtime: Any) -> Any:
    snapshot = getattr(runtime, "state_snapshot", None)
    if callable(snapshot):
        try:
            return _dump(snapshot())
        except TypeError:
            pass
    scenario = getattr(runtime, "scenario", None)
    case_status = getattr(runtime, "case_status", None)
    if scenario is not None and callable(case_status):
        return {
            case.case_id: _dump(case_status(case.case_id))
            for case in sorted(scenario.cases, key=lambda item: item.case_id)
        }
    budget = getattr(runtime, "budget_snapshot", None)
    return {"budget": _dump(budget())} if callable(budget) else {}


def _budget_spent(runtime: Any) -> float:
    budget = getattr(runtime, "budget_snapshot", None)
    if not callable(budget):
        return 0.0
    payload = budget()
    return float(payload.get("spent", 0.0)) if isinstance(payload, dict) else 0.0


def _numeric_components(verification: Any) -> dict[str, float]:
    payload = _dump(verification)
    if not isinstance(payload, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in payload.items():
        if isinstance(value, bool):
            result[key] = 1.0 if value else 0.0
        elif isinstance(value, (int, float)):
            result[key] = float(value)
    return result


class TracingRuntimeProxy:
    """Record public runtime operations without changing wrapped runtime semantics."""

    def __init__(
        self,
        runtime: Any,
        metadata: FoundryTaskMetadata,
        *,
        environment_version: str,
        trace_id: str | None = None,
    ):
        self.runtime = runtime
        self.metadata = metadata
        self.environment_version = environment_version
        self.trace_id = trace_id or f"TRACE-{stable_hash([metadata.task_id, metadata.seed, environment_version])[:16].upper()}"
        self.events: list[TraceEvent] = []
        self.initial_state_hash = stable_hash(_state_payload(runtime))
        self.verification: Any | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.runtime, name)

    def _record_call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        function = getattr(self.runtime, method)
        before = stable_hash(_state_payload(self.runtime))
        spent_before = _budget_spent(self.runtime)
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            after = stable_hash(_state_payload(self.runtime))
            spent_after = _budget_spent(self.runtime)
            self.events.append(
                TraceEvent(
                    step=len(self.events),
                    event_type=f"{method}_error",
                    payload={
                        "method": method,
                        "args": _dump(list(args)),
                        "kwargs": _dump(kwargs),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "success": False,
                    },
                    state_hash_before=before,
                    state_hash_after=after,
                    cost=max(0.0, spent_after - spent_before),
                )
            )
            raise
        after = stable_hash(_state_payload(self.runtime))
        spent_after = _budget_spent(self.runtime)
        self.events.append(
            TraceEvent(
                step=len(self.events),
                event_type=method,
                payload={
                    "method": method,
                    "args": _dump(list(args)),
                    "kwargs": _dump(kwargs),
                    "result": _dump(result),
                    "success": True,
                },
                state_hash_before=before,
                state_hash_after=after,
                cost=max(0.0, spent_after - spent_before),
            )
        )
        return result

    def search_system(self, *args: Any, **kwargs: Any) -> Any:
        return self._record_call("search_system", *args, **kwargs)

    def search(self, *args: Any, **kwargs: Any) -> Any:
        return self._record_call("search", *args, **kwargs)

    def search_all(self, *args: Any, **kwargs: Any) -> Any:
        return self._record_call("search_all", *args, **kwargs)

    def open_record(self, *args: Any, **kwargs: Any) -> Any:
        return self._record_call("open_record", *args, **kwargs)

    def case_status(self, *args: Any, **kwargs: Any) -> Any:
        return self._record_call("case_status", *args, **kwargs)

    def act(self, *args: Any, **kwargs: Any) -> Any:
        return self._record_call("act", *args, **kwargs)

    def advance(self, *args: Any, **kwargs: Any) -> Any:
        return self._record_call("advance", *args, **kwargs)

    def handoff(self, *args: Any, **kwargs: Any) -> Any:
        return self._record_call("handoff", *args, **kwargs)

    def submit(self, *args: Any, **kwargs: Any) -> Any:
        verification = self._record_call("submit", *args, **kwargs)
        self.verification = verification
        return verification

    def trace(self, *, termination_reason: str = "submitted") -> RolloutTrace:
        final_payload = _state_payload(self.runtime)
        reward = float(getattr(self.verification, "overall_reward", 0.0)) if self.verification is not None else 0.0
        return RolloutTrace(
            trace_id=self.trace_id,
            environment_version=self.environment_version,
            task_id=self.metadata.task_id,
            task_seed=self.metadata.seed,
            split=self.metadata.split,
            capability_tags=self.metadata.capability_tags,
            taskset_version=self.metadata.taskset_version,
            harness_version=self.metadata.harness_version,
            runtime_version=self.metadata.runtime_version,
            initial_state_hash=self.initial_state_hash,
            events=list(self.events),
            verifier_components=_numeric_components(self.verification),
            total_reward=reward,
            final_state_hash=stable_hash(final_payload),
            termination_reason=termination_reason,
            total_cost=sum(item.cost for item in self.events),
        )


def _company_system(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    from investigation_world.companyworld.models import CompanySystem
    try:
        return CompanySystem(value)
    except ValueError:
        return value


def _decode_replay_arg(method: str, position: int, value: Any) -> Any:
    if method == "act" and isinstance(value, dict) and "action_type" in value:
        from investigation_world.companyworld.interactive_models import OperationalAction
        return OperationalAction.model_validate(value)
    if method == "search_system":
        if position in {0, 1}:
            return _company_system(value)
    return value


def _decode_replay_kwargs(method: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(kwargs)
    if method in {"search", "search_system"} and "system" in decoded:
        decoded["system"] = _company_system(decoded["system"])
    return decoded


def replay_trace_prefix(runtime: Any, trace: RolloutTrace, *, through_step: int | None = None) -> Any:
    """Replay recorded successful operations on a fresh runtime, excluding submission.

    Failed trace events are skipped because replaying them is not guaranteed to reproduce an
    external/intervention failure unless the fresh runtime carries the same failure schedule.
    `through_step` is inclusive. Replay starts from reset rather than restoring private runtime
    state, so it stays inside public runtime APIs and deterministic episode semantics.
    """
    for event in trace.events:
        if through_step is not None and event.step > through_step:
            break
        method = event.payload.get("method")
        if (
            method == "submit"
            or not isinstance(method, str)
            or event.payload.get("success") is False
        ):
            continue
        function = getattr(runtime, method)
        raw_args = event.payload.get("args", [])
        args = [
            _decode_replay_arg(method, index, value)
            for index, value in enumerate(raw_args if isinstance(raw_args, list) else [])
        ]
        raw_kwargs = event.payload.get("kwargs", {})
        kwargs = _decode_replay_kwargs(method, raw_kwargs if isinstance(raw_kwargs, dict) else {})
        function(*args, **kwargs)
    return runtime


def execute_counterfactual(
    runtime_factory: Callable[[], Any],
    trace: RolloutTrace,
    *,
    branch_step: int,
    alternate_method: str,
    alternate_args: list[Any],
    alternate_kwargs: dict[str, Any] | None = None,
) -> Any:
    """Replay the successful prefix before `branch_step`, then execute an alternate operation."""
    runtime = runtime_factory()
    replay_trace_prefix(runtime, trace, through_step=branch_step - 1)
    decoded = [
        _decode_replay_arg(alternate_method, index, _dump(value))
        for index, value in enumerate(alternate_args)
    ]
    kwargs = _decode_replay_kwargs(alternate_method, _dump(alternate_kwargs or {}))
    getattr(runtime, alternate_method)(*decoded, **kwargs)
    return runtime
