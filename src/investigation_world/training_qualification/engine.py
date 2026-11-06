"""Offline policy evaluation of supplied records, never an execution attestor or trainer."""

from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Literal, Self

from pydantic import AwareDatetime, ConfigDict, Field, StrictInt, model_validator

from investigation_world.capability_science import (
    AcquisitionCurve,
    EvaluationPoint,
    TransferEvidence,
)
from investigation_world.capability_science.core import (
    CapabilitySpec,
    Digest,
    ScienceRecord,
    validate_references,
)
from investigation_world.experience import ExperienceReference
from investigation_world.experience_foundry.paired_evaluation import _training_membership
from investigation_world.foundry.models import capability_contract_digest_payload
from investigation_world.foundry.training_product import TrainingBundle, TrainingRunManifest
from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    GateOutcome,
    MaturityGateEvidence,
    VerifierIdentity,
)
from investigation_world.trajectory import VisibilityClass, canonical_hash
from investigation_world.verifier_monitoring import monitor_exploits
from investigation_world.verifier_monitoring.models import (
    ExploitCorpus,
    ExploitMonitorPolicy,
    ExploitRegressionObservation,
    RegressionOutcome,
)

_PRIVATE: Literal[VisibilityClass.EVALUATOR_PRIVATE] = VisibilityClass.EVALUATOR_PRIVATE
Role = Literal["train", "heldout", "transfer", "guardrail"]


class PrivateRecord(ScienceRecord):
    model_config = ConfigDict(hide_input_in_errors=True)
    visibility: Literal[VisibilityClass.EVALUATOR_PRIVATE] = _PRIVATE


class TrainingPolicy(PrivateRecord):
    schema_version: Literal["veritas.training-policy.v1"] = "veritas.training-policy.v1"
    version: Literal["1"] = "1"
    minimum_replicates: int = Field(default=3, strict=True, ge=2, le=32)
    minimum_population: int = Field(default=20, strict=True, ge=1, le=512)
    minimum_heldout_gain: float = Field(default=0.05, gt=0, le=1)
    minimum_learnability_score: float = Field(default=0.8, gt=0, le=1)
    maximum_generalization_gap: float = Field(default=0.2, ge=0, le=1)
    maximum_seed_gain_range: float = Field(default=0.15, ge=0, le=2)
    maximum_guardrail_regression: float = Field(default=0, ge=0, le=1)
    minimum_ood_gain: float = Field(default=0, ge=0, le=1)
    exploit_policy: ExploitMonitorPolicy = Field(default_factory=ExploitMonitorPolicy)


class ExploitPanel(PrivateRecord):
    """Checkpoint-bound observations; monitor_exploits is rerun, reports are not trusted."""

    corpus: ExploitCorpus
    before: tuple[ExploitRegressionObservation, ...] = Field(default=(), max_length=512)
    after: tuple[ExploitRegressionObservation, ...] = Field(default=(), max_length=512)
    before_checkpoint: Digest
    after_checkpoint: Digest
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def distinct_phases(self) -> Self:
        if {row.observation_id for row in self.before} & {row.observation_id for row in self.after}:
            raise ValueError("exploit phases require distinct observations")
        if {row.evidence.content_sha256 for row in self.before if row.evidence} & {
            row.evidence.content_sha256 for row in self.after if row.evidence
        }:
            raise ValueError("exploit phases require distinct replay evidence")
        if any(row.observed_at.tzinfo is None for row in (*self.before, *self.after)):
            raise ValueError("exploit observation timestamps must include timezone")
        return self


class TrainingReplicate(PrivateRecord):
    seed: int = Field(strict=True, ge=0, le=2**32 - 1)
    manifest: TrainingRunManifest
    train: AcquisitionCurve | None = None
    heldout: AcquisitionCurve | None = None
    learnability: EvaluationPoint | None = None
    transfer: tuple[AcquisitionCurve, ...] = Field(default=(), max_length=8)
    guardrails: tuple[AcquisitionCurve, ...] = Field(default=(), max_length=8)
    exploits: ExploitPanel | None = None

    @model_validator(mode="after")
    def check_seed(self) -> Self:
        if self.seed != self.manifest.seed or not self.manifest.run_id.strip():
            raise ValueError("replicate requires its exact manifest seed and run identity")
        return self


