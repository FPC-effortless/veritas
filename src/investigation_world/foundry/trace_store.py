from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from investigation_world.foundry.models import RolloutTrace


def append_trace(path: str | Path, trace: RolloutTrace) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace.model_dump(mode="json"), sort_keys=True, default=str) + "\n")


def load_traces(path: str | Path) -> list[RolloutTrace]:
    target = Path(path)
    if not target.exists():
        return []
    traces: list[RolloutTrace] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                traces.append(RolloutTrace.model_validate_json(line))
    return traces


def trace_cost(traces: Iterable[RolloutTrace]) -> float:
    return sum(item.total_cost for item in traces)
