from investigation_world.portable_runtime import (
    PortableInvocationKind,
    PortableRuntimeFailureCode,
    PortableStepRequest,
)

from test_portable_runtime import _budget_map, _runtime


def test_unpermitted_search_preserves_native_empty_unmetered_permission_result() -> None:
    runtime = _runtime()
    initial = runtime.reset(seed=41)

    result = runtime.step(
        PortableStepRequest(
            kind=PortableInvocationKind.OPERATION,
            name="search",
            arguments={"system": "UNPERMITTED", "query": "pending order"},
        )
    )

    assert result.failure is None
    assert result.observation == []
    assert result.state_digest == initial.state_digest
    assert _budget_map(runtime) == {"cost": (0, 10), "tool_calls": (0, 8)}


def test_unpermitted_search_precedes_closed_state_as_native_runtime_requires() -> None:
    runtime = _runtime()
    runtime.reset(seed=43)
    submitted = runtime.submit({"evidence_ids": ["record-001"]})
    assert submitted.terminated is True

    unpermitted = runtime.step(
        PortableStepRequest(
            kind=PortableInvocationKind.OPERATION,
            name="search",
            arguments={"system": "UNPERMITTED", "query": "pending order"},
        )
    )
    assert unpermitted.failure is None
    assert unpermitted.observation == []
    assert unpermitted.terminated is True

    permitted = runtime.step(
        PortableStepRequest(
            kind=PortableInvocationKind.OPERATION,
            name="search",
            arguments={"system": "ERP", "query": "pending order"},
        )
    )
    assert permitted.failure is not None
    assert permitted.failure.code == PortableRuntimeFailureCode.EPISODE_TERMINATED
