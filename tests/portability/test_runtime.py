from __future__ import annotations

import pytest

from investigation_world.portability.runtime import SREPortableRuntime
from investigation_world.portability.sre_private import SREPrivatePortableTask


def _task() -> SREPrivatePortableTask:
    return SREPrivatePortableTask(
        task_id="PTASK-FIXTURE",
        seed=17,
        prompt="Classify the incident.",
        expected_causal_class="capacity",
        public_digest="a" * 64,
    )


def test_same_task_and_seed_reproduce_same_initial_state() -> None:
    runtime = SREPortableRuntime(environment_version="sre-v4", tasks=[_task()])

    first = runtime.start("PTASK-FIXTURE", seed=17, invocation="one")
    second = runtime.reset("PTASK-FIXTURE", seed=17, invocation="two")

    assert first.prompt == second.prompt
    assert first.initial_state_digest == second.initial_state_digest
    assert first.run_id != second.run_id


def test_seed_mismatch_is_rejected() -> None:
    runtime = SREPortableRuntime(environment_version="sre-v4", tasks=[_task()])
    with pytest.raises(ValueError, match="seed mismatch"):
        runtime.start("PTASK-FIXTURE", seed=18)


def test_grading_is_deterministic_and_parse_aware() -> None:
    runtime = SREPortableRuntime(environment_version="sre-v4", tasks=[_task()])
    start = runtime.start("PTASK-FIXTURE", seed=17)

    correct = runtime.grade(start, '{"causal_class":"capacity"}')
    wrong = runtime.grade(start, '{"causal_class":"regression"}')
    malformed = runtime.grade(start, "not-json")

    assert correct.reward == 1.0
    assert correct.parsed is True
    assert wrong.reward == 0.0
    assert wrong.parsed is True
    assert malformed.reward == 0.0
    assert malformed.parsed is False
    assert runtime.grade(start, '{"causal_class":"capacity"}').terminal_state_digest == correct.terminal_state_digest
