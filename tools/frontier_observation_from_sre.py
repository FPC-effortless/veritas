from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from investigation_world.frontier.sre_runner import observation_from_sre_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an aggregate/private SRE evaluation report into Frontier calibration evidence"
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--tier", required=True)
    parser.add_argument("--model-snapshot")
    parser.add_argument("--harness", required=True)
    parser.add_argument("--comparison-group-id")
    parser.add_argument("--transport-failures", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    observation = observation_from_sre_report(
        report,
        tier=args.tier,
        model_snapshot=args.model_snapshot,
        harness_identity=args.harness,
        comparison_group_id=args.comparison_group_id,
        input_artifact_hash=hashlib.sha256(args.report.read_bytes()).hexdigest(),
        transport_failures=args.transport_failures,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(observation.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
