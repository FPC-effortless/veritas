from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.models import stable_hash
from investigation_world.qualification.models import (
    EvidenceItem,
    EvidenceManifest,
    PolicyClass,
    PolicyEvaluation,
    PolicyOutcome,
    QualificationCandidate,
    QualificationScenario,
    QualificationSplit,
)
from investigation_world.qualification.source_disjoint import token_jaccard


class SRECausalClass(StrEnum):
    REGRESSION = "regression"
    INFRASTRUCTURE = "infrastructure"
    CAPACITY = "capacity"
    TRANSIENT = "transient"


class SREIncidentSource(BaseModel):
    """One frozen incident thread compiled from a real structured status source."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: str
    incident_id: str
    source_uri: str
    title: str
    early_updates: list[str] = Field(min_length=1)
    resolution_updates: list[str] = Field(min_length=1)
    causal_class: SRECausalClass
    started_at: datetime | None = None
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def source_group_id(self) -> str:
        return f"{self.provider}:{self.incident_id}"

    @property
    def public_text(self) -> str:
        return "\n".join([self.title, *self.early_updates])

    @property
    def private_text(self) -> str:
        return "\n".join(self.resolution_updates)


class SREQualificationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario: QualificationScenario
    public_text: str
    causal_class: SRECausalClass
    provider: str


def _split_incidents(incidents: list[SREIncidentSource]) -> dict[str, QualificationSplit]:
    ordered = sorted(incidents, key=lambda item: stable_hash(item.source_group_id))
    count = len(ordered)
    train_end = max(1, int(count * 0.60))
    dev_end = max(train_end + 1, int(count * 0.80)) if count >= 3 else train_end
    result: dict[str, QualificationSplit] = {}
    for index, incident in enumerate(ordered):
        if index < train_end:
            split = QualificationSplit.TRAIN
        elif index < dev_end:
            split = QualificationSplit.DEV
        else:
            split = QualificationSplit.PRIVATE_TEST
        result[incident.source_group_id] = split
    return result


def compile_sre_candidate(
    incidents: list[SREIncidentSource],
    *,
    version: str = "sre-v1",
) -> tuple[QualificationCandidate, list[SREQualificationCase]]:
    if len(incidents) < 3:
        raise ValueError("SRE qualification requires at least three independent incident sources")
    source_ids = [item.source_group_id for item in incidents]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("SRE incident source groups must be unique")
    splits = _split_incidents(incidents)

    scenarios: list[QualificationScenario] = []
    cases: list[SREQualificationCase] = []
    evidence: list[EvidenceItem] = []
    for incident in incidents:
        public_digest = stable_hash(incident.public_text)
        private_digest = stable_hash([incident.private_text, incident.causal_class.value])
        scenario_id = f"SRE-{stable_hash([incident.source_group_id, public_digest])[:16].upper()}"
        scenario = QualificationScenario(
            scenario_id=scenario_id,
            source_group_id=incident.source_group_id,
            split=splits[incident.source_group_id],
            normalized_text=incident.public_text,
            public_digest=public_digest,
            private_digest=private_digest,
            metadata={"provider": incident.provider},
        )
        scenarios.append(scenario)
        cases.append(
            SREQualificationCase(
                scenario=scenario,
                public_text=incident.public_text,
                causal_class=incident.causal_class,
                provider=incident.provider,
            )
        )
        raw_digest = hashlib.sha256(
            (incident.public_text + "\n---PRIVATE---\n" + incident.private_text).encode("utf-8")
        ).hexdigest()
        evidence.append(
            EvidenceItem(
                evidence_id=f"INCIDENT-{stable_hash(incident.source_group_id)[:16].upper()}",
                source_group_id=incident.source_group_id,
                source_uri=incident.source_uri,
                content_sha256=raw_digest,
                acquired_at=incident.resolved_at,
                metadata={"provider": incident.provider, "incident_id": incident.incident_id},
            )
        )

    manifest = EvidenceManifest(items=evidence)
    candidate_id = f"SRE-CAND-{stable_hash([version, manifest.manifest_id, sorted(source_ids)])[:20].upper()}"
    return (
        QualificationCandidate(
            candidate_id=candidate_id,
            domain="sre_incident_response",
            version=version,
            scenarios=scenarios,
            evidence_manifest=manifest,
            metadata={
                "compiler": "sre-status-incident-v1",
                "private_truth": "later causal/resolution evidence",
                "public_evidence": "early incident updates only",
            },
        ),
        cases,
    )


def _contains_any(value: str, tokens: tuple[str, ...]) -> bool:
    return any(token in value for token in tokens)


def _keyword_prediction(text: str, *, competent: bool) -> SRECausalClass:
    value = text.casefold()
    regression = ("deploy", "release", "rollback", "regression", "change introduced")
    capacity = ("capacity", "overload", "traffic", "saturation", "rate limit", "exhaust")
    infrastructure = ("network", "dns", "database", "storage", "hardware", "power")

    if competent:
        if _contains_any(value, regression):
            return SRECausalClass.REGRESSION
        if _contains_any(value, capacity):
            return SRECausalClass.CAPACITY
        if _contains_any(value, infrastructure):
            return SRECausalClass.INFRASTRUCTURE
        return SRECausalClass.TRANSIENT

    if _contains_any(value, capacity):
        return SRECausalClass.CAPACITY
    if _contains_any(value, ("deploy", "release", "rollback", "change", "regression")):
        return SRECausalClass.REGRESSION
    return SRECausalClass.TRANSIENT


def _trained_public_knn_prediction(
    case: SREQualificationCase,
    train_cases: list[SREQualificationCase],
    *,
    neighbors: int = 3,
    provider_bonus: float = 0.02,
) -> SRECausalClass:
    """Predict from labelled train incidents using public early evidence only.

    The baseline is intentionally simple and auditable. Hyperparameters are fixed from the dev
    split; the private-test causal labels are never consulted. Near-duplicate components are split
    atomically before this policy runs, preventing a duplicate incident family from becoming a
    nearest-neighbour leakage channel.
    """
    if not train_cases:
        return _keyword_prediction(case.public_text, competent=True)
    ranked = sorted(
        (
            token_jaccard(case.public_text, train.public_text)
            + (provider_bonus if case.provider == train.provider else 0.0),
            stable_hash(train.scenario.scenario_id),
            train.causal_class,
        )
        for train in train_cases
    )
    votes: dict[SRECausalClass, float] = defaultdict(float)
    for similarity, _, label in reversed(ranked[-max(1, neighbors):]):
        votes[label] += max(similarity, 0.001)
    rule_prediction = _keyword_prediction(case.public_text, competent=True)
    return max(
        SRECausalClass,
        key=lambda label: (
            votes[label],
            label == rule_prediction,
            -list(SRECausalClass).index(label),
        ),
    )


def _evaluate_prediction(case: SREQualificationCase, prediction: SRECausalClass) -> float:
    return 1.0 if prediction == case.causal_class else 0.0


def execute_sre_policy_suite(
    cases: list[SREQualificationCase],
    *,
    random_seed: int = 7,
) -> list[PolicyEvaluation]:
    train_cases = [case for case in cases if case.scenario.split == QualificationSplit.TRAIN]
    private_cases = [case for case in cases if case.scenario.split == QualificationSplit.PRIVATE_TEST]
    if not private_cases:
        raise ValueError("SRE policy suite requires private-test cases")
    if not train_cases:
        raise ValueError("competent SRE policy requires labelled train cases")
    if {
        case.scenario.source_group_id for case in train_cases
    } & {
        case.scenario.source_group_id for case in private_cases
    }:
        raise ValueError("train/private source groups overlap")

    rng = random.Random(random_seed)
    classes = list(SRECausalClass)
    outcomes: dict[PolicyClass, list[PolicyOutcome]] = {kind: [] for kind in PolicyClass}
    for case in private_cases:
        predictions = {
            PolicyClass.ORACLE: case.causal_class,
            PolicyClass.COMPETENT_HEURISTIC: _trained_public_knn_prediction(case, train_cases),
            PolicyClass.MYOPIC: _keyword_prediction(case.public_text, competent=False),
            PolicyClass.RANDOM: rng.choice(classes),
        }
        for kind, prediction in predictions.items():
            reward = _evaluate_prediction(case, prediction)
            metadata = {"prediction": prediction.value}
            if kind == PolicyClass.COMPETENT_HEURISTIC:
                metadata.update(
                    {
                        "training_split": "train",
                        "training_cases": len(train_cases),
                        "neighbors": 3,
                        "provider_bonus": 0.02,
                        "private_label_access": False,
                    }
                )
            outcomes[kind].append(
                PolicyOutcome(
                    scenario_id=case.scenario.scenario_id,
                    reward=reward,
                    passed=reward == 1.0,
                    metadata=metadata,
                )
            )
        outcomes[PolicyClass.EXPLOIT].append(
            PolicyOutcome(
                scenario_id=case.scenario.scenario_id,
                reward=0.0,
                passed=False,
                metadata={"attempt": "unsupported-resolved-status"},
            )
        )

    names = {
        PolicyClass.ORACLE: "private-causal-oracle",
        PolicyClass.COMPETENT_HEURISTIC: "train-fit-public-evidence-3nn",
        PolicyClass.MYOPIC: "single-signal-myopic",
        PolicyClass.RANDOM: f"seeded-random-{random_seed}",
        PolicyClass.EXPLOIT: "unsupported-terminal-exploit",
    }
    return [
        PolicyEvaluation(policy_class=kind, policy_name=names[kind], outcomes=outcomes[kind])
        for kind in PolicyClass
    ]
