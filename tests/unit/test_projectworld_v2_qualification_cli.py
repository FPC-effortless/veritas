from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import build_projectworld_v2_qualification_candidate as cli


def _report():
    return SimpleNamespace(
        releaseable=True,
        gates=[
            SimpleNamespace(name=name, passed=True)
            for name in sorted(cli.PROJECTWORLD_V2_GATE_NAMES)
        ],
        policy_means={},
        model_dump=lambda **kwargs: {"private_fixture": "do-not-publish"},
    )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown"])
def test_report_requires_exact_gate_names_not_just_count(mutation) -> None:
    report = _report()
    if mutation == "missing":
        report.gates.pop()
    elif mutation == "duplicate":
        report.gates[-1].name = report.gates[0].name
    else:
        report.gates[-1].name = "unimplemented_hud_gate"
    with pytest.raises(RuntimeError, match="exact 18 named"):
        cli._report_is_releaseable(report)


def test_failed_gate_or_nonreleaseable_report_cannot_issue_release() -> None:
    report = _report()
    assert cli._report_is_releaseable(report)
    report.releaseable = False
    assert not cli._report_is_releaseable(report)
    report.releaseable = True
    report.gates[0].passed = False
    assert not cli._report_is_releaseable(report)


@pytest.mark.parametrize("passed", [True, False])
def test_cli_exit_status_and_public_summary_fail_closed(tmp_path, monkeypatch, capsys, passed):
    report = _report()
    report.gates[0].passed = passed
    candidate = SimpleNamespace(
        scenarios=[SimpleNamespace(split=SimpleNamespace(value="private_test"))],
        model_dump=lambda **kwargs: {"private_fixture": "do-not-publish"},
    )
    monkeypatch.setattr(
        cli, "build_calibrated_projectworld_v2_candidate", lambda **kw: (candidate, {})
    )
    monkeypatch.setattr(cli, "execute_calibrated_projectworld_v2_policy_suite", lambda *a, **kw: [])
    monkeypatch.setattr(cli, "qualify_candidate", lambda *a, **kw: report)
    issued = []

    def issue_release(*args):
        issued.append(True)
        return SimpleNamespace(model_dump=lambda **kwargs: {"private_fixture": "do-not-publish"})

    monkeypatch.setattr(cli, "private_release_manifest", issue_release)
    output = tmp_path / "private.json"
    public = tmp_path / "public.json"
    monkeypatch.setattr(
        "sys.argv", ["qualify", "--output", str(output), "--public-output", str(public)]
    )
    if passed:
        cli.main()
    else:
        with pytest.raises(SystemExit, match="qualification failed"):
            cli.main()
    private = json.loads(output.read_text())
    summary = json.loads(public.read_text())
    assert bool(issued) is passed
    assert (private["private_release_manifest"] is not None) is passed
    assert summary["status"] == ("benchmark_candidate" if passed else "not_qualified")
    assert summary["gate_count"] == 18
    assert summary["passed_gates"] == (18 if passed else 17)
    assert "do-not-publish" not in public.read_text()
    assert "do-not-publish" not in capsys.readouterr().out
    assert set(summary) == {
        "status",
        "scenarios",
        "private_test",
        "gate_count",
        "passed_gates",
        "failed_gates",
        "gates",
        "policy_means",
    }


def test_private_and_public_paths_must_be_distinct(tmp_path, monkeypatch) -> None:
    output = tmp_path / "same.json"
    monkeypatch.setattr(
        "sys.argv", ["qualify", "--output", str(output), "--public-output", str(output)]
    )
    with pytest.raises(ValueError, match="different paths"):
        cli.main()
    assert not output.exists()


def test_projectworld_stratum_thresholds_remain_strict() -> None:
    thresholds = cli._projectworld_v2_thresholds()
    assert thresholds.private_stratum_metadata_key == "project_type"
    assert thresholds.minimum_private_strata == 5
    assert thresholds.minimum_private_scenarios_per_stratum == 1
    assert thresholds.maximum_private_stratum_fraction == 0.30


def test_projectworld_qualification_workflow_remains_executable() -> None:
    workflow = Path(".github/workflows/projectworld-v2-qualification.yml").read_text()
    assert "on:" in workflow
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "jobs:" in workflow
    assert "policy-calibration:" in workflow
    assert "build_projectworld_v2_qualification_candidate.py" in workflow


def test_projectworld_workflow_uploads_only_aggregate_summary() -> None:
    workflow = Path(".github/workflows/projectworld-v2-qualification.yml").read_text()
    assert "--public-output" in workflow
    assert "path: ${{ runner.temp }}/projectworld-v2-summary.json" in workflow
    assert "path: results/projectworld-v2" not in workflow
