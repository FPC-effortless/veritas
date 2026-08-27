from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.commercial.sre_evaluation import parse_sre_prediction
from investigation_world.portability.identity import portable_run_id, state_digest
from investigation_world.portability.sre import SRE_PORTABLE_ENVIRONMENT_ID
from investigation_world.portability.sre_private import SREPrivatePortableTask


class PortableEpisodeStart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    task_id: str
    seed: int
    prompt: str
    initial_state_digest: str


class PortableGradeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    task_id: str
    reward: float = Field(ge=0.0, le=1.0)
    parsed: bool
    terminal_state_digest: str


class SREPortableRuntime:
    def __init__(self, *, environment_version: str, tasks: list[SREPrivatePortableTask]) -> None:
        if not tasks:
            raise ValueError("portable SRE runtime requires at least one private task")
        by_id = {task.task_id: task for task in tasks}
        if len(by_id) != len(tasks):
            raise ValueError("portable SRE runtime task IDs must be unique")
        self.environment_version = environment_version
        self._tasks = by_id

    def start(self, task_id: str, *, seed: int, invocation: str = "default") -> PortableEpisodeStart:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"unknown portable SRE task: {task_id}")
        if seed != task.seed:
            raise ValueError(
                f"portable SRE task seed mismatch for {task_id}: expected {task.seed}, got {seed}"
            )
        run_id = portable_run_id(
            environment_id=SRE_PORTABLE_ENVIRONMENT_ID,
            environment_version=self.environment_version,
            task_id=task_id,
            seed=seed,
            invocation=invocation,
        )
        hidden_state = {
            "environment_id": SRE_PORTABLE_ENVIRONMENT_ID,
            "environment_version": self.environment_version,
            "task_id": task.task_id,
            "seed": task.seed,
            "prompt": task.prompt,
            "expected_causal_class": task.expected_causal_class,
        }
        return PortableEpisodeStart(
            run_id=run_id,
            task_id=task.task_id,
            seed=task.seed,
            prompt=task.prompt,
            initial_state_digest=state_digest(hidden_state),
        )

    def reset(self, task_id: str, *, seed: int, invocation: str = "default") -> PortableEpisodeStart:
        return self.start(task_id, seed=seed, invocation=invocation)

    def grade(
        self,
        start: PortableEpisodeStart,
        answer: str,
    ) -> PortableGradeResult:
        task = self._tasks.get(start.task_id)
        if task is None:
            raise KeyError(f"unknown portable SRE task: {start.task_id}")
        replay = self.start(start.task_id, seed=start.seed, invocation="grade-validation")
        if replay.initial_state_digest != start.initial_state_digest:
            raise RuntimeError("portable SRE initial state no longer reproduces for grading")

        prediction = parse_sre_prediction(answer)
        predicted_value = prediction.value if prediction is not None else None
        reward = float(predicted_value == task.expected_causal_class)
        terminal_state = {
            "initial_state_digest": start.initial_state_digest,
            "answer": answer,
            "prediction": predicted_value,
            "reward": reward,
        }
        return PortableGradeResult(
            run_id=start.run_id,
            task_id=start.task_id,
            reward=reward,
            parsed=prediction is not None,
            terminal_state_digest=state_digest(terminal_state),
        )
