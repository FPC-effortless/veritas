from __future__ import annotations

import json
from pathlib import Path

from investigation_world.observatory.models import CapabilityRun


class ObservatoryStore:
    """Append-only local store for capability runs; portable to object storage later."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.runs_path = self.root / "runs.jsonl"

    def append(self, run: CapabilityRun) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.runs_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(run.model_dump(mode="json"), sort_keys=True, default=str) + "\n"
            )

    def load(self) -> list[CapabilityRun]:
        if not self.runs_path.exists():
            return []
        result: list[CapabilityRun] = []
        with self.runs_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    result.append(CapabilityRun.model_validate_json(line))
        return result

    def for_lineage(self, longitudinal_key: str) -> list[CapabilityRun]:
        return sorted(
            (run for run in self.load() if run.cell.longitudinal_key == longitudinal_key),
            key=lambda run: (run.finished_at, run.run_id),
        )

    def latest_for_lineage(self, longitudinal_key: str) -> CapabilityRun | None:
        runs = self.for_lineage(longitudinal_key)
        return runs[-1] if runs else None
