from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from enum import StrEnum
from math import isclose
from re import fullmatch
from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash
from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    GateOutcome,
    MaturityGateEvidence,
    VerifierIdentity,
)


class VerifierFixtureCategory(StrEnum):
    CORRECT_SOLUTION = "correct_solution"
    ALTERNATIVE_CORRECT_STRATEGY = "alternative_correct_strategy"
    PARTIALLY_CORRECT = "partially_correct"
    INCORRECT_PLAUSIBLE = "incorrect_plausible"
    REWARD_HACK = "reward_hack"
    INVALID_STATE_MUTATION = "invalid_state_mutation"
    MISSING_EVIDENCE = "missing_evidence"
    AUTHORITY_PROCESS_VIOLATION = "authority_process_violation"
    FORBIDDEN_SIDE_EFFECT = "forbidden_side_effect"
    NONDETERMINISTIC_PERTURBATION = "nondeterministic_perturbation"
    MALFORMED_ARTIFACT = "malformed_artifact"
    ADVERSARIAL_EDGE_CASE = "adversarial_edge_case"


REQUIRED_VERIFIER_FIXTURE_CATEGORIES = tuple(VerifierFixtureCategory)


def _sha256(value: str, *, name: str) -> None:
    if fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


class VerifierFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    fixture_id: str = ""
    category: VerifierFixtureCategory
    payload_sha256: str
    expected_pass: bool
    minimum_reward: float = Field(ge=0.0, le=1.0)
    maximum_reward: float = Field(ge=0.0, le=1.0)
    strategy_family: str | None = None
    description: str = Field(min_length=1)
    provenance: dict[str, Any] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_fixture(self) -> "VerifierFixture":
        _sha256(self.payload_sha256, name="fixture payload_sha256")
        if self.minimum_reward > self.maximum_reward:
            raise ValueError("fixture minimum_reward cannot exceed maximum_reward")
        if self.category in {
            VerifierFixtureCategory.CORRECT_SOLUTION,
            VerifierFixtureCategory.ALTERNATIVE_CORRECT_STRATEGY,
        } and not self.expected_pass:
            raise ValueError("correct-solution fixtures must be expected to pass")
        payload = self.model_dump(mode="json", exclude={"fixture_id", "provenance"})
        expected = f"VFIX-{stable_hash(payload)[:24].upper()}"
        if self.fixture_id and self.fixture_id != expected:
            raise ValueError("verifier fixture ID does not match immutable contents")
        object.__setattr__(self, "fixture_id", expected)
        return self


class VerifierFixtureManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    manifest_id: str = ""
    suite_version: str = Field(min_length=1)
    environment_identity: EnvironmentIdentity
    verifier_identity: VerifierIdentity
    fixtures: tuple[VerifierFixture, ...]

    @model_validator(mode="after")
    def validate_manifest(self) -> "VerifierFixtureManifest":
        if not self.fixtures:
            raise ValueError("verifier fixture manifest cannot be empty")
        fixture_ids = [item.fixture_id for item in self.fixtures]
        if len(fixture_ids) != len(set(fixture_ids)):
            raise ValueError("verifier fixture IDs must be unique")
        payload = {
            "suite_version": self.suite_version,
            "environment_identity": self.environment_identity.model_dump(mode="json"),
            "verifier_identity": self.verifier_identity.model_dump(mode="json"),
            "fixtures": [
                item.model_dump(mode="json", exclude={"provenance"})
                for item in sorted(self.fixtures, key=lambda fixture: fixture.fixture_id)
            ],
        }
        expected = f"VFIXMAN-{stable_hash(payload)[:24].upper()}"
        if self.manifest_id and self.manifest_id != expected:
            raise ValueError("verifier fixture manifest ID does not match immutable contents")
        object.__setattr__(self, "manifest_id", expected)
        return self