class TrainingEvidence(PrivateRecord):
    schema_version: Literal["veritas.training-evidence.v1"] = "veritas.training-evidence.v1"
    capability: CapabilitySpec
    environment_identity: EnvironmentIdentity
    verifier_identity: VerifierIdentity
    bundle: TrainingBundle | None = None
    configuration_digest: Digest
    expected_seeds: tuple[StrictInt, ...] = Field(min_length=1, max_length=32)
    required_guardrail_capabilities: tuple[Digest, ...] = Field(default=(), max_length=8)
    replicates: tuple[TrainingReplicate, ...] = Field(default=(), max_length=32)
    provenance: Literal["UNKNOWN", "DECLARED", "CONSTRUCTED"] = "UNKNOWN"
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)
    # No existing receipt, hash, fixture, or caller assertion attests model execution.
    # A future provider needs separately reviewed validation, not a PASS input knob.
    execution_attestation_provider: Literal["UNAVAILABLE"] = "UNAVAILABLE"

    @model_validator(mode="after")
    def check_protocol(self) -> Self:
        validate_references(self.evidence_references)
        for version in (
            self.environment_identity.environment_version,
            self.verifier_identity.verifier_version,
        ):
            if version.strip().lower() in {"", "unknown", "latest", "main", "head", "unspecified"}:
                raise ValueError("pinned environment and verifier revisions required")
        if any(
            type(seed) is not int or not 0 <= seed < 2**32 for seed in self.expected_seeds
        ) or len(set(self.expected_seeds)) != len(self.expected_seeds):
            raise ValueError("expected seeds must be unique bounded integers")
        seeds = [rep.seed for rep in self.replicates]
        if len(seeds) != len(set(seeds)) or set(seeds) - set(self.expected_seeds):
            raise ValueError("duplicate or unexpected replicate seed")
        if len({r.manifest.run_id for r in self.replicates}) != len(self.replicates):
            raise ValueError("replicate run identities must be distinct")
        if len(set(self.required_guardrail_capabilities)) != len(
            self.required_guardrail_capabilities
        ):
            raise ValueError("guardrail capabilities must be unique")
        if self.capability.contract_digest in self.required_guardrail_capabilities:
            raise ValueError("unrelated guardrails must not be the target capability")
        training_ids: set[str] = set()
        training_digests: set[str] = set()
        training_mapping: dict[str, str] = {}
        if self.bundle is not None:
            if (
                canonical_hash(capability_contract_digest_payload(self.bundle.capability_contract))
                != self.capability.contract_digest
            ):
                raise ValueError("training bundle capability differs from target")
            _, training_ids, training_digests = _training_membership(self.bundle)
            training_mapping = {
                row["source_id"]: row["source_digest"]
                for row in self.bundle.metadata["verified_learning_lineage"]
            }
        populations: dict[str, str] = {}
        experiment: tuple[str, str, str, str] | None = None
        exploit_corpus_id: str | None = None
        for rep in self.replicates:
            if canonical_hash(rep.manifest.parameters) != self.configuration_digest:
                raise ValueError("manifest configuration content mismatch")
            if self.bundle is not None and rep.manifest.bundle_id != self.bundle.bundle_id:
                raise ValueError("manifest training bundle mismatch")
            curves = (
                [("train", rep.train), ("heldout", rep.heldout)]
                + [("transfer", curve) for curve in rep.transfer]
                + [("guardrail", curve) for curve in rep.guardrails]
            )
            checkpoint_pair: tuple[str, str, str] | None = None
            metric_semantics: tuple[str, str] | None = None
            training_times: tuple[datetime | None, datetime | None] | None = None
            guard_caps: list[str] = []
            panel_sources: dict[str, set[str]] = {}
            for role, curve in curves:
                if curve is None:
                    continue
                if len(curve.points) != 2 or len(curve.interventions) != 1:
                    raise ValueError("one before/after intervention per replicate panel required")
                before, after = curve.points
                panel, step = before.population, curve.interventions[0]
                if len(panel.members) > 512:
                    raise ValueError("qualification population exceeds bounded offline limit")
                if panel.split != ("TRAIN" if role == "train" else "HELD_OUT"):
                    raise ValueError("training/evaluation split mismatch")
                capability = panel.capability.contract_digest
                if role == "guardrail":
                    guard_caps.append(capability)
                    if capability not in self.required_guardrail_capabilities:
                        raise ValueError("unexpected unrelated capability panel")
                elif capability != self.capability.contract_digest:
                    raise ValueError("target capability mismatch")
                conditions = panel.conditions
                if (
                    conditions.environment_id,
                    conditions.environment_revision,
                    conditions.verifier_id,
                    conditions.verifier_revision,
                ) != (
                    self.environment_identity.environment_id,
                    self.environment_identity.environment_version,
                    self.verifier_identity.verifier_id,
                    self.verifier_identity.verifier_version,
                ):
                    raise ValueError("exact environment/verifier semantics mismatch")
                semantics = (conditions.metric, conditions.metric_definition_digest)
                if metric_semantics is not None and semantics != metric_semantics:
                    raise ValueError("panel metric semantics mismatch")
                metric_semantics = semantics
                times = (step.started_at, step.finished_at)
                if training_times is not None and any(
                    left is not None and right is not None and left != right
                    for left, right in zip(training_times, times, strict=True)
                ):
                    raise ValueError("panel intervention chronology mismatch")
                prior_start, prior_finish = training_times or (None, None)
                training_times = (prior_start or times[0], prior_finish or times[1])
                protocol = (
                    before.model_id,
                    before.model_revision,
                    step.trainer_id,
                    step.trainer_revision,
                )
                if experiment is not None and protocol != experiment:
                    raise ValueError("replicate experiment model/checkpoint/trainer drift")
                experiment = protocol
                pair = (before.model_id, before.model_revision, after.model_revision)
                if checkpoint_pair is not None and checkpoint_pair != pair:
                    raise ValueError("panel model/checkpoint mismatch")
                checkpoint_pair = pair
                if (
                    before.model_id != rep.manifest.base_model
                    or before.model_revision == after.model_revision
                ):
                    raise ValueError("distinct before/after checkpoints of manifest model required")
                if (
                    step.training_configuration_digest != self.configuration_digest
                    or step.trainer_revision != rep.manifest.trainer_version
                ):
                    raise ValueError("training method/configuration revision mismatch")
                if self.bundle is not None and (
                    step.training_bundle_digest != canonical_hash(self.bundle)
                    or rep.manifest.trainer != self.bundle.recipe.trainer
                ):
                    raise ValueError("full training bundle identity mismatch")
                if (
                    rep.train is not None
                    and step.training_population.record_id
                    != rep.train.points[0].population.record_id
                ):
                    raise ValueError("intervention training population mismatch")
                ids = {m.reference_id for m in panel.members}
                digests = {m.digest for m in panel.members}
                if self.bundle is not None:
                    if (
                        role == "train"
                        and {m.reference_id: m.digest for m in panel.members} != training_mapping
                    ):
                        raise ValueError(
                            "training population does not cover the exact bundle lineage"
                        )
                    if role != "train" and (ids & training_ids or digests & training_digests):
                        raise ValueError("training and evaluation overlap")
                sources = {str(m.digest) for m in panel.members} | ids
                if any(sources & previous for previous in panel_sources.values()):
                    raise ValueError("evaluation panels must not recycle other panel members")
                panel_sources[panel.record_id] = sources
                # Fixed panel across seeds; no favorable per-seed resampling.
                key = role + ":" + capability
                if role == "transfer":
                    key += ":" + conditions.structure_id + ":" + conditions.distribution_id
                if key in populations and populations[key] != panel.record_id:
                    raise ValueError("replicate population drift")
                populations[key] = panel.record_id
            groups: list[list[datetime]] = [[], [], [], []]
            for _, curve in curves:
                if curve is None:
                    continue
                step = curve.interventions[0]
                for group, timestamp in zip(
                    groups,
                    (
                        curve.points[0].observed_at,
                        step.started_at,
                        step.finished_at,
                        curve.points[1].observed_at,
                    ),
                    strict=True,
                ):
                    if timestamp is not None:
                        group.append(timestamp)
            if rep.exploits is not None:
                groups[0].extend(row.observed_at for row in rep.exploits.before)
                groups[3].extend(row.observed_at for row in rep.exploits.after)
            for left in range(4):
                for right in range(left + 1, 4):
                    if groups[left] and groups[right]:
                        latest, earliest = max(groups[left]), min(groups[right])
                        if latest > earliest or (latest == earliest and (left, right) != (1, 2)):
                            raise ValueError("combined run/exploit chronology is inconsistent")
            if len(guard_caps) != len(set(guard_caps)):
                raise ValueError("duplicate unrelated capability panel")
            if rep.learnability is not None and (
                rep.heldout is None
                or rep.learnability.population != rep.heldout.points[0].population
            ):
                raise ValueError("learnability control must cover the same heldout population")
            if rep.learnability is not None:
                control = rep.learnability
                primary = [
                    point for _, curve in curves if curve is not None for point in curve.points
                ]

                def references(point: EvaluationPoint) -> set[str | None]:
                    return {ref.digest for ref in point.evidence_references} | {
                        ref.digest for row in point.outcomes for ref in row.evidence_references
                    }

                if any(
                    (control.model_id, control.model_revision)
                    == (point.model_id, point.model_revision)
                    or references(control) & references(point)
                    for point in primary
                ):
                    raise ValueError(
                        "learnability requires distinct declared independent control evidence"
                    )
            if rep.exploits is not None:
                if (
                    exploit_corpus_id is not None
                    and rep.exploits.corpus.corpus_id != exploit_corpus_id
                ):
                    raise ValueError("replicate exploit corpus drift")
                exploit_corpus_id = rep.exploits.corpus.corpus_id
            if (
                rep.exploits is not None
                and checkpoint_pair is not None
                and (
                    rep.exploits.before_checkpoint != canonical_hash(checkpoint_pair[:2])
                    or rep.exploits.after_checkpoint
                    != canonical_hash((checkpoint_pair[0], checkpoint_pair[2]))
                )
            ):
                raise ValueError("exploit panel checkpoint binding mismatch")
        return self


