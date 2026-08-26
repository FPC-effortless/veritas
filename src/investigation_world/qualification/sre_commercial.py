from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from investigation_world.foundry.models import stable_hash
from investigation_world.qualification.models import (
    PolicyClass,
    PolicyEvaluation,
    PolicyOutcome,
    QualificationCandidate,
    QualificationSplit,
)
from investigation_world.qualification.sre import (
    SRECausalClass,
    SREIncidentSource,
    SREQualificationCase,
    compile_sre_candidate,
)

# These sources are used as permissively licensed technical/reference inputs for the
# commercial SRE taxonomy. Veritas does not copy their benchmark prose into generated cases.
COMMERCIAL_SRE_SOURCE_REFERENCES: tuple[dict[str, str], ...] = (
    {
        "name": "quantranger/infra-ops-incidents",
        "license": "MIT",
        "role": "synthetic incident taxonomy/reference",
        "url": "https://huggingface.co/datasets/quantranger/infra-ops-incidents",
    },
    {
        "name": "ibm-research/ITBench-Lite",
        "license": "Apache-2.0",
        "role": "SRE task/environment design reference",
        "url": "https://huggingface.co/datasets/ibm-research/ITBench-Lite",
    },
)

_SERVICES = (
    "checkout-api",
    "identity-gateway",
    "event-ingest",
    "search-indexer",
    "billing-worker",
    "notification-router",
    "artifact-store",
    "session-service",
)
_REGIONS = ("us-east", "us-west", "eu-central", "ap-south")

_CLASS_CLUES: dict[SRECausalClass, tuple[str, ...]] = {
    SRECausalClass.REGRESSION: (
        "a recent rollout overlaps the start of symptoms",
        "a configuration change preceded the error increase",
        "the new build reached the affected shard shortly before impact",
        "a feature-flag transition occurred in the affected service",
    ),
    SRECausalClass.INFRASTRUCTURE: (
        "packet loss is isolated to a subset of hosts",
        "node-health probes are failing in one availability zone",
        "storage I/O latency rose sharply on the affected workers",
        "DNS resolution failures cluster on one network segment",
    ),
    SRECausalClass.CAPACITY: (
        "queue depth is increasing faster than workers can drain it",
        "connection-pool utilization is pinned near its limit",
        "request rate is well above the normal operating envelope",
        "worker saturation tracks the growing backlog",
    ),
    SRECausalClass.TRANSIENT: (
        "the burst self-cleared without operator intervention",
        "a brief upstream timeout burst ended before mitigation began",
        "the error spike recovered while resource pressure stayed normal",
        "intermittent upstream latency returned to baseline on its own",
    ),
}

_TITLE_CUES: dict[SRECausalClass, tuple[str, ...]] = {
    SRECausalClass.REGRESSION: ("errors after rollout", "new-build error spike"),
    SRECausalClass.INFRASTRUCTURE: ("host reachability degradation", "zonal node failures"),
    SRECausalClass.CAPACITY: ("queue backlog growing", "service saturation"),
    SRECausalClass.TRANSIENT: ("brief error burst", "intermittent timeout spike"),
}

_DISTRACTORS = (
    "traffic remains within the weekly range",
    "a routine deployment occurred elsewhere in the fleet",
    "one dashboard briefly reported elevated host latency",
    "an upstream dependency also showed a small error increase",
)


def _stratified_split(cases: list[SREQualificationCase]) -> dict[str, QualificationSplit]:
    grouped: dict[SRECausalClass, list[SREQualificationCase]] = defaultdict(list)
    for case in cases:
        grouped[case.causal_class].append(case)
    result: dict[str, QualificationSplit] = {}
    for label in SRECausalClass:
        rows = sorted(grouped[label], key=lambda item: stable_hash(item.scenario.source_group_id))
        n = len(rows)
        train_end = int(n * 0.60)
        dev_end = int(n * 0.80)
        for index, case in enumerate(rows):
            if index < train_end:
                split = QualificationSplit.TRAIN
            elif index < dev_end:
                split = QualificationSplit.DEV
            else:
                split = QualificationSplit.PRIVATE_TEST
            result[case.scenario.source_group_id] = split
    return result


def generate_commercial_sre_incidents(
    *,
    seed: int,
    per_class: int = 40,
) -> list[SREIncidentSource]:
    if per_class < 20:
        raise ValueError("commercial SRE generation requires at least 20 incidents per causal class")
    rng = random.Random(seed)
    incidents: list[SREIncidentSource] = []
    for class_index, label in enumerate(SRECausalClass):
        for index in range(per_class):
            service = _SERVICES[(index + class_index * 3 + rng.randrange(len(_SERVICES))) % len(_SERVICES)]
            region = _REGIONS[(index + rng.randrange(len(_REGIONS))) % len(_REGIONS)]
            clue = _CLASS_CLUES[label][index % len(_CLASS_CLUES[label])]
            title_has_cue = index % 2 == 0
            full_signal = index % 4 != 0
            title = (
                f"{service}: {_TITLE_CUES[label][index % len(_TITLE_CUES[label])]} in {region}"
                if title_has_cue
                else f"{service}: elevated errors and latency in {region}"
            )
            early = [
                f"Impact is limited to {service} in {region}; requests are intermittently failing.",
                clue if full_signal else _DISTRACTORS[(index + class_index) % len(_DISTRACTORS)],
                _DISTRACTORS[(index * 3 + class_index + 1) % len(_DISTRACTORS)],
            ]
            resolution = [
                f"Investigation confirmed the incident causal class as {label.value}.",
                f"The decisive evidence was: {clue}.",
                "The service returned to its expected error and latency envelope after the class-appropriate remediation completed.",
            ]
            incident_id = f"{label.value}-{stable_hash([seed, label.value, index])[:16]}"
            incidents.append(
                SREIncidentSource(
                    provider="veritas-synthetic",
                    incident_id=incident_id,
                    source_uri=f"veritas://sre-commercial-v1/{incident_id}",
                    title=title,
                    early_updates=early,
                    resolution_updates=resolution,
                    causal_class=label,
                    metadata={
                        "generator": "veritas-sre-commercial-v1",
                        "synthetic": True,
                        "text_copied_from_reference_sources": False,
                        "signal_strength": "multi" if full_signal else "ambiguous",
                        "title_cue": title_has_cue,
                    },
                )
            )
    return incidents


