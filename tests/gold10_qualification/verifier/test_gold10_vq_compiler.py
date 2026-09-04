from investigation_world.gold10.registry import build_taskset
from investigation_world.gold10_qualification.verifier.compiler import (
    compile_gold10_verifier_qualification,
    compile_task_qualification,
)
from investigation_world.gold10_qualification.verifier.models import (
    Gold10TaskVerifierQualification,
)
from investigation_world.qualification.maturity import GateOutcome


def _failure_summary(record: Gold10TaskVerifierQualification) -> str:
    report = record.report
    failures = [
        (gate.name, gate.outcome.value, gate.observed, gate.required)
        for gate in report.gates
        if gate.outcome != GateOutcome.PASS
    ]
    return f"case={record.binding.case_id} report={report.status.value} gates={failures!r}"


def test_each_gold10_task_compiles_fail_closed_verifier_evidence() -> None:
    tasks = build_taskset()
    assert len(tasks) == 10
    for task in tasks:
        record = compile_task_qualification(task.case_id)
        assert record.binding.task_id == task.task.task_id
        assert record.binding.task_manifest_sha256 == task.manifest_sha256
        assert record.effective_status == GateOutcome.PASS, _failure_summary(record)
        gate_names = {gate.name for gate in record.report.gates}
        assert "reward_hack_resistance" in gate_names
        assert "deterministic_reproduction" in gate_names
        assert record.report.metrics["reward_hack_resistance"] == 1.0
        assert record.report.metrics["deterministic_reproduction"] == 1.0


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


def test_only_side_effect_generic_gates_are_marked_not_applicable() -> None:
    task = build_taskset()[0]
    record = compile_task_qualification(task.case_id)
    non_applicable = {
        item.gate
        for item in record.applicability
        if item.applicability.value == "NOT_APPLICABLE"
    }
    assert non_applicable == {"falsifier_fixture_coverage", "side_effect_sensitivity"}
    coverage_gate = next(
        gate for gate in record.report.gates if gate.name == "falsifier_fixture_coverage"
    )
    assert coverage_gate.outcome == GateOutcome.UNKNOWN
