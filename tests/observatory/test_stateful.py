"""CONSTRUCTED ordinary conformance checks; no architecture or model is executed."""

from datetime import datetime, timezone
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from investigation_world.capability_science import (
    CapabilitySpec,
    CaseOutcome,
    EvaluationConditions,
    EvaluationPoint,
    EvaluationPopulation,
)
from investigation_world.evidence.models import EvidenceOutcome, EvidenceVisibility
from investigation_world.experience import ExperienceReference
from investigation_world.foundry.models import CapabilityContract
from investigation_world.observatory.stateful import (
    ImportedRun,
    ResourceMeasurement,
    RunManifest,
    StateCheck,
    StateComponent,
    StatefulReport,
    StatefulStudy,
    TimingContext,
    assess_stateful,
    shared_stateful_evidence,
)
from investigation_world.trajectory import VisibilityClass


def ref(name):
    return ExperienceReference(
        reference_id=name,
        reference_type="constructed_fixture",
        digest=sha256(name.encode()).hexdigest(),
        visibility=VisibilityClass.PUBLIC,
    )


def population(metric):
    return EvaluationPopulation(
        capability=CapabilitySpec(
            contract=CapabilityContract(
                capability_id="constructed-recall",
                objective="Public two-case recall fixture",
                success_conditions=["whole answer equals target"],
            )
        ),
        conditions=EvaluationConditions(
            environment_id="fixture",
            environment_revision="fixture-v1",
            verifier_id="equality",
            verifier_revision="equality-v1",
            metric=metric,
            metric_definition_digest=ref(metric).digest,
            distribution_id="fixture-dist-v1",
            structure_id="key-value-v1",
            interface_id="stream-v1",
            evidence_references=(ref("conditions"),),
        ),
        split="HELD_OUT",
        members=(ref("query-a"), ref("query-b")),
        evidence_references=(ref("population"),),
    )


def manifest(seed=1, **changes):
    values = dict(
        family="psn",
        arm="fixture",
        condition="delayed-recall",
        init_seed=seed,
        data_seed=7,
        model_id="constructed-kv",
        source_revision="constructed-fixture-v1",
        source_provenance="CONSTRUCTED",
        exact_population=population("success_fraction"),
        criterion_population=population("criterion_score"),
        **{
            name: ref(name)
            for name in (
                "protocol",
                "source",
                "configuration",
                "checkpoint",
                "stream",
                "adapter",
                "evaluator",
                "runtime",
            )
        },
    )
    values.update(changes)
    return RunManifest(**values)


def point(plan, panel, values):
    return EvaluationPoint(
        population=panel,
        model_id=plan.model_id,
        model_revision=plan.checkpoint.digest,
        sequence_index=0,
        execution_provenance="CONSTRUCTED",
        outcomes=tuple(
            CaseOutcome(
                member_id=m.reference_id,
                member_digest=m.digest,
                value=value,
                evidence_references=(ref(f"{plan.record_id}-{panel.record_id}-{i}"),)
                if value is not None
                else (),
                unavailable_reason="not observed" if value is None else None,
            )
            for i, (m, value) in enumerate(zip(panel.members, values, strict=True))
        ),
        evidence_references=(ref(f"point-{plan.record_id}-{panel.record_id}"),),
    )


def run(plan=None, **changes):
    plan = plan or manifest()
    values = dict(
        manifest=plan,
        status="completed",
        provenance="CONSTRUCTED",
        exact=point(plan, plan.exact_population, (1.0, 0.0)) if plan.exact_population else None,
        criterion=point(plan, plan.criterion_population, (1.0, 0.75))
        if plan.criterion_population
        else None,
        native_acceptance={"query-a": True, "query-b": True},
        policy_acceptance={"query-a": False, "query-b": False},
        policy=ref("risk-policy-bit-error"),
        evidence_references=(ref("receipt"),),
    )
    values.update(changes)
    return ImportedRun(**values)


