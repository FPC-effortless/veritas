from __future__ import annotations

import hashlib
import random
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


def _keyword_prediction(text: str, *, competent: bool) -> SRECausalClass:
    value = text.casefold()
    regression = ("deploy", "release", "rollback", "change", "regression")
    infrastructure = ("network", "dns", "database", "storage", "hardware", "region")
    capacity = ("capacity", "overload", "traffic", "saturation", "rate limit")
    if competent:
        scores = {
            SRECausalClass.REGRESSION: sum(token in value for token in regression),
            SRECausalClass.INFRASTRUCTURE: sum(token in value for token in infrastructure),
            SRECausalClass.CAPACITY: sum(token in value for token in capacity),
            SRECausalClass.TRANSIENT: sum(token in value for token in ("transient", "recovered", "intermittent")),
        }
        best = max(scores.values())
        if best > 0:
            return sorted((kind for kind, score in scores.items() if score == best), key=lambda x: x.value)[0]
        return SRECausalClass.TRANSIENT
    if any(token in value for token in capacity):
        return SRECausalClass.CAPACITY
    if any(token in value for token in regression):
        return SRECausalClass.REGRESSION
    return SRECausalClass.TRANSIENT


def _evaluate_prediction(case: SREQualificationCase, prediction: SRECausalClass) -> float:
    return 1.0 if prediction == case.causal_class else 0.0


def execute_sre_policy_suite(
    cases: list[SREQualificationCase],
    *,
    random_seed: int = 7,
) -> list[PolicyEvaluation]:
    private_cases = [case for case in cases if case.scenario.split == QualificationSplit.PRIVATE_TEST]
    if not private_cases:
        raise ValueError("SRE policy suite requires private-test cases")
    rng = random.Random(random_seed)
    classes = list(SRECausalClass)

    outcomes: dict[PolicyClass, list[PolicyOutcome]] = {kind: [] for kind in PolicyClass}
    for case in private_cases:
        predictions = {
            PolicyClass.ORACLE: case.causal_class,
            PolicyClass.COMPETENT_HEURISTIC: _keyword_prediction(case.public_text, competent=True),
            PolicyClass.MYOPIC: _keyword_prediction(case.public_text, competent=False),
            PolicyClass.RANDOM: rng.choice(classes),
        }
        for kind, prediction in predictions.items():
            reward = _evaluate_prediction(case, prediction)
            outcomes[kind].append(
                PolicyOutcome(
                    scenario_id=case.scenario.scenario_id,
                    reward=reward,
                    passed=reward == 1.0,
                    metadata={"prediction": prediction.value},
                )
            )
        # The exploit policy submits a structurally plausible but unsupported terminal claim.
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
        PolicyClass.COMPETENT_HEURISTIC: "multi-signal-sre-heuristic",
        PolicyClass.MYOPIC: "single-signal-myopic",
        PolicyClass.RANDOM: f"seeded-random-{random_seed}",
        PolicyClass.EXPLOIT: "unsupported-terminal-exploit",
    }
    return [
        PolicyEvaluation(policy_class=kind, policy_name=names[kind], outcomes=outcomes[kind])
        for kind in PolicyClass
    ]
