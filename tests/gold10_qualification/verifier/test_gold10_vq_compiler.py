import pytest

import investigation_world.gold10_qualification.verifier.compiler as compiler
from investigation_world.gold10.registry import build_taskset, load_pilot_contract
from investigation_world.gold10_qualification.verifier.compiler import (
    compile_gold10_verifier_qualification,
    compile_task_qualification,
)
from investigation_world.gold10_qualification.verifier.models import (
    Gold10TaskVerifierQualification,
)
from investigation_world.qualification.maturity import GateOutcome
from investigation_world.qualification.verifier_suite import qualify_verifier


def _failure_summary(record: Gold10TaskVerifierQualification) -> str:
    report = record.report
    failures = [
        (gate.name, gate.outcome.value, gate.observed, gate.required)
        for gate in report.gates
        if gate.outcome != GateOutcome.PASS
    ]
    return (
        f"case={record.binding.case_id} report={report.status.value} "
        f"gates={failures!r}"
    )


def test_each_gold10_task_compiles_fail_closed_verifier_evidence() -> None:
    tasks = build_taskset()
    assert len(tasks) == 10
    contract = load_pilot_contract()
    for task in tasks:
        record = compile_task_qualification(task.case_id)
        assert record.binding.task_id == task.task.task_id
        assert record.binding.task_manifest_sha256 == task.manifest_sha256
        assert record.report.environment_identity.environment_id == contract.world_id
        assert (
            record.report.environment_identity.environment_version
            == contract.world_version
        )
        assert record.effective_status == GateOutcome.PASS, _failure_summary(record)
        gate_names = {gate.name for gate in record.report.gates}
        assert "reward_hack_resistance" in gate_names
        assert "deterministic_reproduction" in gate_names
        assert record.report.metrics["reward_hack_resistance"] == 1.0
        assert record.report.metrics["deterministic_reproduction"] == 1.0
        assert record.report.metrics["alternative_solution_acceptance"] is None
        assert record.report.metrics["process_rule_correctness"] is None
        if task.calibration_required:
            assert record.report.metrics["ambiguity_sensitivity"] == 1.0
        else:
            assert record.report.metrics["ambiguity_sensitivity"] is None


def test_candidate_qualification_requires_all_ten_task_records() -> None:
    result = compile_gold10_verifier_qualification()
    failing = [
        _failure_summary(record)
        for record in result.task_records
        if record.effective_status != GateOutcome.PASS
    ]
    assert result.status == GateOutcome.PASS, failing
    assert len(result.task_records) == 10
    assert len({item.binding.case_id for item in result.task_records}) == 10
    assert result.qualification_id.startswith("G10VQ-")


def test_noncalibration_ambiguity_is_not_manufactured() -> None:
    task = next(item for item in build_taskset() if not item.calibration_required)
    record = compile_task_qualification(task.case_id)
    non_applicable = {
        item.gate
        for item in record.applicability
        if item.applicability.value == "NOT_APPLICABLE"
    }
    assert non_applicable == {
        "falsifier_fixture_coverage",
        "alternative_solution_acceptance",
        "process_rule_correctness",
        "side_effect_sensitivity",
        "ambiguity_sensitivity",
    }
    outcomes = {gate.name: gate.outcome for gate in record.report.gates}
    assert outcomes["falsifier_fixture_coverage"] == GateOutcome.UNKNOWN
    assert outcomes["alternative_solution_acceptance"] == GateOutcome.UNKNOWN
    assert outcomes["process_rule_correctness"] == GateOutcome.UNKNOWN
    assert outcomes["side_effect_sensitivity"] == GateOutcome.UNKNOWN
    assert outcomes["ambiguity_sensitivity"] == GateOutcome.UNKNOWN
    assert record.report.metrics["ambiguity_sensitivity"] is None


def test_calibration_case_retains_real_ambiguity_evidence() -> None:
    task = next(item for item in build_taskset() if item.calibration_required)
    record = compile_task_qualification(task.case_id)
    non_applicable = {
        item.gate
        for item in record.applicability
        if item.applicability.value == "NOT_APPLICABLE"
    }
    assert "ambiguity_sensitivity" not in non_applicable
    outcome = next(
        gate.outcome
        for gate in record.report.gates
        if gate.name == "ambiguity_sensitivity"
    )
    assert outcome == GateOutcome.PASS
    assert record.report.metrics["ambiguity_sensitivity"] == 1.0


def test_world_version_drift_changes_bound_environment_identity(monkeypatch) -> None:
    case_id = build_taskset()[0].case_id
    canonical = load_pilot_contract()
    original = compiler._environment_identity(case_id, compiler.ROOT)

    drifted_contract = canonical.model_copy(update={"world_version": "0.1.1-drift"})
    monkeypatch.setattr(
        compiler,
        "load_pilot_contract",
        lambda root=None: drifted_contract,
    )
    drifted = compiler._environment_identity(case_id, compiler.ROOT)

    assert original.environment_id == canonical.world_id
    assert original.environment_version == canonical.world_version
    assert drifted.environment_id == canonical.world_id
    assert drifted.environment_version == "0.1.1-drift"
    assert drifted.content_sha256 != original.content_sha256


def test_replays_bind_full_qualification_identity_and_reject_stale_rows(
    monkeypatch,
) -> None:
    case_id = build_taskset()[0].case_id
    canonical_contract = load_pilot_contract()
    captured: list[tuple[object, tuple[object, ...]]] = []
    canonical_qualify = compiler.qualify_verifier

    def capture(manifest, replays):
        captured.append((manifest, tuple(replays)))
        return canonical_qualify(manifest, replays)

    monkeypatch.setattr(compiler, "qualify_verifier", capture)
    canonical_record = compile_task_qualification(case_id)
    canonical_manifest, canonical_replays = captured[-1]
    replay = canonical_replays[0]

    required_provenance = {
        "case_id",
        "task_id",
        "task_manifest_sha256",
        "taskset_version",
        "world_id",
        "world_version",
        "environment_content_sha256",
        "verifier_id",
        "verifier_version",
        "verifier_content_sha256",
        "verifier_target_contract_sha256",
        "qualification_binding_sha256",
        "repetition",
    }
    assert required_provenance <= replay.provenance.keys()

    drifted_contract = canonical_contract.model_copy(
        update={"verifier_version": "0.3.1-drift"}
    )
    monkeypatch.setattr(
        compiler,
        "load_pilot_contract",
        lambda root=None: drifted_contract,
    )
    drifted_record = compile_task_qualification(case_id)
    drifted_manifest, _ = captured[-1]

    canonical_fixture_ids = {item.fixture_id for item in canonical_manifest.fixtures}
    drifted_fixture_ids = {item.fixture_id for item in drifted_manifest.fixtures}
    assert canonical_fixture_ids.isdisjoint(drifted_fixture_ids)
    assert (
        canonical_record.report.replay_evidence_id
        != drifted_record.report.replay_evidence_id
    )

    with pytest.raises(ValueError, match="replay references unknown fixture"):
        qualify_verifier(drifted_manifest, canonical_replays)
