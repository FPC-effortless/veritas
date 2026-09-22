from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from investigation_world.frontier.calibration import calibration_gates  # noqa: E402
from investigation_world.frontier.models import (  # noqa: E402
    CALCULATION_VERSION,
    FrontierCalibrationObservation,
    FrontierQualificationPolicy,
    PairedCapabilityComparison,
    stable_content_hash,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _observations(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("observations"), list):
        return payload["observations"]
    raise ValueError("observations input must be a JSON list or object containing observations")


def _paired(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("paired_comparisons"), list):
        return payload["paired_comparisons"]
    if isinstance(payload, list):
        return payload
    raise ValueError(
        "paired comparison input must be a JSON list or object containing paired_comparisons"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate Frontier model/harness calibration evidence"
    )
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument(
        "--paired-comparisons",
        type=Path,
        help=(
            "optional buyer-safe paired weak/strong aggregate; preferred when systems "
            "were evaluated on the same private task panel"
        ),
    )
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    policy = (
        FrontierQualificationPolicy.model_validate(_read_json(args.policy))
        if args.policy
        else FrontierQualificationPolicy()
    )
    raw_observations = _read_json(args.observations)
    observations = [
        FrontierCalibrationObservation.model_validate(item)
        for item in _observations(raw_observations)
    ]

    paired_payloads: list[dict[str, Any]] = []
    if isinstance(raw_observations, dict):
        paired_payloads.extend(raw_observations.get("paired_comparisons", []))
    if args.paired_comparisons:
        paired_payloads.extend(_paired(_read_json(args.paired_comparisons)))
    paired_comparisons = [
        PairedCapabilityComparison.model_validate(item) for item in paired_payloads
    ]

    gates = calibration_gates(observations, policy, paired_comparisons)
    payload = {
        "schema_version": "2",
        "calculation_version": CALCULATION_VERSION,
        "policy": policy.model_dump(mode="json"),
        "observations": [item.model_dump(mode="json") for item in observations],
        "paired_comparisons": [
            item.model_dump(mode="json") for item in paired_comparisons
        ],
        "gates": [gate.model_dump(mode="json") for gate in gates],
        "input_artifact_hashes": {str(args.observations): _artifact_hash(args.observations)},
    }
    if args.paired_comparisons:
        payload["input_artifact_hashes"][str(args.paired_comparisons)] = _artifact_hash(
            args.paired_comparisons
        )
    if args.policy:
        payload["input_artifact_hashes"][str(args.policy)] = _artifact_hash(args.policy)
    payload["bundle_id"] = f"FRCAL-{stable_content_hash(payload)[:24].upper()}"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
