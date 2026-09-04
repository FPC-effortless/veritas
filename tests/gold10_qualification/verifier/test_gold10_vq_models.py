from investigation_world.gold10_qualification.verifier.models import (
    Applicability,
    Gold10ApplicabilityRecord,
    Gold10TaskBinding,
    Gold10TaskVerifierQualification,
    Gold10VerifierQualification,
)
from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    GateOutcome,
    VerifierIdentity,
)
from investigation_world.qualification.verifier_suite import (
    VerifierQualificationGate,
    VerifierQualificationReport,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def _report(status: GateOutcome) -> VerifierQualificationReport:
    gate = VerifierQualificationGate(
        name="reward_hack_resistance",
        outcome=status,
        observed=1.0 if status == GateOutcome.PASS else None,
        required=1.0,
    )
    return VerifierQualificationReport(
        suite_version="gold10-vq-test",
        fixture_manifest_id="fixture-manifest",
        replay_evidence_id="replay-evidence",
        environment_identity=EnvironmentIdentity(
            environment_id="veritas.gold10.investigation",
            environment_version="0.1.0",
            content_sha256=SHA_A,
        ),
        verifier_identity=VerifierIdentity(
            verifier_id="veritas.gold10.evidence-discipline",
            verifier_version="0.3.0",
            content_sha256=SHA_B,
        ),
        metrics={},
        gates=(gate,),
        status=status,
    )


def _task(index: int, status: GateOutcome) -> Gold10TaskVerifierQualification:
    applicability = ()
    if status == GateOutcome.UNKNOWN:
        applicability = (
            Gold10ApplicabilityRecord(
                gate="reward_hack_resistance",
                applicability=Applicability.REQUIRED,
                rationale="reward-hack resistance is mandatory",
            ),
        )
    return Gold10TaskVerifierQualification(
        binding=Gold10TaskBinding(
            case_id=f"case-{index}",
            task_id=f"GOLD10-case-{index}",
            split="train",
            task_manifest_sha256=f"{index:064x}",
            verifier_target_contract_sha256=SHA_A,
        ),
        report=_report(status),
        applicability=applicability,
    )


def test_candidate_pass_requires_all_ten_tasks_to_pass() -> None:
    records = tuple(_task(index, GateOutcome.PASS) for index in range(10))
    result = Gold10VerifierQualification(
        pilot_id="gold10-flagship-pilot-v1",
        taskset_version="gold10-flagship-pilot-v1",
        verifier_target_contract_sha256=SHA_A,
        task_records=records,
        status=GateOutcome.PASS,
    )
    assert result.status == GateOutcome.PASS
    assert result.qualification_id.startswith("G10VQ-")


def test_required_unknown_cannot_be_averaged_away() -> None:
    records = tuple(
        _task(index, GateOutcome.UNKNOWN if index == 4 else GateOutcome.PASS)
        for index in range(10)
    )
    result = Gold10VerifierQualification(
        pilot_id="gold10-flagship-pilot-v1",
        taskset_version="gold10-flagship-pilot-v1",
        verifier_target_contract_sha256=SHA_A,
        task_records=records,
        status=GateOutcome.UNKNOWN,
    )
    assert result.status == GateOutcome.UNKNOWN


def test_not_applicable_never_erases_fail() -> None:
    record = Gold10TaskVerifierQualification(
        binding=Gold10TaskBinding(
            case_id="case-x",
            task_id="GOLD10-case-x",
            split="eval",
            task_manifest_sha256="f" * 64,
            verifier_target_contract_sha256=SHA_A,
        ),
        report=_report(GateOutcome.FAIL),
    )
    assert record.effective_status == GateOutcome.FAIL