def test_complete_exact_and_criterion_are_separate_and_zero_coverage_undefined():
    receipt = run()
    report = assess_stateful(StatefulStudy(expected=(receipt.manifest,), runs=(receipt,)))
    row = report.rows[0]
    assert row.exact_mean == 0.5
    assert row.criterion_mean == 0.875
    assert row.native.coverage == 1.0
    assert row.native.accepted_exact == 0.5
    assert row.native.accepted_exact_error == 0.5
    assert row.native.accepted_criterion == 0.875
    assert row.policy.coverage == 0.0
    assert row.policy.accepted_exact is None
    assert row.policy.accepted_exact_error is None
    assert row.policy.accepted_criterion is None
    assert report.execution_attestation == "UNKNOWN"
    assert report.scientific_qualification == "UNKNOWN"
    assert report.capability_gain is None


def test_missing_and_failed_seed_stay_in_exact_planned_matrix():
    first, second, third = manifest(1), manifest(2), manifest(3)
    failed = ImportedRun(
        manifest=second,
        status="failed",
        reason="fixture deliberately stopped",
        provenance="CONSTRUCTED",
        evidence_references=(ref("failed"),),
    )
    report = assess_stateful(
        StatefulStudy(expected=(first, second, third), runs=(run(first), failed))
    )
    assert [row.status for row in report.rows] == ["completed", "failed", "missing"]
    assert report.expected_runs == 3
    assert report.completed_runs == 1
    assert report.missing_runs == 1
    assert report.complete_matrix is False
    assert all(row.population_size == 2 for row in report.rows)
    assert report.rows[2].native is None


def test_report_reparses_and_recomputes_arithmetic():
    receipt = run()
    report = assess_stateful(StatefulStudy(expected=(receipt.manifest,), runs=(receipt,)))
    assert StatefulReport.model_validate_json(report.model_dump_json()) == report
    payload = report.model_dump(mode="python")
    payload["record_id"] = ""
    payload["rows"][0]["record_id"] = ""
    payload["rows"][0]["exact_mean"] = 1.0
    with pytest.raises(ValueError):
        StatefulReport.model_validate(payload)


def test_complete_expected_population_and_mask_membership_are_required():
    plan = manifest()
    with pytest.raises(ValueError):
        run(plan, native_acceptance={"query-a": True})
    with pytest.raises(ValueError):
        run(plan, policy_acceptance={"query-a": True, "other": False})
    alternate = population("success_fraction").model_dump(mode="python")
    alternate["record_id"] = ""
    alternate["members"] = alternate["members"][:1]
    smaller = EvaluationPopulation.model_validate(alternate)
    with pytest.raises(ValueError):
        run(plan, exact=point(plan, smaller, (1.0,)))


def test_unknown_observations_and_acceptances_do_not_become_zero_or_disappear():
    plan = manifest()
    receipt = run(
        plan,
        exact=point(plan, plan.exact_population, (1.0, None)),
        native_acceptance={"query-a": True, "query-b": None},
    )
    row = assess_stateful(StatefulStudy(expected=(plan,), runs=(receipt,))).rows[0]
    assert row.exact_mean is None
    assert row.exact_unknown == 1
    assert row.criterion_unknown == 0
    assert row.native.unknown == 1
    assert row.native.coverage is None
    assert row.native.accepted_exact is None


def test_metric_checkpoint_and_duplicate_slot_mismatch_reject():
    plan = manifest()
    with pytest.raises(ValueError):
        run(plan, exact=point(plan, plan.criterion_population, (1.0, 0.0)))
    changed = point(plan, plan.exact_population, (1.0, 0.0)).model_dump(mode="python")
    changed.update(record_id="", model_revision="foreign-checkpoint")
    with pytest.raises(ValueError):
        run(plan, exact=EvaluationPoint.model_validate(changed))
    with pytest.raises(ValueError):
        StatefulStudy(expected=(plan, plan), runs=(run(plan),))
    with pytest.raises(ValueError):
        StatefulStudy(expected=(plan,), runs=(run(manifest(2)),))


def timing():
    return TimingContext(
        method="perf_counter_ns; nearest-rank quantiles",
        hardware="constructed CPU",
        runtime=ref("runtime"),
        import_path="/constructed/fixture.py",
        imported_source=ref("source"),
        import_evidence=ref("retained-import-path-and-byte-hash-observation"),
        threads=1,
        batch_size=1,
        stream_steps=4,
        warmups=1,
        repetitions=20,
        boundary="whole stream, inference only",
        samples=ref("timing-samples"),
    )


