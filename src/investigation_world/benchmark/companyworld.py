from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from investigation_world.benchmark.models import (
    BenchmarkInvariant,
    CompanyWorldBenchmarkReport,
    PolicyStatistics,
)
from investigation_world.benchmark.policies import DEFAULT_PUBLIC_POLICIES, PublicPolicy
from investigation_world.companyworld import CompanyWorldAdapter, split_episode_ids, verify_companyworld
from investigation_world.companyworld.models import CompanyWorldEpisode
from investigation_world.core.models import InvestigationResult


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _family_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "episodes": len(values),
        "mean_reward": statistics.fmean(values) if values else 0.0,
        "min_reward": min(values) if values else 0.0,
        "max_reward": max(values) if values else 0.0,
        "nonzero_rate": sum(value > 0 for value in values) / max(1, len(values)),
        "perfect_rate": sum(value >= 1.0 - 1e-12 for value in values) / max(1, len(values)),
    }


def _statistics(
    name: str,
    scored: list[tuple[str, float]],
    *,
    privileged: bool = False,
) -> PolicyStatistics:
    values = [reward for _, reward in scored]
    by_family_values: dict[str, list[float]] = defaultdict(list)
    for family, reward in scored:
        by_family_values[family].append(reward)
    return PolicyStatistics(
        policy=name,
        privileged=privileged,
        episodes=len(values),
        mean_reward=statistics.fmean(values) if values else 0.0,
        min_reward=min(values) if values else 0.0,
        max_reward=max(values) if values else 0.0,
        median_reward=statistics.median(values) if values else 0.0,
        p95_reward=_percentile(values, 0.95),
        nonzero_rate=sum(value > 0 for value in values) / max(1, len(values)),
        perfect_rate=sum(value >= 1.0 - 1e-12 for value in values) / max(1, len(values)),
        by_family={
            family: _family_summary(family_values)
            for family, family_values in sorted(by_family_values.items())
        },
    )


def _oracle_result(episode: CompanyWorldEpisode, *, include_evidence: bool = True) -> InvestigationResult:
    claims = []
    evidence = []
    for fact in episode.oracle.facts:
        claims.append(
            {
                "object_type": fact.object_type,
                "object_id": fact.object_id,
                "field_name": fact.field_name,
                "value": fact.expected_value,
            }
        )
        if include_evidence and fact.supporting_record_ids:
            evidence.append({"record_id": fact.supporting_record_ids[0]})
    return InvestigationResult(
        claims=claims,
        evidence=evidence,
        overall_confidence=1.0,
    )


def _score_public_policy(
    policy: PublicPolicy,
    episodes: Iterable[CompanyWorldEpisode],
) -> PolicyStatistics:
    scored: list[tuple[str, float]] = []
    for episode in episodes:
        result = policy(episode.public_payload())
        reward = verify_companyworld(result, episode).overall_reward
        scored.append((episode.task.task_type, reward))
    return _statistics(policy.name, scored)


def _score_privileged_oracle(episodes: Iterable[CompanyWorldEpisode]) -> PolicyStatistics:
    scored: list[tuple[str, float]] = []
    for episode in episodes:
        reward = verify_companyworld(_oracle_result(episode), episode).overall_reward
        scored.append((episode.task.task_type, reward))
    return _statistics("privileged_oracle", scored, privileged=True)


def _score_oracle_without_evidence(episodes: Iterable[CompanyWorldEpisode]) -> PolicyStatistics:
    scored: list[tuple[str, float]] = []
    for episode in episodes:
        reward = verify_companyworld(
            _oracle_result(episode, include_evidence=False), episode
        ).overall_reward
        scored.append((episode.task.task_type, reward))
    return _statistics("oracle_without_evidence", scored, privileged=True)


def _public_hash(episodes: list[CompanyWorldEpisode]) -> str:
    payload = [episode.public_payload() for episode in episodes]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _invariant(
    name: str,
    passed: bool,
    observed,
    expected,
    detail: str = "",
) -> BenchmarkInvariant:
    return BenchmarkInvariant(
        name=name,
        passed=bool(passed),
        observed=observed,
        expected=expected,
        detail=detail,
    )


