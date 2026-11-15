"""Constructed private records only: no training, scorer or protected-panel execution."""

import copy
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("trainlab")
from trainlab.runner import LabError
from trainlab.training_assessment import assess_private_training, point_identity

from investigation_world.training_qualification import TrainingPolicy, assess_training

# Reuse the canonical provider's established constructed fixture, not a new attestor.
spec = importlib.util.spec_from_file_location(
    "train001_bridge_fixtures", Path(__file__).with_name("test_training_qualification.py")
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def report(**changes):
    return assess_training(
        fixtures.evidence(**changes),
        policy=TrainingPolicy(
            minimum_replicates=2,
            minimum_population=4,
        ),
    )


def phase(point):
    rows = [
        {"episode_id": row.member_id, "score": row.value, "parsed": True} for row in point.outcomes
    ]
    return {"episodes": rows, "mean": point.recorded_mean, "parse_failures": 0}


def diagnostics(value):
    rows = []
    for rep in value.evidence.replicates:
        points = dict(
            zip(
                ("train_before", "train_after", "heldout_before", "heldout_after"),
                (*rep.train.points, *rep.heldout.points),
                strict=True,
            )
        )
        target = copy.deepcopy(phase(rep.train.points[0]))
        for row in target["episodes"]:
            row["score"] = 1.0
        target["mean"] = 1.0
        rows.append(
            {
                "training_seed": rep.seed,
                "reference_target_sanity": target,
                "minimum_reference_score": 0.95,
                "canonical_binding": {
                    "run_id": rep.manifest.run_id,
                    "point_sha256": {k: point_identity(v) for k, v in points.items()},
                },
                **{name: phase(point) for name, point in points.items()},
            }
        )
    return rows


def test_recomputation_and_four_phase_linkage_never_qualify():
    value = report()
    result = assess_private_training(value, diagnostics(value)).private_payload()
    assert result["canonical_status"] == "UNKNOWN"
    assert result["qualification"] == "NOT_QUALIFIED"
    assert result["training_validated"] is False
    assert result["claim_promotion"] == "NOT_GRANTED"
    assert all(row["status"] == "DIAGNOSTIC_SCORES_LINKED" for row in result["diagnostics"])
    gates = {gate["name"]: gate["outcome"] for gate in result["canonical_report"]["gates"]}
    assert gates["execution_and_chronology"] == "UNKNOWN"
    assert result["providers"]["independent_scorer_replay"] == "NOT_PERFORMED"


def test_no_public_identity_or_private_details_escape():
    value = report()
    result = assess_private_training(value, diagnostics(value))
    assert result.public_payload() == {"visibility": "evaluator_private", "withheld": True}
    assert result.buyer_safe_payload() == result.public_payload()
    assert "run-1" not in repr(result)
    assert value.record_id not in repr(result)


def test_forged_canonical_pass_rejected():
    value = report().model_dump(mode="json")
    value["training_validated"] = True
    with pytest.raises(LabError):
        assess_private_training(value)


def test_missing_seed_phase_binding_or_reference_stays_unassessed():
    value = report()
    for field in ("heldout_after", "canonical_binding", "reference_target_sanity"):
        records = diagnostics(value)
        records[0].pop(field)
        result = assess_private_training(value, records).private_payload()
        assert result["diagnostics"][0]["status"] == "UNASSESSED"
    result = assess_private_training(value, diagnostics(value)[1:]).private_payload()
    assert result["diagnostics"][0]["status"] == "UNASSESSED"
    assert len(result["diagnostics"]) == 2


def test_unscored_canonical_rows_not_dropped_or_interpreted():
    value = report(heldout_after=(None, 0.6, 0.6, 0.6))
    result = assess_private_training(value, diagnostics(value)).private_payload()
    assert all(row["status"] == "UNASSESSED" for row in result["diagnostics"])
    assert any(panel["after_unknown_count"] for panel in result["canonical_report"]["panels"])


@pytest.mark.parametrize("mutation", ["seed", "point", "run", "score", "duplicate", "population"])
def test_inconsistent_association_rejected(mutation):
    value = report()
    records = diagnostics(value)
    if mutation == "seed":
        records[1]["training_seed"] = records[0]["training_seed"]
    elif mutation == "point":
        records[0]["canonical_binding"]["point_sha256"]["train_before"] = "0" * 64
    elif mutation == "run":
        records[0]["canonical_binding"]["run_id"] = "another-run"
    elif mutation == "score":
        records[0]["heldout_after"]["episodes"][0]["score"] = 0.9
    elif mutation == "duplicate":
        records[0]["train_before"]["episodes"].append(records[0]["train_before"]["episodes"][0])
    else:
        records[0]["train_before"]["episodes"][0]["episode_id"] = "other-source"
    with pytest.raises(LabError):
        assess_private_training(value, records)


def test_failed_target_sanity_cannot_be_hidden_by_positive_gains():
    value = report()
    records = diagnostics(value)
    records[0]["reference_target_sanity"]["episodes"][0]["score"] = 0
    records[0]["reference_target_sanity"]["mean"] = 0.75
    result = assess_private_training(value, records).private_payload()
    assert result["diagnostics"][0]["diagnosis"]["diagnosis"] == "target_scorer_sanity_failed"
    assert result["claim_promotion"] == "NOT_GRANTED"


def test_canonical_failure_preserved_despite_valid_diagnostic_binding():
    value = report(heldout_after=(0.0,) * 4)
    result = assess_private_training(value, diagnostics(value)).private_payload()
    assert result["canonical_status"] == "FAIL"
    assert result["qualification"] == "NOT_QUALIFIED"


def test_research_lab_facade_does_not_index_private_records(tmp_path):
    pytest.importorskip("research_lab")
    from research_lab.core import Controller

    lab = Controller(tmp_path / "lab")
    value = report()
    result = lab.assess_private_training(value, diagnostics(value))
    assert result.private_payload()["canonical_status"] == "UNKNOWN"
    assert not list(lab.root.rglob("*.json"))


def test_retained_private_assessment_recomputes_and_rejects_summary_edit():
    import json

    from trainlab.training_assessment import (
        PrivateTrainingAssessment,
        verify_private_training_assessment,
    )

    value = report()
    result = assess_private_training(value, diagnostics(value))
    assert verify_private_training_assessment(result) is True
    payload = result.private_payload()
    payload["diagnostics"][0]["diagnosis"]["diagnosis"] = "fabricated-transfer"
    changed = PrivateTrainingAssessment(json.dumps(payload).encode())
    with pytest.raises(LabError):
        verify_private_training_assessment(changed)


def test_repository_tools_use_current_helper_with_old_package_already_loaded():
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    code = """import sys, types
old = types.ModuleType("trainlab")
old.__path__ = []
sys.modules["trainlab"] = old
from tools.training_value_diagnostics import unique_rows
assert unique_rows([{"episode_id": "a"}]) == {"a": {"episode_id": "a"}}
"""
    subprocess.run([sys.executable, "-c", code], cwd=root, check=True)