class PanelSummary(PrivateRecord):
    seed: int
    role: Role
    population_id: str
    capability_digest: Digest
    expected_count: int
    before_known_count: int
    after_known_count: int
    before_unknown_count: int
    after_unknown_count: int
    before_zero_score_count: int
    after_zero_score_count: int
    before_mean: float | None
    after_mean: float | None
    delta: float | None
    transfer_classifications: tuple[str, ...] = ()


class TrainingGate(PrivateRecord):
    name: str
    outcome: GateOutcome
    reason: str


def _reduce(values: list[GateOutcome]) -> GateOutcome:
    return (
        GateOutcome.FAIL
        if GateOutcome.FAIL in values
        else GateOutcome.UNKNOWN
        if not values or GateOutcome.UNKNOWN in values
        else GateOutcome.PASS
    )


def _threshold(value: float | None, limit: float, *, minimum: bool = True) -> GateOutcome:
    if value is None:
        return GateOutcome.UNKNOWN
    passed = value >= limit if minimum else value <= limit
    return GateOutcome.PASS if passed else GateOutcome.FAIL


def _summary(rep: TrainingReplicate, role: Role, curve: AcquisitionCurve) -> PanelSummary:
    before, after = curve.points
    b, a = before.recorded_mean, after.recorded_mean
    classifications: tuple[str, ...] = ()
    if role == "transfer" and rep.train is not None:
        classifications = TransferEvidence(
            source=rep.train.points[0],
            target=curve,
            evidence_references=curve.interventions[0].evidence_references,
        ).classifications
        source = rep.train.points[0].population.conditions
        target = curve.points[0].population.conditions
        if source.structure_id == target.structure_id:
            classifications = tuple(
                "WITHIN_FAMILY_DISTRIBUTION_SHIFT" if item == "STRUCTURAL_OOD" else item
                for item in classifications
            )
    return PanelSummary(
        seed=rep.seed,
        role=role,
        population_id=before.population.record_id,
        capability_digest=before.population.capability.contract_digest,
        expected_count=len(before.outcomes),
        before_known_count=sum(row.value is not None for row in before.outcomes),
        after_known_count=sum(row.value is not None for row in after.outcomes),
        before_unknown_count=sum(row.value is None for row in before.outcomes),
        after_unknown_count=sum(row.value is None for row in after.outcomes),
        before_zero_score_count=sum(row.value == 0 for row in before.outcomes),
        after_zero_score_count=sum(row.value == 0 for row in after.outcomes),
        before_mean=b,
        after_mean=a,
        delta=a - b if a is not None and b is not None else None,
        transfer_classifications=classifications,
    )


