from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from itertools import combinations

from investigation_world.qualification.models import QualificationScenario

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalized_tokens(text: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(text.casefold()))


def normalized_text(text: str) -> str:
    return " ".join(normalized_tokens(text))


def token_jaccard(left: str, right: str) -> float:
    a = set(normalized_tokens(left))
    b = set(normalized_tokens(right))
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _token_hash(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")


def simhash64(text: str) -> int:
    tokens = normalized_tokens(text)
    if not tokens:
        return 0
    weights = [0] * 64
    for token in tokens:
        value = _token_hash(token)
        for bit in range(64):
            weights[bit] += 1 if value & (1 << bit) else -1
    fingerprint = 0
    for bit, weight in enumerate(weights):
        if weight >= 0:
            fingerprint |= 1 << bit
    return fingerprint


def hamming64(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def source_group_overlap(
    scenarios: list[QualificationScenario],
) -> dict[str, list[str]]:
    by_source: dict[str, set[str]] = defaultdict(set)
    for scenario in scenarios:
        by_source[scenario.source_group_id].add(scenario.split.value)
    return {
        source: sorted(splits)
        for source, splits in sorted(by_source.items())
        if len(splits) > 1
    }


def _candidate_pairs(
    scenarios: list[QualificationScenario],
) -> set[tuple[int, int]]:
    """LSH blocking for cross-split near-duplicate checks.

    Four 16-bit SimHash bands guarantee that fingerprints within Hamming distance <=3 share at
    least one band. Exact normalized-text matches are also always included.
    """
    hashes = [simhash64(item.normalized_text) for item in scenarios]
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    exact: dict[str, list[int]] = defaultdict(list)
    for index, scenario in enumerate(scenarios):
        value = hashes[index]
        for band in range(4):
            buckets[(band, (value >> (band * 16)) & 0xFFFF)].append(index)
        exact[normalized_text(scenario.normalized_text)].append(index)

    pairs: set[tuple[int, int]] = set()
    for members in [*buckets.values(), *exact.values()]:
        for left, right in combinations(sorted(set(members)), 2):
            if scenarios[left].split != scenarios[right].split:
                pairs.add((left, right))
    return pairs


def cross_split_near_duplicates(
    scenarios: list[QualificationScenario],
    *,
    jaccard_threshold: float = 0.90,
    simhash_distance: int = 3,
) -> list[tuple[str, str]]:
    if not 0.0 <= jaccard_threshold <= 1.0:
        raise ValueError("jaccard_threshold must be between 0 and 1")
    if not 0 <= simhash_distance <= 64:
        raise ValueError("simhash_distance must be between 0 and 64")

    hashes = [simhash64(item.normalized_text) for item in scenarios]
    matches: list[tuple[str, str]] = []
    for left, right in sorted(_candidate_pairs(scenarios)):
        a = scenarios[left]
        b = scenarios[right]
        if not a.normalized_text or not b.normalized_text:
            continue
        jaccard = token_jaccard(a.normalized_text, b.normalized_text)
        hamming = hamming64(hashes[left], hashes[right])
        if jaccard >= jaccard_threshold or hamming <= simhash_distance:
            matches.append(tuple(sorted((a.scenario_id, b.scenario_id))))
    return sorted(set(matches))