def resource(**changes):
    values = dict(
        metric="latency_p95",
        unit="second",
        scope="one stream",
        value=0.002,
        provenance="CONSTRUCTED",
        measurement=ref("timing-record"),
        timing=timing(),
    )
    values.update(changes)
    return ResourceMeasurement(**values)


def test_resource_units_timing_scope_unknowns_and_provenance_are_explicit():
    assert resource().value == 0.002
    for changes in (
        {"unit": "bytes"},
        {"timing": None},
        {"value": float("nan")},
        {"provenance": "UNKNOWN"},
        {"value": -1.0},
    ):
        with pytest.raises(ValueError):
            resource(**changes)
    unknown = resource(value=None, timing=None, provenance="UNKNOWN", reason="not measured")
    assert unknown.value is None
    assert resource(metric="state_bytes", unit="byte", value=16, timing=None).value == 16
    with pytest.raises(ValueError):
        resource(metric="state_bytes", unit="byte", value=1.5, timing=None)


def test_state_ownership_and_intervention_scopes_are_bound_without_causal_claims():
    component = StateComponent(
        component_id="memory",
        owner_id="stream-a",
        scope="transient",
        bytes=16,
        evidence_references=(ref("memory"),),
    )
    check = StateCheck(
        kind="query_erasure",
        component_ids=("memory",),
        status="OBSERVED",
        provenance="CONSTRUCTED",
        detail="Synthetic memory becomes empty before query",
        evidence_references=(ref("erasure"),),
    )
    receipt = run(components=(component,), checks=(check,))
    assert receipt.checks[0].kind == "query_erasure"
    with pytest.raises(ValueError):
        run(components=(), checks=(check,))
    with pytest.raises(ValueError):
        StateCheck(kind="reset", component_ids=("memory",), status="OBSERVED", provenance="UNKNOWN")


def test_private_projection_and_shared_observed_envelope():
    receipt = run()
    report = assess_stateful(StatefulStudy(expected=(receipt.manifest,), runs=(receipt,)))
    assert report.public_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}
    assert report.buyer_safe_payload() == report.public_payload()
    evidence = shared_stateful_evidence(
        report,
        observed_at=datetime(2026, 10, 31, tzinfo=timezone.utc),
        producer=ref("adapter"),
    )
    assert evidence.outcome == EvidenceOutcome.OBSERVED
    assert evidence.visibility == EvidenceVisibility.OPERATOR_PRIVATE
    assert evidence.subjects[0].subject_id == report.record_id
    assert "attestation" in evidence.claim


def test_sealed_references_and_self_asserted_attestation_reject():
    sealed = ref("sealed").model_copy(update={"visibility": VisibilityClass.SEALED})
    with pytest.raises(ValueError):
        manifest(source=sealed)
    with pytest.raises(ValueError):
        run(execution_attestation="PASS")


def test_component_owner_scope_is_distinct_from_state_kind():
    component = StateComponent(
        component_id="rng",
        owner_id="process",
        scope="rng",
        owner_scope="shared",
        bytes=None,
        reason="not measured",
        evidence_references=(ref("rng"),),
    )
    assert component.owner_scope == "shared"
    assert component.scope == "rng"


def test_acceptance_requires_literal_booleans_not_coerced_strings_or_numbers():
    for value in ("true", 1, 0):
        with pytest.raises(ValueError):
            run(native_acceptance={"query-a": value, "query-b": False})


def test_constructed_family_and_fixed_physical_resource_units():
    assert manifest(family="constructed").family == "constructed"
    for metric, unit in (
        ("flops", "FLOP"),
        ("cpu_core_seconds", "CPU-core-second"),
        ("energy_joules", "joule"),
    ):
        assert resource(metric=metric, unit=unit, value=2, timing=None).value == 2


