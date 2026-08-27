from __future__ import annotations

import json
from pathlib import Path

import verifiers.v1 as vf

from .scoring import score_prediction


class SREOpenData(vf.TaskData):
    expected_causal_class: str
    public_task_id: str


class SREOpenTask(vf.Task[SREOpenData, vf.State, vf.TaskConfig]):
    @vf.reward
    async def causal_classification(self, trace: vf.Trace) -> float:
        return score_prediction(trace.last_reply, self.data.expected_causal_class)


class SREOpenTaskset(vf.Taskset[SREOpenTask, vf.TasksetConfig]):
    """Twelve project-authored synthetic tasks for public integration/evaluation smoke tests."""

    def load(self) -> list[SREOpenTask]:
        records = json.loads(
            Path(__file__).with_name("public_tasks.json").read_text(encoding="utf-8")
        )
        return [
            SREOpenTask(
                SREOpenData(
                    idx=index,
                    prompt=record["prompt"],
                    expected_causal_class=record["expected_causal_class"],
                    public_task_id=record["task_id"],
                ),
                self.config.task,
            )
            for index, record in enumerate(records)
        ]
