from investigation_world.foundry.models import DistributionSplit, RolloutTrace, TraceEvent
from investigation_world.observatory.analysis import behavior_from_trace


def _trace(events: list[TraceEvent]) -> RolloutTrace:
    return RolloutTrace(
        trace_id="TRACE-RECOVERY",
        environment_version="cw-1",
        task_id="TASK-1",
        task_seed=1,
        split=DistributionSplit.IID_TEST,
        capability_tags=["recovery"],
        taskset_version="ts-1",
        harness_version="h-1",
        runtime_version="companyworld-runtime-v2",
        initial_state_hash="s0",
        final_state_hash="s0",
        events=events,
        total_reward=0.0,
        total_cost=0.0,
        termination_reason="test",
    )


def test_success_on_different_system_is_not_recovery():
    trace = _trace([
        TraceEvent(
            step=0,
            event_type="search_system_error",
            payload={
                "method": "search_system",
                "args": ["ERP", "ORD-1"],
                "kwargs": {},
                "success": False,
                "error_type": "RuntimeError",
                "error": "ERP unavailable",
            },
            state_hash_before="s0",
            state_hash_after="s0",
        ),
        TraceEvent(
            step=1,
            event_type="search_system",
            payload={
                "method": "search_system",
                "args": ["WMS", "ORD-1"],
                "kwargs": {},
                "success": True,
                "result": [],
            },
            state_hash_before="s0",
            state_hash_after="s0",
        ),
    ])

    behavior = behavior_from_trace(trace)
    assert behavior.failure_signals == 1
    assert behavior.recovery_events == 0


def test_retry_on_same_system_is_recovery():
    trace = _trace([
        TraceEvent(
            step=0,
            event_type="search_system_error",
            payload={
                "method": "search_system",
                "args": ["ERP", "ORD-1"],
                "kwargs": {},
                "success": False,
                "error_type": "RuntimeError",
                "error": "ERP unavailable",
            },
            state_hash_before="s0",
            state_hash_after="s0",
        ),
        TraceEvent(
            step=1,
            event_type="search_system",
            payload={
                "method": "search_system",
                "args": ["ERP", "ORD-1"],
                "kwargs": {},
                "success": True,
                "result": [],
            },
            state_hash_before="s0",
            state_hash_after="s0",
        ),
    ])

    assert behavior_from_trace(trace).recovery_events == 1