class VerifierReplay(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    fixture_id: str = Field(min_length=1)
    repetition: int = Field(ge=0)
    reward: float = Field(ge=0.0, le=1.0)
    passed: bool
    component_scores: dict[str, float] = Field(default_factory=dict)
    output_sha256: str
    observed_at: datetime
    provenance: dict[str, Any] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_replay(self) -> "VerifierReplay":
        _sha256(self.output_sha256, name="verifier replay output_sha256")
        if any(value < 0.0 or value > 1.0 for value in self.component_scores.values()):
            raise ValueError("verifier component scores must be within [0, 1]")
        return self


class VerifierQualificationThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    maximum_false_positive_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    maximum_false_negative_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    minimum_alternative_solution_acceptance: float = Field(default=1.0, ge=0.0, le=1.0)
    minimum_reward_hack_resistance: float = Field(default=1.0, ge=0.0, le=1.0)
    minimum_deterministic_reproduction: float = Field(default=1.0, ge=0.0, le=1.0)
    minimum_evidence_dependence: float = Field(default=1.0, ge=0.0, le=1.0)
    minimum_state_grounding_correctness: float = Field(default=1.0, ge=0.0, le=1.0)
    minimum_process_rule_correctness: float = Field(default=1.0, ge=0.0, le=1.0)
    minimum_side_effect_sensitivity: float = Field(default=1.0, ge=0.0, le=1.0)
    minimum_ambiguity_sensitivity: float = Field(default=1.0, ge=0.0, le=1.0)
    reward_tolerance: float = Field(default=0.0, ge=0.0, le=1.0)


class VerifierQualificationGate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    outcome: GateOutcome
    observed: Any = None
    required: Any = None
    detail: str = ""


class VerifierQualificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    report_id: str = ""
    suite_version: str
    fixture_manifest_id: str
    replay_evidence_id: str
    environment_identity: EnvironmentIdentity
    verifier_identity: VerifierIdentity
    metrics: dict[str, float | None]
    gates: tuple[VerifierQualificationGate, ...]
    status: GateOutcome

    @property
    def qualified(self) -> bool:
        return self.status == GateOutcome.PASS

    @model_validator(mode="after")
    def validate_report(self) -> "VerifierQualificationReport":
        expected_status = (
            GateOutcome.FAIL
            if any(gate.outcome == GateOutcome.FAIL for gate in self.gates)
            else GateOutcome.UNKNOWN
            if any(gate.outcome == GateOutcome.UNKNOWN for gate in self.gates)
            else GateOutcome.PASS
        )
        if self.status != expected_status:
            raise ValueError("verifier qualification status does not match gate outcomes")
        payload = self.model_dump(mode="json", exclude={"report_id"})
        expected = f"VQREPORT-{stable_hash(payload)[:24].upper()}"
        if self.report_id and self.report_id != expected:
            raise ValueError("verifier qualification report ID does not match immutable contents")
        object.__setattr__(self, "report_id", expected)
        return self


def _gate(
    name: str,
    outcome: GateOutcome,
    observed: Any,
    required: Any,
    detail: str = "",
) -> VerifierQualificationGate:
    return VerifierQualificationGate(
        name=name,
        outcome=outcome,
        observed=observed,
        required=required,
        detail=detail,
    )


def _threshold_gate(
    name: str,
    observed: float | None,
    required: float,
    *,
    minimum: bool,
) -> VerifierQualificationGate:
    if observed is None:
        return _gate(
            name,
            GateOutcome.UNKNOWN,
            None,
            required,
            "required fixture evidence is missing",
        )
    passed = observed >= required if minimum else observed <= required
    return _gate(name, GateOutcome.PASS if passed else GateOutcome.FAIL, observed, required)


def _matches_expected(fixture: VerifierFixture, replay: VerifierReplay) -> bool:
    return (
        replay.passed == fixture.expected_pass
        and fixture.minimum_reward <= replay.reward <= fixture.maximum_reward
    )


def _category_rate(
    categories: set[VerifierFixtureCategory],
    fixtures: tuple[VerifierFixture, ...],
    replay_map: dict[str, list[VerifierReplay]],
) -> float | None:
    relevant = [fixture for fixture in fixtures if fixture.category in categories]
    observations = [
        _matches_expected(fixture, replay)
        for fixture in relevant
        for replay in replay_map.get(fixture.fixture_id, [])
    ]
    if not observations:
        return None
    return mean(observations)


def qualify_verifier(
    manifest: VerifierFixtureManifest,
    replays: tuple[VerifierReplay, ...] | list[VerifierReplay],
    *,
    thresholds: VerifierQualificationThresholds | None = None,
) -> VerifierQualificationReport:
    cfg = thresholds or VerifierQualificationThresholds()
    fixtures_by_id = {fixture.fixture_id: fixture for fixture in manifest.fixtures}
    replay_map: dict[str, list[VerifierReplay]] = defaultdict(list)
    replay_keys: set[tuple[str, int]] = set()
    for replay in replays:
        if replay.fixture_id not in fixtures_by_id:
            raise ValueError(f"replay references unknown fixture: {replay.fixture_id}")
        key = (replay.fixture_id, replay.repetition)
        if key in replay_keys:
            raise ValueError(f"duplicate verifier replay: {replay.fixture_id}/{replay.repetition}")
        replay_keys.add(key)
        replay_map[replay.fixture_id].append(replay)
    for values in replay_map.values():
        values.sort(key=lambda replay: replay.repetition)
    replay_evidence_payload = [
        replay.model_dump(mode="json", exclude={"observed_at", "provenance"})
        for replay in sorted(replays, key=lambda item: (item.fixture_id, item.repetition))
    ]
    replay_evidence_id = f"VREPLAY-{stable_hash(replay_evidence_payload)[:24].upper()}"

    observed_categories = {fixture.category for fixture in manifest.fixtures}
    missing_categories = set(REQUIRED_VERIFIER_FIXTURE_CATEGORIES) - observed_categories
    category_outcome = GateOutcome.UNKNOWN if missing_categories else GateOutcome.PASS
    missing_replays = [
        fixture.fixture_id for fixture in manifest.fixtures if not replay_map[fixture.fixture_id]
    ]
    replay_outcome = GateOutcome.UNKNOWN if missing_replays else GateOutcome.PASS

    positive = [fixture for fixture in manifest.fixtures if fixture.expected_pass]
    negative = [fixture for fixture in manifest.fixtures if not fixture.expected_pass]
    positive_results = [
        replay for fixture in positive for replay in replay_map.get(fixture.fixture_id, [])
    ]
    negative_results = [
        replay for fixture in negative for replay in replay_map.get(fixture.fixture_id, [])
    ]
    false_positive_rate = (
        mean(replay.passed for replay in negative_results) if negative_results else None
    )
    false_negative_rate = (
        mean(not replay.passed for replay in positive_results) if positive_results else None
    )

    alternative_acceptance = _category_rate(
        {VerifierFixtureCategory.ALTERNATIVE_CORRECT_STRATEGY},
        manifest.fixtures,
        replay_map,
    )
    reward_hack_resistance = _category_rate(
        {VerifierFixtureCategory.REWARD_HACK}, manifest.fixtures, replay_map
    )
    evidence_dependence = _category_rate(
        {VerifierFixtureCategory.MISSING_EVIDENCE}, manifest.fixtures, replay_map
    )
    state_grounding = _category_rate(
        {VerifierFixtureCategory.INVALID_STATE_MUTATION}, manifest.fixtures, replay_map
    )
    process_rules = _category_rate(
        {VerifierFixtureCategory.AUTHORITY_PROCESS_VIOLATION},
        manifest.fixtures,
        replay_map,
    )
    side_effects = _category_rate(
        {VerifierFixtureCategory.FORBIDDEN_SIDE_EFFECT}, manifest.fixtures, replay_map
    )
    ambiguity = _category_rate(
        {
            VerifierFixtureCategory.ALTERNATIVE_CORRECT_STRATEGY,
            VerifierFixtureCategory.ADVERSARIAL_EDGE_CASE,
        },
        manifest.fixtures,
        replay_map,
    )

    deterministic_fixtures: list[bool] = []
    deterministic_missing = False
    for fixture in manifest.fixtures:
        values = replay_map[fixture.fixture_id]
        if len(values) < 2:
            deterministic_missing = True
            continue
        first = values[0]
        deterministic_fixtures.append(
            all(
                replay.passed == first.passed
                and isclose(replay.reward, first.reward, abs_tol=cfg.reward_tolerance)
                and replay.component_scores == first.component_scores
                for replay in values[1:]
            )
        )
    deterministic_reproduction = (
        None
        if deterministic_missing or not deterministic_fixtures
        else mean(deterministic_fixtures)
    )

    all_observations = [
        _matches_expected(fixture, replay)
        for fixture in manifest.fixtures
        for replay in replay_map.get(fixture.fixture_id, [])
    ]
    expected_behavior = mean(all_observations) if all_observations else None
    exploit_failures = [
        replay.fixture_id
        for fixture in manifest.fixtures
        if fixture.category == VerifierFixtureCategory.REWARD_HACK
        for replay in replay_map.get(fixture.fixture_id, [])
        if not _matches_expected(fixture, replay)
    ]
    exploit_outcome = (
        GateOutcome.UNKNOWN
        if reward_hack_resistance is None
        else GateOutcome.FAIL
        if exploit_failures
        else GateOutcome.PASS
    )

    metrics = {
        "false_positive_rate": false_positive_rate,
        "false_negative_rate": false_negative_rate,
        "alternative_solution_acceptance": alternative_acceptance,
        "reward_hack_resistance": reward_hack_resistance,
        "deterministic_reproduction": deterministic_reproduction,
        "evidence_dependence": evidence_dependence,
        "state_grounding_correctness": state_grounding,
        "process_rule_correctness": process_rules,
        "side_effect_sensitivity": side_effects,
        "ambiguity_sensitivity": ambiguity,
        "expected_behavior_rate": expected_behavior,
    }
    gates = (
        _gate(
            "falsifier_fixture_coverage",
            category_outcome,
            sorted(category.value for category in observed_categories),
            sorted(category.value for category in REQUIRED_VERIFIER_FIXTURE_CATEGORIES),
            "every qualified verifier must retain the complete falsifier taxonomy",
        ),
        _gate(
            "fixture_replay_coverage",
            replay_outcome,
            sorted(missing_replays),
            [],
            "every fixture requires at least one replay",
        ),
        _threshold_gate(
            "false_positive_rate",
            false_positive_rate,
            cfg.maximum_false_positive_rate,
            minimum=False,
        ),
        _threshold_gate(
            "false_negative_rate",
            false_negative_rate,
            cfg.maximum_false_negative_rate,
            minimum=False,
        ),
        _threshold_gate(
            "alternative_solution_acceptance",
            alternative_acceptance,
            cfg.minimum_alternative_solution_acceptance,
            minimum=True,
        ),
        _threshold_gate(
            "reward_hack_resistance",
            reward_hack_resistance,
            cfg.minimum_reward_hack_resistance,
            minimum=True,
        ),
        _gate(
            "known_unbounded_reward_exploits",
            exploit_outcome,
            sorted(exploit_failures),
            [],
            "known reward-hack fixtures must not pass or exceed their reward bounds",
        ),
        _threshold_gate(
            "deterministic_reproduction",
            deterministic_reproduction,
            cfg.minimum_deterministic_reproduction,
            minimum=True,
        ),
        _threshold_gate(
            "evidence_dependence",
            evidence_dependence,
            cfg.minimum_evidence_dependence,
            minimum=True,
        ),
        _threshold_gate(
            "state_grounding_correctness",
            state_grounding,
            cfg.minimum_state_grounding_correctness,
            minimum=True,
        ),
        _threshold_gate(
            "process_rule_correctness",
            process_rules,
            cfg.minimum_process_rule_correctness,
            minimum=True,
        ),
        _threshold_gate(
            "side_effect_sensitivity",
            side_effects,
            cfg.minimum_side_effect_sensitivity,
            minimum=True,
        ),
        _threshold_gate(
            "ambiguity_sensitivity",
            ambiguity,
            cfg.minimum_ambiguity_sensitivity,
            minimum=True,
        ),
        _threshold_gate(
            "expected_reward_and_pass_behavior",
            expected_behavior,
            1.0,
            minimum=True,
        ),
    )
    status = (
        GateOutcome.FAIL
        if any(gate.outcome == GateOutcome.FAIL for gate in gates)
        else GateOutcome.UNKNOWN
        if any(gate.outcome == GateOutcome.UNKNOWN for gate in gates)
        else GateOutcome.PASS
    )
    return VerifierQualificationReport(
        suite_version=manifest.suite_version,
        fixture_manifest_id=manifest.manifest_id,
        replay_evidence_id=replay_evidence_id,
        environment_identity=manifest.environment_identity,
        verifier_identity=manifest.verifier_identity,
        metrics=metrics,
        gates=gates,
        status=status,
    )


def verifier_maturity_evidence(
    report: VerifierQualificationReport,
    *,
    qualification_policy_version: str,
    observed_at: datetime,
    provenance: dict[str, Any],
) -> tuple[MaturityGateEvidence, ...]:
    if not provenance:
        raise ValueError("verifier maturity evidence requires provenance")
    gates_by_name = {gate.name: gate for gate in report.gates}
    report_digest = stable_hash(report.model_dump(mode="json"))

    def evidence(gate: str, outcome: GateOutcome) -> MaturityGateEvidence:
        return MaturityGateEvidence(
            gate=gate,
            outcome=outcome,
            evidence_id=report.report_id,
            content_sha256=report_digest,
            environment_content_sha256=report.environment_identity.content_sha256,
            verifier_content_sha256=report.verifier_identity.content_sha256,
            qualification_policy_version=qualification_policy_version,
            observed_at=observed_at,
            provenance=provenance,
            detail="derived from the content-addressed verifier qualification report",
        )

    return (
        evidence("verifier_qualification", report.status),
        evidence(
            "falsifier_fixtures",
            gates_by_name["falsifier_fixture_coverage"].outcome,
        ),
        evidence(
            "reward_hack_resistance",
            gates_by_name["reward_hack_resistance"].outcome,
        ),
    )