def build_commercial_sre_candidate(
    *,
    seed: int,
    per_class: int = 40,
    version: str = "sre-commercial-v1",
) -> tuple[QualificationCandidate, list[SREQualificationCase]]:
    incidents = generate_commercial_sre_incidents(seed=seed, per_class=per_class)
    candidate, cases = compile_sre_candidate(incidents, version=version)
    split_map = _stratified_split(cases)
    cases = [
        case.model_copy(
            update={
                "scenario": case.scenario.model_copy(
                    update={"split": split_map[case.scenario.source_group_id]}
                )
            }
        )
        for case in cases
    ]
    scenario_by_id = {case.scenario.scenario_id: case.scenario for case in cases}
    candidate = candidate.model_copy(
        update={
            "scenarios": [scenario_by_id[item.scenario_id] for item in candidate.scenarios],
            "metadata": {
                **candidate.metadata,
                "compiler": "veritas-sre-commercial-v1",
                "synthetic": True,
                "private_seed_required_for_release": True,
                "per_class": per_class,
                "source_references": list(COMMERCIAL_SRE_SOURCE_REFERENCES),
                "source_text_copied": False,
                "split_strategy": "deterministic-stratified-60-20-20-per-causal-class",
            },
        }
    )
    return candidate, cases


def _label_scores(text: str) -> dict[SRECausalClass, int]:
    value = text.casefold()
    tokens: dict[SRECausalClass, tuple[str, ...]] = {
        SRECausalClass.REGRESSION: ("rollout", "configuration change", "new build", "feature-flag"),
        SRECausalClass.INFRASTRUCTURE: ("packet loss", "node-health", "storage i/o", "dns resolution"),
        SRECausalClass.CAPACITY: ("queue depth", "connection-pool", "request rate", "saturation", "backlog"),
        SRECausalClass.TRANSIENT: ("self-cleared", "brief upstream", "recovered", "intermittent upstream"),
    }
    return {label: sum(token in value for token in patterns) for label, patterns in tokens.items()}


def _competent_prediction(public_text: str) -> SRECausalClass:
    scores = _label_scores(public_text)
    best = max(scores.values())
    if best <= 0:
        return SRECausalClass.TRANSIENT
    return max(SRECausalClass, key=lambda label: (scores[label], -list(SRECausalClass).index(label)))


def _myopic_prediction(public_text: str) -> SRECausalClass:
    title = public_text.splitlines()[0] if public_text else ""
    scores = _label_scores(title)
    best = max(scores.values())
    if best <= 0:
        return SRECausalClass.TRANSIENT
    return max(SRECausalClass, key=lambda label: (scores[label], -list(SRECausalClass).index(label)))


def execute_commercial_sre_policy_suite(
    cases: list[SREQualificationCase],
    *,
    random_seed: int = 7,
) -> list[PolicyEvaluation]:
    private_cases = [case for case in cases if case.scenario.split == QualificationSplit.PRIVATE_TEST]
    if not private_cases:
        raise ValueError("commercial SRE policy suite requires private-test cases")
    rng = random.Random(random_seed)
    labels = list(SRECausalClass)
    outcomes: dict[PolicyClass, list[PolicyOutcome]] = {kind: [] for kind in PolicyClass}
    for case in private_cases:
        predictions = {
            PolicyClass.ORACLE: case.causal_class,
            PolicyClass.COMPETENT_HEURISTIC: _competent_prediction(case.public_text),
            PolicyClass.MYOPIC: _myopic_prediction(case.public_text),
            PolicyClass.RANDOM: rng.choice(labels),
        }
        for kind, prediction in predictions.items():
            reward = 1.0 if prediction == case.causal_class else 0.0
            outcomes[kind].append(
                PolicyOutcome(
                    scenario_id=case.scenario.scenario_id,
                    reward=reward,
                    passed=reward == 1.0,
                    metadata={
                        "prediction": prediction.value,
                        "private_label_access": kind == PolicyClass.ORACLE,
                    },
                )
            )
        outcomes[PolicyClass.EXPLOIT].append(
            PolicyOutcome(
                scenario_id=case.scenario.scenario_id,
                reward=0.0,
                passed=False,
                metadata={"attempt": "unsupported-terminal-claim", "private_label_access": False},
            )
        )
    names = {
        PolicyClass.ORACLE: "private-causal-oracle",
        PolicyClass.COMPETENT_HEURISTIC: "multi-signal-public-evidence",
        PolicyClass.MYOPIC: "title-only-single-signal",
        PolicyClass.RANDOM: f"uniform-random-{random_seed}",
        PolicyClass.EXPLOIT: "unsupported-terminal-exploit",
    }
    return [
        PolicyEvaluation(policy_class=kind, policy_name=names[kind], outcomes=outcomes[kind])
        for kind in PolicyClass
    ]
