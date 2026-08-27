from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from investigation_world.frontier.models import FrontierCalibrationObservation  # noqa: E402
from investigation_world.frontier.sre_runner import (  # noqa: E402
    paired_comparison_from_private_sre_reports,
)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Reduce two private same-panel SRE reports to a buyer-safe paired 2x2 "
            "capability comparison"
        )
    )
    parser.add_argument("--weak-report", type=Path, required=True)
    parser.add_argument("--strong-report", type=Path, required=True)
    parser.add_argument("--weak-observation", type=Path, required=True)
    parser.add_argument("--strong-observation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    weak_observation = FrontierCalibrationObservation.model_validate(
        _read(args.weak_observation)
    )
    strong_observation = FrontierCalibrationObservation.model_validate(
        _read(args.strong_observation)
    )
    comparison = paired_comparison_from_private_sre_reports(
        _read(args.weak_report),
        _read(args.strong_report),
        weak_observation=weak_observation,
        strong_observation=strong_observation,
        input_artifact_hashes={
            "weak_report": _sha(args.weak_report),
            "strong_report": _sha(args.strong_report),
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(comparison.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
