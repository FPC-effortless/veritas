from __future__ import annotations

from datetime import datetime, timezone

from investigation_world.qualification import (
    DEFAULT_MATURITY_POLICY,
    REQUIRED_VERIFIER_FIXTURE_CATEGORIES,
    EnvironmentIdentity,
    EnvironmentMaturity,
    GateOutcome,
    MaturityGateEvidence,
    VerifierFixture,
    VerifierFixtureCategory,
    VerifierFixtureManifest,
    VerifierIdentity,
    VerifierReplay,
    assess_environment_maturity,
    qualify_verifier,
    verifier_maturity_evidence,
)

NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)
ENVIRONMENT = EnvironmentIdentity(
    environment_id="ENV-verifier-suite",
    environment_version="1.0.0",
    content_sha256="a" * 64,
)
VERIFIER = VerifierIdentity(
    verifier_id="VER-under-test",
    verifier_version="1.0.0",
    content_sha256="b" * 64,
)


def _expected_pass(category: VerifierFixtureCategory) -> bool:
    return category in {
        VerifierFixtureCategory.CORRECT_SOLUTION,
        VerifierFixtureCategory.ALTERNATIVE_CORRECT_STRATEGY,
        VerifierFixtureCategory.NONDETERMINISTIC_PERTURBATION,
    }


def _manifest(
    *,
    excluded: set[VerifierFixtureCategory] | None = None,
) -> VerifierFixtureManifest:
    excluded = excluded or set()
    fixtures = []
    for index, category in enumerate(REQUIRED_VERIFIER_FIXTURE_CATEGORIES, start=1):
        if category in excluded:
            continue
        expected_pass = _expected_pass(category)
        fixtures.append(
            VerifierFixture(
                category=category,
                payload_sha256=f"{index:064x}",
                expected_pass=expected_pass,
                minimum_reward=1.0 if expected_pass else 0.0,
                maximum_reward=1.0 if expected_pass else 0.0,
                strategy_family=(
                    "non-reference-valid-strategy"
                    if category == VerifierFixtureCategory.ALTERNATIVE_CORRECT_STRATEGY
                    else None
                ),
                description=f"Falsifier fixture for {category.value}",
                provenance={"author": "independent-verifier-reviewer"},
            )
        )
    return VerifierFixtureManifest(
        suite_version="verifier-qualification-v1",
        environment_identity=ENVIRONMENT,
        verifier_identity=VERIFIER,
        fixtures=tuple(fixtures),
    )


def _replays(
    manifest: VerifierFixtureManifest,
    *,
    repetitions: int = 2,
) -> list[VerifierReplay]:
    values = []
    for fixture_index, fixture in enumerate(manifest.fixtures, start=1):
        for repetition in range(repetitions):
            values.append(
                VerifierReplay(
                    fixture_id=fixture.fixture_id,
                    repetition=repetition,
                    reward=1.0 if fixture.expected_pass else 0.0,
                    passed=fixture.expected_pass,
                    component_scores={"outcome": 1.0 if fixture.expected_pass else 0.0},
                    output_sha256=f"{fixture_index * 10 + repetition:064x}",
                    observed_at=NOW,
                    provenance={"runner": "deterministic-test-runner"},
                )
            )
    return values


def _maturity_evidence(gate: str) -> MaturityGateEvidence:
    return MaturityGateEvidence(
        gate=gate,
        outcome=GateOutcome.PASS,
        evidence_id=f"EVID-{gate}",
        content_sha256="d" * 64,
        environment_content_sha256=ENVIRONMENT.content_sha256,
        verifier_content_sha256=VERIFIER.content_sha256,
        qualification_policy_version=DEFAULT_MATURITY_POLICY.policy_version,
        observed_at=NOW,
        provenance={"runner": "unit-test"},
    )


def test_complete_falsifier_suite_qualifies_the_verifier() -> None:
    manifest = _manifest()
    report = qualify_verifier(manifest, _replays(manifest))

    assert report.qualified
    assert report.status == GateOutcome.PASS
    assert report.metrics["false_positive_rate"] == 0.0
    assert report.metrics["false_negative_rate"] == 0.0
    assert report.metrics["alternative_solution_acceptance"] == 1.0
    assert report.metrics["reward_hack_resistance"] == 1.0
    assert report.metrics["deterministic_reproduction"] == 1.0
    assert report.fixture_manifest_id == manifest.manifest_id
    assert report.replay_evidence_id.startswith("VREPLAY-")