def _evaluate(
    evidence: TrainingEvidence, policy: TrainingPolicy
) -> tuple[tuple[PanelSummary, ...], tuple[TrainingGate, ...]]:
    checks: dict[str, list[GateOutcome]] = {
        name: []
        for name in (
            "baseline_measured",
            "learnability",
            "train_before_after",
            "held_out_improvement",
            "replicate_stability",
            "overfit_and_memorization",
            "ood_transfer",
            "unrelated_capability_guardrails",
            "reward_exploitation_regression",
            "full_population_and_provenance",
            "execution_and_chronology",
            "memorization_and_near_duplicate_probes",
        )
    }
    panels: list[PanelSummary] = []
    transfer_populations = {
        curve.points[0].population.record_id
        for rep in evidence.replicates
        for curve in rep.transfer
    }
    gains: list[float] = []
    for rep in evidence.replicates:
        role_curves: list[tuple[Role, AcquisitionCurve | None]] = [
            ("train", rep.train),
            ("heldout", rep.heldout),
        ]
        role_curves.extend(("transfer", curve) for curve in rep.transfer)
        role_curves.extend(("guardrail", curve) for curve in rep.guardrails)
        summaries = [_summary(rep, role, curve) for role, curve in role_curves if curve is not None]
        panels.extend(summaries)
        by_role: dict[str, PanelSummary] = {
            row.role: row for row in summaries if row.role in {"train", "heldout"}
        }
        for role, gate in (("train", "train_before_after"), ("heldout", "held_out_improvement")):
            row = by_role.get(role)
            checks[gate].append(
                _threshold(
                    row.delta if row else None,
                    policy.minimum_heldout_gain if role == "heldout" else 0,
                )
            )
            checks["baseline_measured"].append(
                GateOutcome.PASS
                if row is not None and row.before_mean is not None
                else GateOutcome.UNKNOWN
            )
        learn = rep.learnability.recorded_mean if rep.learnability else None
        checks["learnability"].append(_threshold(learn, policy.minimum_learnability_score))
        train, heldout = by_role.get("train"), by_role.get("heldout")
        if heldout is not None and heldout.delta is not None:
            gains.append(heldout.delta)
        gap = (
            train.delta - heldout.delta
            if train and heldout and train.delta is not None and heldout.delta is not None
            else None
        )
        score_gap = (
            train.after_mean - heldout.after_mean
            if train and heldout and train.after_mean is not None and heldout.after_mean is not None
            else None
        )
        checks["overfit_and_memorization"].extend(
            (
                _threshold(gap, policy.maximum_generalization_gap, minimum=False),
                _threshold(score_gap, policy.maximum_generalization_gap, minimum=False),
            )
        )
        transfer = [row for row in summaries if row.role == "transfer"]
        if {curve.points[0].population.record_id for curve in rep.transfer} != transfer_populations:
            checks["ood_transfer"].append(GateOutcome.UNKNOWN)
        checks["ood_transfer"].append(
            _reduce(
                [
                    _threshold(row.delta, policy.minimum_ood_gain)
                    if "STRUCTURAL_OOD" in row.transfer_classifications
                    else GateOutcome.UNKNOWN
                    for row in transfer
                ]
            )
        )
        guardrails = [row for row in summaries if row.role == "guardrail"]
        complete_guards = bool(evidence.required_guardrail_capabilities) and {
            row.capability_digest for row in guardrails
        } == set(evidence.required_guardrail_capabilities)
        checks["unrelated_capability_guardrails"].append(
            _reduce(
                [_threshold(row.delta, -policy.maximum_guardrail_regression) for row in guardrails]
                + ([] if complete_guards else [GateOutcome.UNKNOWN])
            )
        )
        checks["full_population_and_provenance"].extend(
            GateOutcome.PASS
            if row.expected_count >= policy.minimum_population
            and row.before_unknown_count == row.after_unknown_count == 0
            else GateOutcome.UNKNOWN
            for row in summaries
        )
        if rep.train is None or rep.heldout is None:
            checks["full_population_and_provenance"].append(GateOutcome.UNKNOWN)
        if rep.exploits is None or not rep.exploits.corpus.findings:
            checks["reward_exploitation_regression"].append(GateOutcome.UNKNOWN)
        else:
            panel = rep.exploits
            reports = [
                monitor_exploits(
                    panel.corpus,
                    environment_identity=evidence.environment_identity,
                    verifier_identity=evidence.verifier_identity,
                    observations=observations,
                    generated_at=panel.observed_at,
                    provenance={"source": "training-policy-evaluation"},
                    policy=policy.exploit_policy,
                )
                for observations in (panel.before, panel.after)
            ]
            checks["reward_exploitation_regression"].extend(report.status for report in reports)
            if not reports[0].applicable_exploit_ids:
                checks["reward_exploitation_regression"].append(GateOutcome.UNKNOWN)
            before_success = sum(x.outcome == RegressionOutcome.SUCCEEDED for x in panel.before)
            after_success = sum(x.outcome == RegressionOutcome.SUCCEEDED for x in panel.after)
            if after_success > before_success:
                checks["reward_exploitation_regression"].append(GateOutcome.FAIL)
    complete = len(evidence.replicates) == len(evidence.expected_seeds)
    stable = complete and len(gains) == len(evidence.replicates) >= policy.minimum_replicates
    checks["replicate_stability"] = [
        _threshold(min(gains) if gains else None, policy.minimum_heldout_gain),
        _threshold(
            max(gains) - min(gains) if len(gains) >= 2 else None,
            policy.maximum_seed_gain_range,
            minimum=False,
        ),
    ]
    if not stable:
        checks["replicate_stability"].append(GateOutcome.UNKNOWN)
    if not complete or evidence.bundle is None:
        checks["full_population_and_provenance"].append(GateOutcome.UNKNOWN)
    # Source records intentionally have UNKNOWN execution and chronology attestations.
    checks["execution_and_chronology"] = [GateOutcome.UNKNOWN]
    checks["memorization_and_near_duplicate_probes"] = [GateOutcome.UNKNOWN]
    return tuple(panels), tuple(
        TrainingGate(
            name=name,
            outcome=_reduce(values),
            reason=(
                "independent_execution_and_prospective_chronology_provider_unavailable"
                if name == "execution_and_chronology"
                else "behavioral_memorization_and_near_duplicate_provider_unavailable"
                if name == "memorization_and_near_duplicate_probes"
                else "policy_applied_to_complete_declared_evidence"
            ),
        )
        for name, values in checks.items()
    )