def fixture_module():
    # Installed verification copies this public example beside tests, never package source.
    path = Path(__file__).resolve().parents[2] / "examples" / "stateful_evaluation.py"
    spec = spec_from_file_location("public_stateful_fixture", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_fixture_replays_predictions_before_feedback_and_is_repeatable():
    fixture = fixture_module()
    baseline = fixture.replay_fixture()
    assert fixture.replay_fixture() == baseline
    rows = baseline["rows"]
    assert len(rows) == 6
    assert sum(row["exact"] for row in rows) / len(rows) == 0.5
    assert sum(row["component"] for row in rows) / len(rows) == 0.75
    assert sum(row["native_accept"] for row in rows) == 3
    assert sum(row["policy_accept"] for row in rows) == 0
    assert rows[0]["answer"] == (0, 0)
    assert rows[0]["target"] == (1, 0)
    assert {row["stream"] for row in rows} == {"A", "B"}
    erased = fixture.replay_fixture(erase_before_final=True)["rows"]
    assert sum(row["exact"] for row in erased) / len(erased) == 1 / 3
    assert sum(row["component"] for row in erased) / len(erased) == 2 / 3
    assert sum(row["native_accept"] for row in erased) == 2
    assert all(fixture.check_fixture_lifecycle().values())


def test_actual_fixture_import_provenance_matches_independent_module_bytes():
    import investigation_world.observatory.stateful as implementation

    fixture = fixture_module()
    module = Path(implementation.__file__).resolve()
    expected = sha256(module.read_bytes()).hexdigest()
    observed = fixture.local_import_provenance(expected)
    assert observed["source_comparison"] == "MATCH"
    assert observed["module_path"] == str(module)
    assert observed["module_sha256"] == expected
    assert observed["cpu_timing"] == "NOT_RUN"
    with pytest.raises(ValueError, match="actual imported module"):
        fixture.local_import_provenance("0" * 64)


def test_public_fixture_report_preserves_expected_cells_and_unknown_resources():
    report = fixture_module().fixture_report()
    baseline, erased = report.rows
    assert report.expected_runs == report.completed_runs == 2
    assert report.missing_runs == 0
    assert baseline.exact_mean == 0.5
    assert baseline.criterion_mean == 0.75
    assert erased.exact_mean == 1 / 3
    assert erased.criterion_mean == 2 / 3
    assert baseline.native.accepted == 3
    assert erased.native.accepted == 2
    assert all(row.policy.coverage == 0 for row in report.rows)
    assert all(row.policy.accepted_exact_error is None for row in report.rows)
    assert all(plan.family == "constructed" for plan in report.study.expected)
    assert all(run.resources[0].value is None for run in report.study.runs)
    assert all(check.passed for run in report.study.runs for check in run.checks)
    assert report.execution_attestation == report.actual_import_verified == "UNKNOWN"
    assert report.public_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}


def test_exact_metric_absence_is_explicit_and_never_invented_from_criterion():
    plan = manifest(exact_population=None, exact_unavailable_reason="not applicable: regression")
    receipt = run(plan, exact=None)
    row = assess_stateful(StatefulStudy(expected=(plan,), runs=(receipt,))).rows[0]
    assert row.exact_mean is None
    assert row.exact_unknown is None
    assert row.native.accepted_exact_error is None
    assert row.criterion_mean == 0.875
    with pytest.raises(ValueError):
        manifest(exact_population=None)


def test_timing_binds_timed_implementation_not_receipt_adapter():
    plan = manifest()
    context = timing().model_dump(mode="python")
    for missing in ("import_path", "imported_source", "import_evidence"):
        fields = {key: value for key, value in context.items() if key not in (missing, "record_id")}
        with pytest.raises(ValueError):
            TimingContext.model_validate(fields)
    changed = {**context, "record_id": "", "imported_source": plan.adapter}
    with pytest.raises(ValueError, match="timed imported implementation"):
        run(plan, resources=(resource(timing=TimingContext.model_validate(changed)),))
    assert run(plan, resources=(resource(),)).resources[0].timing.imported_source == plan.source


def test_one_measurement_artifact_can_support_distinct_nonadditive_quantiles():
    p50 = resource(metric="latency_p50", value=0.001)
    p95 = resource(metric="latency_p95", value=0.002)
    assert len(run(resources=(p50, p95)).resources) == 2
    with pytest.raises(ValueError, match="duplicate resource metric"):
        run(resources=(p50, p50))
    other_bytes = resource(measurement=ref("timing-record").model_copy(update={"digest": "a" * 64}))
    with pytest.raises(ValueError, match="different content"):
        run(resources=(p50, other_bytes))
