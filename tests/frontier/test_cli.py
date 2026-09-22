import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "frontier" / "fixtures"


def _run(*args: str) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_fixture_report_generation_is_byte_deterministic(tmp_path):
    diversity_a = tmp_path / "diversity-a.json"
    diversity_b = tmp_path / "diversity-b.json"
    calibration = tmp_path / "calibration.json"
    report_a = tmp_path / "report-a.json"
    report_b = tmp_path / "report-b.json"

    common_diversity = [
        "tools/frontier_task_diversity.py", "--input", str(FIXTURES / "tasks.json"),
        "--benchmark-name", "SyntheticFrontierFixture", "--benchmark-version", "fixture-v1",
        "--candidate-id", "FIXTURE-CAND-1",
    ]
    _run(*common_diversity, "--output", str(diversity_a))
    _run(*common_diversity, "--output", str(diversity_b))
    assert diversity_a.read_bytes() == diversity_b.read_bytes()

    _run(
        "tools/frontier_calibration.py", "--observations", str(FIXTURES / "observations.json"),
        "--output", str(calibration),
    )
    qualify = [
        "tools/frontier_qualify.py",
        "--qualification",
        str(FIXTURES / "scientific_qualification.json"),
        "--diversity", str(diversity_a), "--calibration", str(calibration),
        "--training-value", str(FIXTURES / "training_value.json"),
        "--generalization", str(FIXTURES / "generalization.json"),
    ]
    _run(*qualify, "--output", str(report_a))
    _run(*qualify, "--output", str(report_b))
    assert report_a.read_bytes() == report_b.read_bytes()
    payload = json.loads(report_a.read_text())
    assert payload["scientifically_qualified"] is True
    assert payload["frontier_qualified"] is True
    assert payload["report_id"].startswith("FRQ-")
