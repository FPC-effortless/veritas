from investigation_world.gold10_qualification.verifier import models as vq_models
from investigation_world.qualification import maturity
from investigation_world.qualification import verifier_suite


SHA_A = "a" * 64
SHA_B = "b" * 64


def _report(status: maturity.GateOutcome) -> verifier_suite.VerifierQualificationReport:
    gate = verifier_suite.VerifierQualificationGate(
        name="reward_hack_resistance",
        outcome=status,
        observed=1.0 if status == maturity.GateOutcome.PASS else None,
        required=1.0,
    )
    return verifier_suite.VerifierQualificationReport(
        suite_version="gold10-vq-test",
        fixture_manifest_id="fixture-manifest",
        replay_evidence_id="replay-evidence",
        environment_identity=maturity.EnvironmentIdentity(
            environment_id="veritas.gold10.investigation",
            environment_version="0.1.0",
            content_sha256=SHA_A,
        ),
        verifier_identity=maturity.VerifierIdentity(
            verifier_id="veritas.gold10.evidence-discipline",
            verifier_version="0.3.0",
            content_sha256=SHA_B,
        ),
        metrics={},
        gates=(gate,),
        status=status,
    )


def _task(
    index: int,
    status: maturity.GateOutcome,
) -> vq_models.Gold10TaskVerifierQualification:
    applicability = ()
    if status == maturity.GateOutcome.UNKNOWN:
        applicability = (
            vq_models.Gold10ApplicabilityRecord(
                gate="reward_hack_resistance",
                applicability=vq_models.Applicability.REQUIRED,
                rationale="reward-hack resistance is mandatory",
            ),
        )
    return vq_models.Gold10TaskVerifierQualification(
        binding=vq_models.Gold10TaskBinding(
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
    records = tuple(_task(index, maturity.GateOutcome.PASS) for index in range(10))
    result = vq_models.Gold10VerifierQualification(
        pilot_id="gold10-flagship-pilot-v1",
        taskset_version="gold10-flagship-pilot-v1",
        verifier_target_contract_sha256=SHA_A,
        task_records=records,
        status=maturity.GateOutcome.PASS,
    )
    assert result.status == maturity.GateOutcome.PASS
    assert result.qualification_id.startswith("G10VQ-")


def test_required_unknown_cannot_be_averaged_away() -> None:
    records = tuple(
        _task(
            index,
            maturity.GateOutcome.UNKNOWN if index == 4 else maturity.GateOutcome.PASS,
        )
        for index in range(10)
    )
    result = vq_models.Gold10VerifierQualification(
        pilot_id="gold10-flagship-pilot-v1",
        taskset_version="gold10-flagship-pilot-v1",
        verifier_target_contract_sha256=SHA_A,
        task_records=records,
        status=maturity.GateOutcome.UNKNOWN,
    )
    assert result.status == maturity.GateOutcome.UNKNOWN


def test_not_applicable_never_erases_fail() -> None:
    record = vq_models.Gold10TaskVerifierQualification(
        binding=vq_models.Gold10TaskBinding(
            case_id="case-x",
            task_id="GOLD10-case-x",
            split="eval",
            task_manifest_sha256="f" * 64,
            verifier_target_contract_sha256=SHA_A,
        ),
        report=_report(maturity.GateOutcome.FAIL),
    )
    assert record.effective_status == maturity.GateOutcome.FAIL
