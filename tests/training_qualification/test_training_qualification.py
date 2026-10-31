"""CONSTRUCTED evidence exercises logic; no model or training qualification is minted."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from investigation_world.capability_science import (
    AcquisitionCurve,
    CaseOutcome,
    EvaluationConditions,
    EvaluationPoint,
    EvaluationPopulation,
    TrainingIntervention,
)
from investigation_world.capability_science.core import CapabilitySpec
from investigation_world.experience import ExperienceReference
from investigation_world.foundry.models import CapabilityContract, DistributionSplit
from investigation_world.foundry.training_product import (
    TrainerKind,
    TrainingBundle,
    TrainingExample,
    TrainingRecipe,
    TrainingRunManifest,
)
from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    GateOutcome,
    VerifierIdentity,
)
from investigation_world.training_qualification import (
    TrainingEvidence,
    TrainingPolicy,
    TrainingReplicate,
    assess_training,
    training_maturity_evidence,
)
from investigation_world.trajectory import canonical_hash

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def digest(value):
    return sha256(value.encode()).hexdigest()


def ref(name):
    return ExperienceReference(reference_id=name, reference_type="CONSTRUCTED", digest=digest(name))


def spec(name="repair"):
    return CapabilitySpec(contract=CapabilityContract(capability_id=name, objective=name))


def population(name, *, capability=None, split="HELD_OUT", structure="within-family"):
    return EvaluationPopulation(
        capability=capability or spec(),
        split=split,
        conditions=EvaluationConditions(
            environment_id="world",
            environment_revision="v1",
            verifier_id="verifier",
            verifier_revision="v1",
            metric="criterion_score",
            metric_definition_digest=digest("metric"),
            distribution_id=name,
            structure_id=structure,
            interface_id="interface-v1",
            evidence_references=(ref("conditions"),),
        ),
        members=tuple(ref(f"{name}-{i}") for i in range(4)),
        evidence_references=(ref(f"population-{name}"),),
    )


def point(panel, values, index, seed=0, **changes):
    fields = dict(
        population=panel,
        model_id="model",
        model_revision="base-checkpoint-v1" if index == 0 else f"checkpoint-{seed}-{index}",
        sequence_index=index,
        observed_at=NOW + timedelta(hours=index * 3),
        execution_provenance="CONSTRUCTED",
        evidence_references=(ref(f"point-{changes.get('model_id', 'model')}-{seed}-{index}"),),
        outcomes=tuple(
            CaseOutcome(
                member_id=m.reference_id,
                member_digest=m.digest,
                value=v,
                evidence_references=(
                    ref(
                        f"result-{changes.get('model_id', 'model')}-{seed}-{index}-{m.reference_id}"
                    ),
                )
                if v is not None
                else (),
                unavailable_reason="CONSTRUCTED missing" if v is None else None,
            )
            for m, v in zip(panel.members, values, strict=True)
        ),
    )
    fields.update(changes)
    return EvaluationPoint(**fields)


def curve(panel, train, bundle, seed=0, before=(0.2,) * 4, after=(0.6,) * 4):
    b, a = point(panel, before, 0, seed), point(panel, after, 1, seed)
    return AcquisitionCurve(
        points=(b, a),
        interventions=(
            TrainingIntervention(
                before_point_id=b.record_id,
                after_point_id=a.record_id,
                training_population=train,
                trainer_id="trainer",
                trainer_revision="v1",
                training_bundle_digest=canonical_hash(bundle),
                training_configuration_digest=canonical_hash({}),
                started_at=NOW + timedelta(hours=1),
                finished_at=NOW + timedelta(hours=2),
                execution_provenance="CONSTRUCTED",
                evidence_references=(ref(f"training-{seed}"),),
            ),
        ),
    )


def evidence(*, heldout_after=(0.6,) * 4, seeds=(1, 2), include_guardrail=True):
    target, guard = spec(), spec("unrelated")
    train = population("train", split="TRAIN")
    heldout = population("heldout")
    ood = population("ood", structure="new-structure")
    unrelated = population("guardrail", capability=guard)
    bundle = TrainingBundle(
        bundle_id="CONSTRUCTED-bundle",
        capability_contract=target.contract,
        recipe=TrainingRecipe(
            recipe_id="recipe",
            trainer=TrainerKind.SFT,
            capability_contract_id=target.contract.capability_id,
        ),
        train_examples=[
            TrainingExample(
                example_id=m.reference_id,
                trajectory_id=f"t{i}",
                task_id=m.reference_id,
                split=DistributionSplit.TRAIN,
                trainer=TrainerKind.SFT,
                trace_ref="constructed",
                verifier_score=1,
            )
            for i, m in enumerate(train.members)
        ],
        metadata={
            "verified_learning_lineage": [
                dict(
                    verified_trajectory_id=f"t{i}",
                    task_id=m.reference_id,
                    source_id=m.reference_id,
                    source_digest=m.digest,
                    experience_id=f"e{i}",
                    trajectory_id=f"r{i}",
                )
                for i, m in enumerate(train.members)
            ]
        },
    )
    reps = tuple(
        TrainingReplicate(
            seed=s,
            manifest=TrainingRunManifest(
                run_id=f"run-{s}",
                bundle_id=bundle.bundle_id,
                trainer=TrainerKind.SFT,
                base_model="model",
                trainer_version="v1",
                seed=s,
            ),
            train=curve(train, train, bundle, s),
            heldout=curve(heldout, train, bundle, s, after=heldout_after),
            learnability=point(heldout, (1.0,) * 4, 0, s, model_id="expert"),
            transfer=(curve(ood, train, bundle, s),),
            guardrails=(curve(unrelated, train, bundle, s, before=(0.8,) * 4, after=(0.8,) * 4),)
            if include_guardrail
            else (),
        )
        for s in seeds
    )
    return TrainingEvidence(
        capability=target,
        environment_identity=EnvironmentIdentity(
            environment_id="world", environment_version="v1", content_sha256=digest("world")
        ),
        verifier_identity=VerifierIdentity(
            verifier_id="verifier", verifier_version="v1", content_sha256=digest("verifier")
        ),
        bundle=bundle,
        configuration_digest=canonical_hash({}),
        expected_seeds=(1, 2),
        required_guardrail_capabilities=(guard.contract_digest,),
        replicates=reps,
        provenance="CONSTRUCTED",
        evidence_references=(ref("study"),),
    )


def outcomes(report):
    return {g.name: g.outcome for g in report.gates}


def test_constructed_positive_measurements_cannot_attest_execution_or_promote():
    report = assess_training(
        evidence(), policy=TrainingPolicy(minimum_replicates=2, minimum_population=4)
    )
    gates = outcomes(report)
    assert gates["held_out_improvement"] == "PASS"
    assert gates["replicate_stability"] == "PASS"
    assert gates["execution_and_chronology"] == "UNKNOWN"
    assert report.status == "UNKNOWN"  # also no exploit evidence, never silently PASS
    assert report.capability_gain is None
    assert all(
        item.outcome == "UNKNOWN"
        for item in training_maturity_evidence(
            report, qualification_policy_version="test", observed_at=NOW
        )
    )


def test_training_memorization_does_not_pass_heldout_gate():
    report = assess_training(
        evidence(heldout_after=(0.2,) * 4),
        policy=TrainingPolicy(minimum_population=4, minimum_replicates=2),
    )
    assert outcomes(report)["held_out_improvement"] == "FAIL"
    assert report.status == "FAIL"


def test_missing_seed_or_guardrail_never_passes():
    report = assess_training(
        evidence(seeds=(1,), include_guardrail=False),
        policy=TrainingPolicy(minimum_population=4, minimum_replicates=2),
    )
    assert outcomes(report)["replicate_stability"] == "UNKNOWN"
    assert outcomes(report)["unrelated_capability_guardrails"] == "UNKNOWN"
    assert report.expected_replicates == 2 and report.observed_replicates == 1


def test_unknown_rows_are_counted_not_dropped():
    report = assess_training(
        evidence(heldout_after=(None, 0.6, 0.6, 0.6)),
        policy=TrainingPolicy(minimum_population=4, minimum_replicates=2),
    )
    assert outcomes(report)["held_out_improvement"] == "UNKNOWN"
    rows = [x for x in report.panels if x.role == "heldout"]
    assert all(
        x.expected_count == 4 and x.after_unknown_count == 1 and x.delta is None for x in rows
    )


def test_whole_private_report_projection_withholds_every_identity():
    report = assess_training(evidence())
    assert report.public_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}
    assert report.buyer_safe_payload() == report.public_payload()
    assert "CONSTRUCTED-bundle" not in str(report.public_payload())


def test_nested_tampering_is_revalidated():
    data = evidence()
    data.bundle.metadata["verified_learning_lineage"][0]["source_digest"] = digest("substitute")
    with pytest.raises(ValueError):
        assess_training(data)


def rebuild(value, **changes):
    payload = value.model_dump(mode="python")
    payload.update(changes)
    payload["record_id"] = ""
    return type(value).model_validate(payload)


def add_exploits(data, *, succeeded=False, missing=False):
    from investigation_world.training_qualification import ExploitPanel
    from investigation_world.verifier_monitoring.models import (
        DisclosureLevel,
        DiscoverySource,
        ExploitClass,
        ExploitCorpus,
        ExploitEvidenceReference,
        ExploitFinding,
        ExploitRegressionObservation,
        ExploitSeverity,
        RegressionOutcome,
    )

    reference = ExploitEvidenceReference(
        evidence_id="constructed-exploit",
        content_sha256=digest("x"),
        reference_uri="constructed:private",
        disclosure=DisclosureLevel.OPERATOR_PRIVATE,
    )
    finding = ExploitFinding(
        exploit_class=ExploitClass.REWARD_HACK,
        severity=ExploitSeverity.LOW,
        environment_identity=data.environment_identity,
        verifier_identity=data.verifier_identity,
        reproducer=reference,
        discovery_source=DiscoverySource.SYNTHETIC_FALSIFIER,
        discovered_at=NOW,
        summary="PRIVATE-CONSTRUCTED-EXPLOIT",
        provenance={"fixture": True},
    )
    corpus = ExploitCorpus(schema_version="v1", findings=(), dispositions=()).append_finding(
        finding, recorded_at=NOW, provenance={"fixture": True}
    )
    reps = []
    for rep in data.replicates:
        observations = tuple(
            ExploitRegressionObservation(
                exploit_id=finding.exploit_id,
                environment_identity=data.environment_identity,
                verifier_identity=data.verifier_identity,
                outcome=RegressionOutcome.SUCCEEDED
                if succeeded and i
                else RegressionOutcome.BLOCKED,
                canonical_reward=0,
                observed_reward=0,
                evidence=ExploitEvidenceReference(
                    evidence_id=f"phase-{rep.seed}-{i}",
                    content_sha256=digest(f"phase-{rep.seed}-{i}"),
                    reference_uri="constructed:phase",
                    disclosure=DisclosureLevel.OPERATOR_PRIVATE,
                ),
                observed_at=NOW + timedelta(hours=i * 3),
                provenance={"fixture": True},
            )
            for i in (0, 1)
        )
        b, a = rep.heldout.points
        panel = ExploitPanel(
            corpus=corpus,
            before=(observations[0],),
            after=() if missing else (observations[1],),
            before_checkpoint=canonical_hash((b.model_id, b.model_revision)),
            after_checkpoint=canonical_hash((a.model_id, a.model_revision)),
            observed_at=NOW,
        )
        reps.append(rebuild(rep, exploits=panel))
    return rebuild(data, replicates=tuple(reps))


def test_all_conditional_gates_pass_only_for_constructed_complete_evidence():
    report = assess_training(
        add_exploits(evidence()), policy=TrainingPolicy(minimum_population=4, minimum_replicates=2)
    )
    assert all(
        g.outcome == "PASS"
        for g in report.gates
        if g.name not in {"execution_and_chronology", "memorization_and_near_duplicate_probes"}
    )
    assert report.status == "UNKNOWN"
    assert report.training_validated is False
    assert report.mean_recorded_heldout_delta == pytest.approx(0.4)


@pytest.mark.parametrize(
    "succeeded,missing,expected", [(True, False, "FAIL"), (False, True, "UNKNOWN")]
)
def test_exploit_regression_and_missing_replays_are_not_hidden(succeeded, missing, expected):
    report = assess_training(
        add_exploits(evidence(), succeeded=succeeded, missing=missing),
        policy=TrainingPolicy(minimum_population=4, minimum_replicates=2),
    )
    assert outcomes(report)["reward_exploitation_regression"] == expected
    maturity = {
        g.gate: g.outcome
        for g in training_maturity_evidence(
            report, qualification_policy_version="test", observed_at=NOW
        )
    }
    assert maturity["reward_exploitation_regression"] == expected
    assert maturity["multi_seed_stability"] == "UNKNOWN"


def test_loss_only_or_frontier_discovery_has_no_qualification_path():
    report = assess_training(rebuild(evidence(), replicates=()))
    assert report.status == "UNKNOWN"
    assert report.observed_replicates == 0
    with pytest.raises(ValueError):
        rebuild(evidence(), lm_loss=0.01)


def test_unknown_proof_cannot_hide_observed_unrelated_regression():
    data = evidence()
    reps = []
    for rep in data.replicates:
        guard = rep.guardrails[0]
        negative = curve(
            guard.points[0].population,
            rep.train.points[0].population,
            data.bundle,
            rep.seed,
            before=(0.8,) * 4,
            after=(0.6,) * 4,
        )
        reps.append(rebuild(rep, guardrails=(negative,)))
    report = assess_training(rebuild(data, replicates=tuple(reps)))
    assert outcomes(report)["unrelated_capability_guardrails"] == "FAIL"
    assert report.status == "FAIL"


def test_one_successful_seed_does_not_erase_failed_seed():
    data = evidence()
    rep = data.replicates[1]
    failed = curve(
        rep.heldout.points[0].population,
        rep.train.points[0].population,
        data.bundle,
        rep.seed,
        after=(0.1,) * 4,
    )
    report = assess_training(
        rebuild(data, replicates=(data.replicates[0], rebuild(rep, heldout=failed))),
        policy=TrainingPolicy(minimum_population=4, minimum_replicates=2),
    )
    assert outcomes(report)["replicate_stability"] == "FAIL"
    assert outcomes(report)["held_out_improvement"] == "FAIL"
    assert len([row for row in report.panels if row.role == "heldout"]) == 2


def test_maturity_adapter_does_not_accept_forged_report_outcomes():
    report = assess_training(evidence())
    payload = report.model_dump(mode="python")
    payload.update(record_id="", status="PASS", training_validated=False)
    with pytest.raises(ValueError, match="recomputed"):
        type(report).model_validate(payload)
    with pytest.raises(ValueError):
        training_maturity_evidence(
            report.model_copy(update={"status": GateOutcome.PASS}),
            qualification_policy_version="test",
            observed_at=NOW,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_seeds", (1, 1)),
        ("expected_seeds", (True, 2)),
        ("execution_attestation_provider", "TRUST_ME"),
        ("visibility", "public"),
    ],
)
def test_strict_protocol_and_privacy_fields(field, value):
    with pytest.raises(ValueError):
        rebuild(evidence(), **{field: value})


def test_incomplete_duplicate_or_replaced_member_is_rejected_not_intersected():
    data = evidence()
    point = data.replicates[0].heldout.points[0]
    for rows in (point.outcomes[:-1], (point.outcomes[0],) * 4):
        with pytest.raises(ValueError):
            rebuild(point, outcomes=rows)


def test_seed_panels_must_not_change_population():
    data = evidence()
    rep = data.replicates[1]
    shifted = curve(
        population("other-heldout"), rep.train.points[0].population, data.bundle, rep.seed
    )
    with pytest.raises(ValueError):
        rebuild(
            data, replicates=(data.replicates[0], rebuild(rep, heldout=shifted, learnability=None))
        )


def test_heldout_metric_semantics_cannot_differ_from_train():
    data = evidence()
    rep = data.replicates[0]
    panel = rep.heldout.points[0].population
    panel = rebuild(
        panel, conditions=rebuild(panel.conditions, metric_definition_digest=digest("other"))
    )
    changed = curve(panel, rep.train.points[0].population, data.bundle, rep.seed)
    with pytest.raises(ValueError, match="metric"):
        rebuild(
            data, replicates=(rebuild(rep, heldout=changed, learnability=None), data.replicates[1])
        )


def test_source_digest_permutation_cannot_relabel_training_members():
    data = evidence()
    bundle = data.bundle.model_copy(deep=True)
    rows = bundle.metadata["verified_learning_lineage"]
    rows[0]["source_digest"], rows[1]["source_digest"] = (
        rows[1]["source_digest"],
        rows[0]["source_digest"],
    )
    reps = []
    for rep in data.replicates:

        def rebound(item):
            step = rebuild(item.interventions[0], training_bundle_digest=canonical_hash(bundle))
            return rebuild(item, interventions=(step,))

        reps.append(
            rebuild(
                rep,
                train=rebound(rep.train),
                heldout=rebound(rep.heldout),
                transfer=tuple(rebound(x) for x in rep.transfer),
                guardrails=tuple(rebound(x) for x in rep.guardrails),
            )
        )
    with pytest.raises(ValueError, match="exact bundle lineage"):
        rebuild(data, bundle=bundle, replicates=tuple(reps))


def test_copied_exploit_phase_evidence_cannot_count_as_before_and_after():
    data = add_exploits(evidence())
    panel = data.replicates[0].exploits
    with pytest.raises(ValueError, match="distinct observations"):
        rebuild(panel, after=panel.before)
    after = panel.after[0].model_copy(
        update={"evidence": panel.before[0].evidence, "observation_id": ""}
    )
    with pytest.raises(ValueError, match="distinct replay"):
        rebuild(panel, after=(after,))


def test_same_structure_distribution_shift_is_not_broad_structural_transfer():
    data = evidence()
    reps = []
    for rep in data.replicates:
        same_structure = population("renamed-ood", structure="within-family")
        transfer = curve(same_structure, rep.train.points[0].population, data.bundle, rep.seed)
        reps.append(rebuild(rep, transfer=(transfer,)))
    report = assess_training(rebuild(data, replicates=tuple(reps)))
    assert outcomes(report)["ood_transfer"] == "UNKNOWN"
    assert all(
        "STRUCTURAL_OOD" not in p.transfer_classifications
        for p in report.panels
        if p.role == "transfer"
    )


def test_post_training_score_gap_is_not_hidden_by_small_train_gain():
    data = evidence(heldout_after=(0.3,) * 4)
    reps = tuple(
        rebuild(
            rep,
            train=curve(
                rep.train.points[0].population,
                rep.train.points[0].population,
                data.bundle,
                rep.seed,
                before=(0.9,) * 4,
                after=(1.0,) * 4,
            ),
        )
        for rep in data.replicates
    )
    report = assess_training(rebuild(data, replicates=reps))
    assert outcomes(report)["overfit_and_memorization"] == "FAIL"


def test_actual_manifest_configuration_is_bound():
    data = evidence()
    rep = data.replicates[0]
    manifest = rep.manifest.model_copy(update={"parameters": {"different": True}})
    with pytest.raises(ValueError, match="configuration"):
        rebuild(data, replicates=(rebuild(rep, manifest=manifest), data.replicates[1]))


def replace_curve_model(item, model):
    before, after = (rebuild(p, model_id=model) for p in item.points)
    step = rebuild(
        item.interventions[0], before_point_id=before.record_id, after_point_id=after.record_id
    )
    return rebuild(item, points=(before, after), interventions=(step,))


def test_different_models_cannot_count_as_seeds_of_one_experiment():
    data = evidence()
    rep = data.replicates[1]
    changed = rebuild(
        rep,
        manifest=rep.manifest.model_copy(update={"base_model": "other-model"}),
        train=replace_curve_model(rep.train, "other-model"),
        heldout=replace_curve_model(rep.heldout, "other-model"),
        transfer=tuple(replace_curve_model(x, "other-model") for x in rep.transfer),
        guardrails=tuple(replace_curve_model(x, "other-model") for x in rep.guardrails),
    )
    with pytest.raises(ValueError, match="experiment model/checkpoint/trainer"):
        rebuild(data, replicates=(data.replicates[0], changed))


def test_inconsistent_training_times_are_not_hidden_by_valid_individual_curves():
    data = evidence()
    rep = data.replicates[0]
    item = rep.heldout
    step = rebuild(item.interventions[0], started_at=NOW + timedelta(hours=1, minutes=1))
    changed = rebuild(item, interventions=(step,))
    with pytest.raises(ValueError, match="intervention chronology"):
        rebuild(data, replicates=(rebuild(rep, heldout=changed), data.replicates[1]))


def test_reused_after_training_exploit_as_baseline_is_rejected():
    data = add_exploits(evidence())
    rep = data.replicates[0]
    row = rep.exploits.before[0]
    payload = row.model_dump(mode="python")
    payload.update(observation_id="", observed_at=NOW + timedelta(hours=2))
    changed = type(row).model_validate(payload)
    panel = rebuild(rep.exploits, before=(changed,))
    with pytest.raises(ValueError, match="chronology|precede training"):
        rebuild(data, replicates=(rebuild(rep, exploits=panel), data.replicates[1]))


def test_unpinned_and_nonfinite_fields_fail_closed():
    for value in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            TrainingPolicy(minimum_heldout_gain=value)
    data = evidence()
    with pytest.raises(ValueError, match="pinned"):
        rebuild(
            data,
            verifier_identity=VerifierIdentity(
                verifier_id="verifier", verifier_version="latest", content_sha256=digest("verifier")
            ),
        )


def test_maturity_order_stays_frontier_then_training():
    from investigation_world.qualification.maturity import MATURITY_ORDER, EnvironmentMaturity

    assert MATURITY_ORDER.index(EnvironmentMaturity.FRONTIER_QUALIFIED) + 1 == MATURITY_ORDER.index(
        EnvironmentMaturity.TRAINING_VALIDATED
    )


def test_validation_error_does_not_echo_private_input_payload():
    data = evidence().model_dump(mode="python")
    data.update(record_id="", visibility="public", private_note="PRIVATE-CANARY-TEXT")
    with pytest.raises(ValueError) as error:
        TrainingEvidence.model_validate(data)
    assert "PRIVATE-CANARY-TEXT" not in str(error.value)


def test_partial_panel_times_cannot_hide_reversed_combined_training_interval():
    data = evidence()
    rep = data.replicates[0]
    train_step = rebuild(
        rep.train.interventions[0], started_at=NOW + timedelta(hours=2), finished_at=None
    )
    heldout_step = rebuild(
        rep.heldout.interventions[0], started_at=None, finished_at=NOW + timedelta(hours=1)
    )
    train = rebuild(rep.train, interventions=(train_step,))
    heldout = rebuild(rep.heldout, interventions=(heldout_step,))
    changed = rebuild(rep, train=train, heldout=heldout, transfer=(), guardrails=())
    with pytest.raises(ValueError, match="chronology"):
        rebuild(data, replicates=(changed,))


def test_missing_heldout_times_cannot_bypass_known_train_exploit_chronology():
    data = add_exploits(evidence())
    rep = data.replicates[0]
    step = rebuild(rep.heldout.interventions[0], started_at=None, finished_at=None)
    heldout = rebuild(rep.heldout, interventions=(step,))
    payload = rep.exploits.before[0].model_dump(mode="python")
    payload.update(observation_id="", observed_at=NOW + timedelta(hours=2))
    row = type(rep.exploits.before[0]).model_validate(payload)
    panel = rebuild(rep.exploits, before=(row,))
    with pytest.raises(ValueError, match="chronology|precede"):
        rebuild(
            data, replicates=(rebuild(rep, heldout=heldout, exploits=panel), data.replicates[1])
        )


def test_learnability_cannot_reuse_the_trained_model_result_as_independent_control():
    data = evidence(heldout_after=(0.9,) * 4)
    rep = data.replicates[0]
    with pytest.raises(ValueError, match="independent control"):
        rebuild(
            data, replicates=(rebuild(rep, learnability=rep.heldout.points[1]), data.replicates[1])
        )


def test_known_failed_seed_remains_failure_when_another_expected_seed_is_missing():
    report = assess_training(
        evidence(seeds=(1,), heldout_after=(0.1,) * 4),
        policy=TrainingPolicy(minimum_population=4, minimum_replicates=2),
    )
    assert outcomes(report)["replicate_stability"] == "FAIL"
    assert report.observed_replicates == 1 and report.expected_replicates == 2
