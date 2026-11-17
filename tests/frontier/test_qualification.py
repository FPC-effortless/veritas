import copy
import json

from investigation_world.frontier.diversity import compute_task_diversity
from investigation_world.frontier.models import FrontierCalibrationObservation, GateStatus
from investigation_world.frontier.qualification import (
    build_frontier_qualification_report,
    summarize_training_value,
)


def _diverse_tasks():
    return [
        {
            "task_id": f"t-{i}",
            "split": "train" if i < 12 else "private_test",
            "source_family": f"source-{i % 8}",
            "grammar_family": f"grammar-{i % 8}",
            "workflow_topology": f"flow-{i % 6}>branch-{i % 4}>end-{i % 5}",
            "action_sequence": [f"tool-{i % 9}", f"act-{i % 11}", f"end-{i % 5}"],
            "failure_mode": f"failure-{i % 5}",
            "verifier_conditions": [f"condition-{i % 7}"],
            "artifact_schema": f"schema-{i % 6}",
            "components": [f"c-{i % 11}", f"c-{(i * 7 + 3) % 17}"],
            "prompt": f"Distinct operational workflow {i} source {i % 8} action {i % 11}",
        }
        for i in range(32)
    ]


def _small_model_observations():
    return [
        FrontierCalibrationObservation(
            model_identity="Qwen2.5-0.5B", harness_identity="local", tier="weak", score=0.31
        ),
        FrontierCalibrationObservation(
            model_identity="SmolLM2-360M", harness_identity="local", tier="weak", score=0.24
        ),
    ]


def test_absent_training_controls_are_unknown():
    report = build_frontier_qualification_report(
        scientific_qualification={"releaseable": True},
        training_value={"within_family_transfer": "PASS", "model_tier": "strong"},
    )
    controls = next(g for g in report.gates if g.name == "control_regression_guardrail")
    assert controls.status is GateStatus.UNKNOWN


def test_sparse_diversity_dimensions_are_unknown_instead_of_passing():
    tasks = [
        {
            "source_family": f"source-{i % 12}",
            "causal_class": f"class-{i % 4}",
            "prompt": f"Distinct incident evidence {i}",
        }
        for i in range(30)
    ]
    diversity = compute_task_diversity(tasks)
    report = build_frontier_qualification_report(
        scientific_qualification={"releaseable": True},
        diversity=diversity,
    )
    gate = next(g for g in report.gates if g.name == "task_diversity")
    assert gate.status is GateStatus.UNKNOWN
    assert gate.observed["available_diversity_dimension_count"] == 2
    assert "workflow_topology" in gate.observed["missing_diversity_dimensions"]


def test_within_family_training_evidence_cannot_become_external_transfer():
    summary = summarize_training_value(
        {
            "experiment": "diagnostic_lora_sft_hardened_replicated_transfer",
            "model": "Qwen/Qwen2.5-1.5B-Instruct",
            "seed_level_mean_delta": {"ci95_low": 0.02, "ci95_high": 0.08},
        }
    )
    assert summary.within_family_transfer is GateStatus.PASS
    assert summary.cross_family_transfer is GateStatus.UNKNOWN
    assert summary.external_benchmark_transfer is GateStatus.UNKNOWN
    assert summary.control_benchmark_preservation is GateStatus.UNKNOWN


def test_report_identity_is_deterministic_and_buyer_safe():
    inputs = dict(
        scientific_qualification={"releaseable": True, "candidate_id": "C-1", "report_id": "Q-1"},
        diversity=compute_task_diversity(_diverse_tasks()),
        observations=_small_model_observations(),
    )
    first = build_frontier_qualification_report(**inputs)
    second = build_frontier_qualification_report(**inputs)
    assert first.report_id == second.report_id
    rendered = json.dumps(first.model_dump(mode="json"), sort_keys=True).lower()
    assert '"tasks"' not in rendered
    assert '"scenarios"' not in rendered
    assert "private_task_rows" not in rendered
    assert "hidden_oracle" not in rendered
    assert first.buyer_safe is True


def test_frontier_layer_never_changes_existing_scientific_qualification():
    source = {
        "releaseable": True,
        "candidate_id": "C-1",
        "gates": [{"name": "scientific", "passed": True}],
    }
    before = copy.deepcopy(source)
    report = build_frontier_qualification_report(scientific_qualification=source)
    assert source == before
    assert report.scientifically_qualified is True
    failed = build_frontier_qualification_report(scientific_qualification={"releaseable": False})
    assert failed.scientifically_qualified is False


def test_sre_v4_science_can_pass_while_frontier_status_remains_not_yet_qualified():
    release = {
        "candidate_id": "SRE-CAND-92A84929AD1E82E24357",
        "version": "sre-v4",
        "status": "benchmark_candidate",
        "failed_gates": [],
        "report_id": "QREPORT-C585121E94D91766BB6664E3",
        "panel_id": "QPANEL-AFF065BA4C2FD75BE9BB3EBE",
        "evidence_manifest_id": "EVID-2C69B48DCDD5F2232EABDC9B",
        "private_release_manifest_id": "PRIVREL-036192DA63716D331C929C0C",
    }
    report = build_frontier_qualification_report(
        scientific_qualification=release,
        observations=_small_model_observations(),
    )
    assert report.scientifically_qualified is True
    assert report.frontier_qualified is False
    non_saturation = next(g for g in report.gates if g.name == "non_saturation")
    assert non_saturation.status is GateStatus.UNKNOWN
    assert "strong/frontier" in non_saturation.detail


def test_all_outputs_are_reproducible():
    kwargs = {
        "scientific_qualification": {"releaseable": True, "candidate_id": "C-X"},
        "diversity": compute_task_diversity(_diverse_tasks()),
        "observations": _small_model_observations(),
        "generalization": {"random_held_out": "PASS", "source_disjoint": "PASS"},
    }
    first = build_frontier_qualification_report(**kwargs).model_dump(mode="json")
    second = build_frontier_qualification_report(**kwargs).model_dump(mode="json")
    assert first == second
