from __future__ import annotations

from investigation_world.portability.metering import (
    InMemoryPortableMeteringSink,
    PortableMeteringEvent,
    PortableMeteringEventKind,
)
from investigation_world.portability.runtime import SREPortableRuntime
from investigation_world.portability.sre_private import SREPrivatePortableTask


def _task() -> SREPrivatePortableTask:
    return SREPrivatePortableTask(
        task_id="PTASK-METERING-FIXTURE",
        seed=41,
        prompt="Private prompt that must not enter metering.",
        expected_causal_class="capacity",
        public_digest="b" * 64,
    )


def test_runtime_emits_buyer_safe_usage_events() -> None:
    sink = InMemoryPortableMeteringSink()
    runtime = SREPortableRuntime(
        environment_version="sre-v4",
        tasks=[_task()],
        metering_hook=sink,
    )

    start = runtime.start("PTASK-METERING-FIXTURE", seed=41, invocation="pilot-run")
    grade = runtime.grade(start, '{"causal_class":"capacity"}')

    assert [event.kind for event in sink.events] == [
        PortableMeteringEventKind.EPISODE_STARTED,
        PortableMeteringEventKind.EPISODE_GRADED,
    ]
    assert sink.events[0].run_id == start.run_id
    assert sink.events[1].run_id == grade.run_id
    assert sink.events[1].reward == 1.0

    serialized = "\n".join(event.model_dump_json() for event in sink.events)
    assert "Private prompt" not in serialized
    assert "expected_causal_class" not in serialized
    assert '"capacity"' not in serialized
    assert "causal_class" not in serialized


def test_metering_event_identity_is_content_derived() -> None:
    payload = dict(
        kind=PortableMeteringEventKind.EPISODE_STARTED,
        run_id="PRUN-FIXTURE",
        environment_id="veritas.sre.causal-classification",
        environment_version="sre-v4",
        task_id="PTASK-FIXTURE",
        seed=7,
        state_digest="a" * 64,
    )
    first = PortableMeteringEvent(**payload)
    second = PortableMeteringEvent(**payload)
    assert first.event_id == second.event_id
    assert first.event_id.startswith("PMETER-")


def test_different_invocations_produce_distinct_metered_runs() -> None:
    sink = InMemoryPortableMeteringSink()
    runtime = SREPortableRuntime(
        environment_version="sre-v4",
        tasks=[_task()],
        metering_hook=sink,
    )

    first = runtime.start("PTASK-METERING-FIXTURE", seed=41, invocation="one")
    second = runtime.start("PTASK-METERING-FIXTURE", seed=41, invocation="two")

    assert first.initial_state_digest == second.initial_state_digest
    assert first.run_id != second.run_id
    assert sink.events[0].event_id != sink.events[1].event_id