def validate_companyworld_benchmark(
    dataset: str | Path,
    *,
    limit: int | None = None,
    policies: tuple[PublicPolicy, ...] = DEFAULT_PUBLIC_POLICIES,
    verify_determinism: bool = True,
) -> CompanyWorldBenchmarkReport:
    adapter = CompanyWorldAdapter(dataset)
    source_report = adapter.validate()
    episodes = adapter.compile_episodes(limit=limit)
    family_counts = Counter(episode.task.task_type for episode in episodes)
    split_counts = {
        name: len(ids) for name, ids in split_episode_ids(episodes).items()
    }

    policy_stats = [_score_public_policy(policy, episodes) for policy in policies]
    policy_stats.append(_score_privileged_oracle(episodes))
    policy_stats.append(_score_oracle_without_evidence(episodes))
    by_name = {item.policy: item for item in policy_stats}

    leakage_count = sum(bool(adapter.public_projection_leaks(episode)) for episode in episodes)
    missing_direct_support = sum(
        not fact.supporting_record_ids
        for episode in episodes
        for fact in episode.oracle.facts
    )
    answerable_without_records = sum(
        episode.oracle.answerable and not episode.records for episode in episodes
    )

    invariants = [
        _invariant(
            "source_integrity",
            source_report.valid,
            source_report.errors,
            [],
            "CompanyWorld's ledger/FK/inventory validation and task-oracle alignment must pass.",
        ),
        _invariant("public_oracle_leakage", leakage_count == 0, leakage_count, 0),
        _invariant("direct_evidence_available", missing_direct_support == 0, missing_direct_support, 0),
        _invariant("answerable_tasks_have_records", answerable_without_records == 0, answerable_without_records, 0),
        _invariant(
            "privileged_oracle_succeeds",
            by_name["privileged_oracle"].min_reward >= 1.0 - 1e-12,
            by_name["privileged_oracle"].min_reward,
            1.0,
        ),
        _invariant(
            "public_reference_solver_succeeds",
            by_name["public_evidence_reference"].min_reward >= 1.0 - 1e-12,
            by_name["public_evidence_reference"].min_reward,
            1.0,
            "Every task must be solvable from public evidence without oracle access.",
        ),
        _invariant("empty_policy_zero", by_name["empty"].max_reward == 0.0, by_name["empty"].max_reward, 0.0),
        _invariant(
            "conclusion_only_zero",
            by_name["conclusion_only"].max_reward == 0.0,
            by_name["conclusion_only"].max_reward,
            0.0,
        ),
        _invariant(
            "always_abstain_zero_on_answerable",
            by_name["always_abstain"].max_reward == 0.0,
            by_name["always_abstain"].max_reward,
            0.0,
        ),
        _invariant(
            "citation_only_zero",
            by_name["cite_everything"].max_reward == 0.0,
            by_name["cite_everything"].max_reward,
            0.0,
        ),
        _invariant(
            "wrong_projection_zero",
            by_name["projection_trust"].max_reward == 0.0,
            by_name["projection_trust"].max_reward,
            0.0,
            "Blind trust in the intentionally divergent system projection must never score.",
        ),
        _invariant(
            "field_stuffing_bounded",
            by_name["field_stuffing"].max_reward <= 0.25,
            by_name["field_stuffing"].max_reward,
            "<= 0.25",
        ),
        _invariant(
            "evidence_has_value",
            by_name["oracle_without_evidence"].max_reward < by_name["privileged_oracle"].min_reward,
            {
                "without_evidence_max": by_name["oracle_without_evidence"].max_reward,
                "with_evidence_min": by_name["privileged_oracle"].min_reward,
            },
            "without evidence < with direct evidence",
        ),
    ]

    if verify_determinism:
        repeat = CompanyWorldAdapter(dataset).compile_episodes(limit=limit)
        first_hash = _public_hash(episodes)
        second_hash = _public_hash(repeat)
        invariants.append(
            _invariant(
                "deterministic_compilation",
                first_hash == second_hash,
                first_hash,
                second_hash,
            )
        )

    errors = [item.name for item in invariants if not item.passed]
    return CompanyWorldBenchmarkReport(
        world_id=adapter.world_id,
        episodes=len(episodes),
        task_families=dict(sorted(family_counts.items())),
        splits=split_counts,
        invariants=invariants,
        policies=policy_stats,
        errors=errors,
        warnings=source_report.warnings,
        metadata={
            "source_validation": source_report.model_dump(mode="json"),
            "public_payload_sha256": _public_hash(episodes),
            "policy_interface": "public_payload_only",
            "determinism_checked": verify_determinism,
        },
    )


def write_companyworld_benchmark_report(
    dataset: str | Path,
    output: str | Path,
    *,
    limit: int | None = None,
    verify_determinism: bool = True,
) -> CompanyWorldBenchmarkReport:
    report = validate_companyworld_benchmark(
        dataset,
        limit=limit,
        verify_determinism=verify_determinism,
    )
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2))
    return report