def test_alternative_correct_strategy_is_not_compared_to_reference_trajectory() -> None:
    manifest = _manifest()
    alternative = next(
        fixture
        for fixture in manifest.fixtures
        if fixture.category == VerifierFixtureCategory.ALTERNATIVE_CORRECT_STRATEGY
    )
    assert alternative.strategy_family == "non-reference-valid-strategy"

    report = qualify_verifier(manifest, _replays(manifest))

    assert report.metrics["alternative_solution_acceptance"] == 1.0
    assert report.qualified


def test_known_reward_exploit_prevents_qualification() -> None:
    manifest = _manifest()
    replays = _replays(manifest)
    exploit_id = next(
        fixture.fixture_id
        for fixture in manifest.fixtures
        if fixture.category == VerifierFixtureCategory.REWARD_HACK
    )
    index = next(i for i, replay in enumerate(replays) if replay.fixture_id == exploit_id)
    replays[index] = replays[index].model_copy(update={"reward": 1.0, "passed": True})

    report = qualify_verifier(manifest, replays)

    assert not report.qualified
    assert report.status == GateOutcome.FAIL
    assert report.metrics["reward_hack_resistance"] < 1.0
    assert next(
        gate for gate in report.gates if gate.name == "known_unbounded_reward_exploits"
    ).outcome == GateOutcome.FAIL


def test_missing_falsifier_category_remains_unknown() -> None:
    manifest = _manifest(excluded={VerifierFixtureCategory.MALFORMED_ARTIFACT})

    report = qualify_verifier(manifest, _replays(manifest))

    assert report.status == GateOutcome.UNKNOWN
    assert not report.qualified
    coverage = next(gate for gate in report.gates if gate.name == "falsifier_fixture_coverage")
    assert coverage.outcome == GateOutcome.UNKNOWN


def test_single_replay_cannot_claim_deterministic_reproduction() -> None:
    manifest = _manifest()

    report = qualify_verifier(manifest, _replays(manifest, repetitions=1))

    assert report.status == GateOutcome.UNKNOWN
    assert report.metrics["deterministic_reproduction"] is None


def test_score_drift_fails_deterministic_reproduction() -> None:
    manifest = _manifest()
    replays = _replays(manifest)
    first_fixture_id = manifest.fixtures[0].fixture_id
    index = next(
        i
        for i, replay in enumerate(replays)
        if replay.fixture_id == first_fixture_id and replay.repetition == 1
    )
    replays[index] = replays[index].model_copy(update={"reward": 0.5})

    report = qualify_verifier(manifest, replays)

    assert report.status == GateOutcome.FAIL
    assert report.metrics["deterministic_reproduction"] < 1.0


def test_report_is_content_addressed_to_exact_replays() -> None:
    manifest = _manifest()
    first_replays = _replays(manifest)
    second_replays = _replays(manifest)
    second_replays[0] = second_replays[0].model_copy(update={"output_sha256": "e" * 64})

    first = qualify_verifier(manifest, first_replays)
    second = qualify_verifier(manifest, second_replays)

    assert first.metrics == second.metrics
    assert first.replay_evidence_id != second.replay_evidence_id
    assert first.report_id != second.report_id


def test_qualified_report_supplies_fail_closed_maturity_transition_evidence() -> None:
    manifest = _manifest()
    report = qualify_verifier(manifest, _replays(manifest))
    verifier_evidence = verifier_maturity_evidence(
        report,
        qualification_policy_version=DEFAULT_MATURITY_POLICY.policy_version,
        observed_at=NOW,
        provenance={"runner": "verifier-qualification-suite"},
    )
    executable_evidence = [
        _maturity_evidence(gate)
        for gate in DEFAULT_MATURITY_POLICY.requirements[EnvironmentMaturity.EXECUTABLE]
    ]

    maturity = assess_environment_maturity(
        environment_identity=ENVIRONMENT,
        verifier_identity=VERIFIER,
        evidence=executable_evidence + list(verifier_evidence),
        provenance={"runner": "unit-test"},
        target_status=EnvironmentMaturity.VERIFIER_VALIDATED,
        evaluated_at=NOW,
    )

    assert maturity.status == EnvironmentMaturity.VERIFIER_VALIDATED


def test_unqualified_report_cannot_promote_verifier_maturity() -> None:
    manifest = _manifest(excluded={VerifierFixtureCategory.REWARD_HACK})
    report = qualify_verifier(manifest, _replays(manifest))

    evidence = verifier_maturity_evidence(
        report,
        qualification_policy_version=DEFAULT_MATURITY_POLICY.policy_version,
        observed_at=NOW,
        provenance={"runner": "verifier-qualification-suite"},
    )

    assert evidence[0].outcome == GateOutcome.UNKNOWN
    assert evidence[2].outcome == GateOutcome.UNKNOWN
