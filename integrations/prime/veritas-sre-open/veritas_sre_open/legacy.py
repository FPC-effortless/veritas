from __future__ import annotations

import json
from pathlib import Path

from datasets import Dataset
import verifiers as vf

from .scoring import score_prediction


def load_environment() -> vf.Environment:
    """Compatibility entrypoint expected by current Environments Hub tooling."""

    records = json.loads(
        Path(__file__).with_name("public_tasks.json").read_text(encoding="utf-8")
    )
    dataset = Dataset.from_list(
        [
            {
                "question": record["prompt"],
                "answer": record["expected_causal_class"],
                "public_task_id": record["task_id"],
            }
            for record in records
        ]
    )

    async def causal_classification(completion, answer, **kwargs) -> float:
        del kwargs
        if isinstance(completion, list) and completion:
            last = completion[-1]
            raw = last.get("content", "") if isinstance(last, dict) else str(last)
        else:
            raw = completion
        return score_prediction(raw, str(answer))

    rubric = vf.Rubric(funcs=[causal_classification])
    return vf.SingleTurnEnv(dataset=dataset, rubric=rubric)
