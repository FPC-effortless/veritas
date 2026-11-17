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
    FrontierCalibrationObservation,
    FrontierQualificationPolicy,
    FrontierQualificationReport,
    FrontierStatus,
    GateStatus,
    PairedCapabilityComparison,
    TaskDiversityReport,
)
from investigation_world.frontier.qualification import (  # noqa: E402
    build_frontier_qualification_report,
)


def _read_json(path: Path | None) -> Any:
    return None if path is None else json.loads(path.read_text(encoding="utf-8"))


def _artifact_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_observations(payload: Any) -> list[FrontierCalibrationObservation]:
    if payload is None:
        return []
    source = payload.get("observations") if isinstance(payload, dict) else payload
    if not isinstance(source, list):
        raise ValueError("calibration input must be a list or object containing observations")
    return [FrontierCalibrationObservation.model_validate(item) for item in source]


def _normalized_paired(payload: Any) -> list[PairedCapabilityComparison]:
    if payload is None or not isinstance(payload, dict):
        return []
    source = payload.get("paired_comparisons", [])
    if not isinstance(source, list):
        raise ValueError("calibration paired_comparisons must be a list")
    return [PairedCapabilityComparison.model_validate(item) for item in source]


def _with_paired_calibration(
    report: FrontierQualificationReport,
    *,
    observations: list[FrontierCalibrationObservation],
    paired_comparisons: list[PairedCapabilityComparison],
    policy: FrontierQualificationPolicy,
) -> FrontierQualificationReport:
    if not paired_comparisons:
        return report

    calibration = calibration_gates(observations, policy, paired_comparisons)
    # The base builder owns the non-calibration gates and scientific boundary. Replace
    # only its first four Frontier-owned calibration gates, then revalidate the whole
    # report so the content-derived ID and final status remain canonical.
    gates = [*calibration, *report.gates[4:]]
    frontier_qualified = (
        report.scientifically_qualified is True
        and all(gate.status is GateStatus.PASS for gate in gates)
    )
    payload = report.model_dump(mode="json")
    payload.update(
        {
            "report_id": "",
            "gates": [gate.model_dump(mode="json") for gate in gates],
            "frontier_qualified": frontier_qualified,
            "frontier_status": (
                FrontierStatus.FRONTIER_QUALIFIED
                if frontier_qualified
                else FrontierStatus.NOT_YET_FRONTIER_QUALIFIED
            ),
        }
    )
    return FrontierQualificationReport.model_validate(payload)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Produce a buyer-safe Frontier Qualification report"
    )
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--diversity", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--training-value", type=Path)
    parser.add_argument("--generalization", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    scientific = _read_json(args.qualification)
    diversity_payload = _read_json(args.diversity)
    calibration_payload = _read_json(args.calibration)
    training = _read_json(args.training_value)
    generalization = _read_json(args.generalization)
    policy_payload = _read_json(args.policy)

    policy = (
        FrontierQualificationPolicy.model_validate(policy_payload)
        if policy_payload
        else FrontierQualificationPolicy()
    )
    diversity = TaskDiversityReport.model_validate(diversity_payload) if diversity_payload else None
    observations = _normalized_observations(calibration_payload)
    paired_comparisons = _normalized_paired(calibration_payload)

    supplied = {
        "qualification": args.qualification,
        "diversity": args.diversity,
        "calibration": args.calibration,
        "training_value": args.training_value,
        "generalization": args.generalization,
        "policy": args.policy,
    }
    hashes = {name: _artifact_hash(path) for name, path in supplied.items() if path is not None}

    report = build_frontier_qualification_report(
        scientific_qualification=scientific,
        diversity=diversity,
        observations=observations,
        generalization=generalization,
        training_value=training,
        policy=policy,
        input_artifact_hashes=hashes,
    )
    report = _with_paired_calibration(
        report,
        observations=observations,
        paired_comparisons=paired_comparisons,
        policy=policy,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