class TrainingReport(PrivateRecord):
    schema_version: Literal["veritas.training-report.v1"] = "veritas.training-report.v1"
    evidence: TrainingEvidence
    policy: TrainingPolicy
    panels: tuple[PanelSummary, ...]
    gates: tuple[TrainingGate, ...]
    status: GateOutcome
    expected_replicates: int
    observed_replicates: int
    mean_recorded_heldout_delta: float | None
    capability_gain: None = None
    training_validated: Literal[False] = False

    @model_validator(mode="after")
    def recompute(self) -> Self:
        panels, gates = _evaluate(self.evidence, self.policy)
        deltas = [row.delta for row in panels if row.role == "heldout"]
        average = (
            mean(x for x in deltas if x is not None)
            if deltas
            and all(x is not None for x in deltas)
            and len(deltas) == len(self.evidence.expected_seeds)
            else None
        )
        if (
            self.panels != panels
            or self.gates != gates
            or self.status != _reduce([g.outcome for g in gates])
            or self.expected_replicates != len(self.evidence.expected_seeds)
            or self.observed_replicates != len(self.evidence.replicates)
            or self.mean_recorded_heldout_delta != average
        ):
            raise ValueError("report must match independently recomputed policy results")
        return self


def assess_training(
    evidence: TrainingEvidence, *, policy: TrainingPolicy | None = None
) -> TrainingReport:
    evidence = evidence.checked()
    policy = (policy or TrainingPolicy()).checked()
    panels, gates = _evaluate(evidence, policy)
    deltas = [row.delta for row in panels if row.role == "heldout"]
    return TrainingReport(
        evidence=evidence,
        policy=policy,
        panels=panels,
        gates=gates,
        status=_reduce([g.outcome for g in gates]),
        expected_replicates=len(evidence.expected_seeds),
        observed_replicates=len(evidence.replicates),
        mean_recorded_heldout_delta=(
            mean(x for x in deltas if x is not None)
            if deltas
            and all(x is not None for x in deltas)
            and len(deltas) == len(evidence.expected_seeds)
            else None
        ),
    )


