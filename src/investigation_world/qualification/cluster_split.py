from __future__ import annotations

import hashlib
from collections import Counter, defaultdict

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


def _targets(
    total: int,
    *,
    train_fraction: float,
    dev_fraction: float,
) -> dict[QualificationSplit, float]:
    return {
        QualificationSplit.TRAIN: total * train_fraction,
        QualificationSplit.DEV: total * dev_fraction,
        QualificationSplit.PRIVATE_TEST: total * (1.0 - train_fraction - dev_fraction),
    }


def _assign_component(
    component: list[QualificationScenario],
    split: QualificationSplit,
    *,
    assignments: dict[str, QualificationSplit],
    loads: dict[QualificationSplit, int],
) -> None:
    for scenario in component:
        assignments[scenario.scenario_id] = split
    loads[split] += len(component)


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
    targets = _targets(len(scenarios), train_fraction=train_fraction, dev_fraction=dev_fraction)
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
        _assign_component(component, split, assignments=assignments, loads=loads)

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
        _assign_component(component, split, assignments=assignments, loads=loads)
    return assignments


def _component_strata(
    component: list[QualificationScenario],
    metadata_key: str,
) -> Counter[str]:
    return Counter(str(item.metadata.get(metadata_key, "<missing>")) for item in component)


def stratified_cluster_disjoint_split_map(
    scenarios: list[QualificationScenario],
    *,
    stratum_metadata_key: str,
    minimum_private_scenarios_per_stratum: int = 5,
    minimum_train_scenarios_per_stratum: int = 1,
    train_fraction: float = 0.60,
    dev_fraction: float = 0.20,
) -> dict[str, QualificationSplit]:
    """Partition duplicate clusters while deterministically protecting label/stratum coverage.

    The split is allowed to use evaluator-only stratum metadata because it is constructed before
    any model or policy result is inspected. Near-duplicate components remain atomic, so this does
    not trade class balance for contamination. If the source pool lacks enough examples of a
    stratum, the function makes the best deterministic allocation and the qualification coverage
    gate remains responsible for rejecting the candidate.
    """
    components = near_duplicate_components(scenarios)
    if len(components) < 3:
        raise ValueError(
            "qualification requires at least three near-duplicate components for leakage-safe splitting"
        )

    component_counts = [_component_strata(component, stratum_metadata_key) for component in components]
    all_strata = sorted(
        {
            str(item.metadata.get(stratum_metadata_key, "<missing>"))
            for item in scenarios
        }
    )
    targets = _targets(len(scenarios), train_fraction=train_fraction, dev_fraction=dev_fraction)
    loads = {split: 0 for split in targets}
    assignments: dict[str, QualificationSplit] = {}
    unassigned = set(range(len(components)))

    def allocate_for_deficits(
        split: QualificationSplit,
        minimum_per_stratum: int,
    ) -> None:
        if minimum_per_stratum <= 0:
            return
        deficits = {stratum: minimum_per_stratum for stratum in all_strata}
        while unassigned and any(value > 0 for value in deficits.values()):
            def support(index: int) -> tuple[int, int, float, int, str]:
                counts = component_counts[index]
                covered = sum(
                    min(counts.get(stratum, 0), max(deficits[stratum], 0))
                    for stratum in all_strata
                )
                strata_covered = sum(
                    1
                    for stratum in all_strata
                    if deficits[stratum] > 0 and counts.get(stratum, 0) > 0
                )
                size = len(components[index])
                density = covered / max(size, 1)
                # max() prefers high useful support/density, then smaller clusters, then a stable key.
                return (covered, strata_covered, density, -size, _component_key(components[index]))

            index = max(unassigned, key=support)
            useful = support(index)[0]
            if useful <= 0:
                break
            _assign_component(
                components[index],
                split,
                assignments=assignments,
                loads=loads,
            )
            unassigned.remove(index)
            for stratum, count in component_counts[index].items():
                if stratum in deficits:
                    deficits[stratum] = max(0, deficits[stratum] - count)

    # Protect private support first, then enough labelled training support for the public baseline.
    allocate_for_deficits(QualificationSplit.PRIVATE_TEST, minimum_private_scenarios_per_stratum)
    allocate_for_deficits(QualificationSplit.TRAIN, minimum_train_scenarios_per_stratum)

    # Every split must still contain at least one independent component.
    if loads[QualificationSplit.DEV] == 0 and unassigned:
        index = min(unassigned, key=lambda i: _component_key(components[i]))
        _assign_component(
            components[index],
            QualificationSplit.DEV,
            assignments=assignments,
            loads=loads,
        )
        unassigned.remove(index)
    if loads[QualificationSplit.TRAIN] == 0 and unassigned:
        index = min(unassigned, key=lambda i: _component_key(components[i]))
        _assign_component(
            components[index],
            QualificationSplit.TRAIN,
            assignments=assignments,
            loads=loads,
        )
        unassigned.remove(index)
    if loads[QualificationSplit.PRIVATE_TEST] == 0 and unassigned:
        index = min(unassigned, key=lambda i: _component_key(components[i]))
        _assign_component(
            components[index],
            QualificationSplit.PRIVATE_TEST,
            assignments=assignments,
            loads=loads,
        )
        unassigned.remove(index)

    # Fill toward the requested global fractions without breaking the protected coverage above.
    for index in sorted(unassigned, key=lambda i: _component_key(components[i])):
        component = components[index]
        size = len(component)
        split = min(
            targets,
            key=lambda item: (
                (loads[item] + size) / max(targets[item], 1.0),
                loads[item] / max(targets[item], 1.0),
                item.value,
            ),
        )
        _assign_component(component, split, assignments=assignments, loads=loads)

    return assignments


def repartition_candidate_by_near_duplicates(
    candidate: QualificationCandidate,
    *,
    stratum_metadata_key: str | None = None,
    minimum_private_scenarios_per_stratum: int = 0,
    minimum_train_scenarios_per_stratum: int = 0,
) -> tuple[QualificationCandidate, dict[str, QualificationSplit]]:
    if stratum_metadata_key:
        mapping = stratified_cluster_disjoint_split_map(
            candidate.scenarios,
            stratum_metadata_key=stratum_metadata_key,
            minimum_private_scenarios_per_stratum=minimum_private_scenarios_per_stratum,
            minimum_train_scenarios_per_stratum=minimum_train_scenarios_per_stratum,
        )
        split_protocol = "near-duplicate-component-disjoint-stratified-v2"
    else:
        mapping = cluster_disjoint_split_map(candidate.scenarios)
        split_protocol = "near-duplicate-component-disjoint-v1"

    scenarios = [
        scenario.model_copy(update={"split": mapping[scenario.scenario_id]})
        for scenario in candidate.scenarios
    ]
    metadata = {
        **candidate.metadata,
        "split_protocol": split_protocol,
        "near_duplicate_components": len(near_duplicate_components(candidate.scenarios)),
    }
    if stratum_metadata_key:
        metadata.update(
            {
                "stratum_metadata_key": stratum_metadata_key,
                "minimum_private_scenarios_per_stratum": minimum_private_scenarios_per_stratum,
                "minimum_train_scenarios_per_stratum": minimum_train_scenarios_per_stratum,
            }
        )
    return candidate.model_copy(update={"scenarios": scenarios, "metadata": metadata}), mapping
