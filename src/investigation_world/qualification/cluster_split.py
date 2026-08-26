from __future__ import annotations

import hashlib
from collections import defaultdict

from investigation_world.qualification.models import (
    QualificationCandidate,
    QualificationScenario,
    QualificationSplit,
)
from investigation_world.qualification.source_disjoint import hamming64, simhash64, token_jaccard


def _component_key(component: list[QualificationScenario]) -> str:
    payload = "|".join(sorted(item.scenario_id for item in component))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def near_duplicate_components(
    scenarios: list[QualificationScenario],
    *,
    jaccard_threshold: float = 0.90,
    simhash_distance: int = 3,
) -> list[list[QualificationScenario]]:
    """Return transitive near-duplicate components independent of the current split.

    Qualification must partition *clusters* rather than individual scenarios; otherwise two
    semantically equivalent scenarios can be deterministically assigned to different splits and
    then correctly fail the contamination gate.
    """
    if not scenarios:
        return []
    parent = list(range(len(scenarios)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a = find(left)
        b = find(right)
        if a != b:
            parent[b] = a

    hashes = [simhash64(item.normalized_text) for item in scenarios]
    for left in range(len(scenarios)):
        a = scenarios[left]
        if not a.normalized_text:
            continue
        for right in range(left + 1, len(scenarios)):
            b = scenarios[right]
            if not b.normalized_text:
                continue
            if (
                token_jaccard(a.normalized_text, b.normalized_text) >= jaccard_threshold
                or hamming64(hashes[left], hashes[right]) <= simhash_distance
            ):
                union(left, right)

    groups: dict[int, list[QualificationScenario]] = defaultdict(list)
    for index, scenario in enumerate(scenarios):
        groups[find(index)].append(scenario)
    return sorted(
        (sorted(group, key=lambda item: item.scenario_id) for group in groups.values()),
        key=lambda group: (-len(group), _component_key(group)),
    )


def cluster_disjoint_split_map(
    scenarios: list[QualificationScenario],
    *,
    train_fraction: float = 0.60,
    dev_fraction: float = 0.20,
) -> dict[str, QualificationSplit]:
    """Assign whole near-duplicate components to deterministic train/dev/private splits."""
    components = near_duplicate_components(scenarios)
    if len(components) < 3:
        raise ValueError(
            "qualification requires at least three near-duplicate components for leakage-safe splitting"
        )
    total = len(scenarios)
    targets = {
        QualificationSplit.TRAIN: total * train_fraction,
        QualificationSplit.DEV: total * dev_fraction,
        QualificationSplit.PRIVATE_TEST: total * (1.0 - train_fraction - dev_fraction),
    }
    loads = {split: 0 for split in targets}
    assignments: dict[str, QualificationSplit] = {}

    # Seed every split with one independent component. Put the largest component in train, then
    # private test, then dev; this avoids a tiny private panel when one boilerplate family is large.
    seeded = [
        QualificationSplit.TRAIN,
        QualificationSplit.PRIVATE_TEST,
        QualificationSplit.DEV,
    ]
    for component, split in zip(components[:3], seeded, strict=True):
        for scenario in component:
            assignments[scenario.scenario_id] = split
        loads[split] += len(component)

    for component in components[3:]:
        size = len(component)
        split = min(
            targets,
            key=lambda item: (
                (loads[item] + size) / max(targets[item], 1.0),
                loads[item] / max(targets[item], 1.0),
                item.value,
            ),
        )
        for scenario in component:
            assignments[scenario.scenario_id] = split
        loads[split] += size
    return assignments


def repartition_candidate_by_near_duplicates(
    candidate: QualificationCandidate,
) -> tuple[QualificationCandidate, dict[str, QualificationSplit]]:
    mapping = cluster_disjoint_split_map(candidate.scenarios)
    scenarios = [
        scenario.model_copy(update={"split": mapping[scenario.scenario_id]})
        for scenario in candidate.scenarios
    ]
    metadata = {
        **candidate.metadata,
        "split_protocol": "near-duplicate-component-disjoint-v1",
        "near_duplicate_components": len(near_duplicate_components(candidate.scenarios)),
    }
    return candidate.model_copy(update={"scenarios": scenarios, "metadata": metadata}), mapping