def training_maturity_evidence(
    report: TrainingReport, *, qualification_policy_version: str, observed_at: datetime
) -> tuple[MaturityGateEvidence, ...]:
    """Evaluator-private adapter; does not promote or alter canonical maturity ordering."""
    report = report.checked()
    gates = {gate.name: gate.outcome for gate in report.gates}
    groups = {
        "held_out_training_improvement": (
            "baseline_measured",
            "learnability",
            "train_before_after",
            "held_out_improvement",
            "overfit_and_memorization",
            "ood_transfer",
            "unrelated_capability_guardrails",
            "memorization_and_near_duplicate_probes",
        ),
        "multi_seed_stability": ("replicate_stability",),
        "reward_exploitation_regression": ("reward_exploitation_regression",),
    }
    return tuple(
        MaturityGateEvidence(
            gate=name,
            outcome=_reduce(
                [gates[key] for key in keys]
                + [gates["full_population_and_provenance"], gates["execution_and_chronology"]]
            ),
            evidence_id=report.record_id,
            content_sha256=canonical_hash(report),
            environment_content_sha256=report.evidence.environment_identity.content_sha256,
            verifier_content_sha256=report.evidence.verifier_identity.content_sha256,
            qualification_policy_version=qualification_policy_version,
            observed_at=observed_at,
            provenance={"source": "training_qualification", "visibility": "evaluator_private"},
            detail="conditional record evaluation; no independent execution attestation",
        )
        for name, keys in groups.items()
    )
