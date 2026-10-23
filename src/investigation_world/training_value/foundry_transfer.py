from __future__ import annotations

import json
from statistics import mean
from typing import Any, Callable

from investigation_world.benchmark.policies import PublicEvidenceReferencePolicy
from investigation_world.calibration.fixtures import build_o2c_episode
from investigation_world.calibration.full_context import _claims, _json_object, _prompt
from investigation_world.companyworld.models import CompanyWorldEpisode
from investigation_world.companyworld.verifier import verify_companyworld
from investigation_world.foundry import (
    DifficultyVector,
    DistributionSplit,
    SampledTaskParameters,
    materialize_companyworld_task,
)

GenerateFn = Callable[[str], str]


def _sample(
    *,
    split: DistributionSplit,
    seed: int,
    distractors: int,
    entities: int,
    tools: int,
    missing: float,
    conflict: float,
    budget_ratio: float,
    adversarial_pressure: float,
) -> SampledTaskParameters:
    return SampledTaskParameters(
        sample_id=f"FT-{split.value.upper()}-{seed:05d}",
        distribution_id="foundry-transfer-v1",
        split=split,
        seed=seed,
        capability_tags=["discover", "interpret", "verify"],
        task_family="O2C_FULFILLMENT_TIMING",
        domain="operations",
        difficulty=DifficultyVector(
            entities=entities,
            tools=tools,
            steps=2,
            distractors=distractors,
            missing_probability=missing,
            conflict_probability=conflict,
            dependency_depth=2,
            budget_ratio=budget_ratio,
            stochasticity=0.0,
            adversarial_pressure=adversarial_pressure,
        ),
    )


def _materialized_episode(index: int, sample: SampledTaskParameters, *, delay: int) -> CompanyWorldEpisode:
    base = build_o2c_episode(index, delay_days=delay)
    world_id = {
        DistributionSplit.TRAIN: "CW-FOUNDRY-TRAIN",
        DistributionSplit.IID_TEST: "CW-FOUNDRY-IID",
        DistributionSplit.OOD: "CW-FOUNDRY-OOD",
        DistributionSplit.ADVERSARIAL: "CW-FOUNDRY-ADVERSARIAL",
    }[sample.split]
    task = base.task.model_copy(update={"world_id": world_id})
    base = base.model_copy(update={"world_id": world_id, "task": task})
    return materialize_companyworld_task(base, sample).episode


def build_transfer_suite(
    *,
    train_candidates: int = 24,
    eval_per_split: int = 8,
) -> dict[str, list[CompanyWorldEpisode]]:
    suites: dict[str, list[CompanyWorldEpisode]] = {"train_pool": [], "iid": [], "ood": [], "adversarial": []}

    for offset in range(train_candidates):
        index = 2000 + offset
        sample = _sample(
            split=DistributionSplit.TRAIN,
            seed=100 + offset,
            distractors=offset % 3,
            entities=1 + (offset % 3),
            tools=2 + (offset % 2),
            missing=0.0 if offset % 3 else 0.1,
            conflict=0.0 if offset % 4 else 0.15,
            budget_ratio=1.0,
            adversarial_pressure=0.1,
        )
        suites["train_pool"].append(_materialized_episode(index, sample, delay=(offset * 3 + 1) % 8))

    for offset in range(eval_per_split):
        index = 4000 + offset
        sample = _sample(
            split=DistributionSplit.IID_TEST,
            seed=400 + offset,
            distractors=offset % 3,
            entities=1 + (offset % 3),
            tools=2 + (offset % 2),
            missing=0.0 if offset % 3 else 0.1,
            conflict=0.0 if offset % 4 else 0.15,
            budget_ratio=1.0,
            adversarial_pressure=0.1,
        )
        suites["iid"].append(_materialized_episode(index, sample, delay=(offset * 5 + 2) % 8))

        ood_sample = _sample(
            split=DistributionSplit.OOD,
            seed=600 + offset,
            distractors=3 + (offset % 3),
            entities=4 + (offset % 3),
            tools=4,
            missing=0.2,
            conflict=0.35,
            budget_ratio=0.75,
            adversarial_pressure=0.45,
        )
        suites["ood"].append(_materialized_episode(6000 + offset, ood_sample, delay=8 + (offset % 8)))

        adv_sample = _sample(
            split=DistributionSplit.ADVERSARIAL,
            seed=800 + offset,
            distractors=5 + (offset % 3),
            entities=6 + (offset % 2),
            tools=5,
            missing=0.3,
            conflict=1.0,
            budget_ratio=0.6,
            adversarial_pressure=1.0,
        )
        episode = _materialized_episode(8000 + offset, adv_sample, delay=(offset * 7 + 3) % 12)
        # Reorder records deterministically so surface order cannot be memorized.
        episode.records = list(reversed(episode.records))
        suites["adversarial"].append(episode)

    return suites


def _target_payload(episode: CompanyWorldEpisode) -> dict[str, Any]:
    result = PublicEvidenceReferencePolicy()(episode.public_payload())
    return {
        "claims": [
            {"field_name": claim.get("field_name"), "value": claim.get("value")}
            for claim in result.claims
        ],
        "evidence_record_ids": [item.get("record_id") for item in result.evidence],
        "confidence": 1.0,
    }


def score_generator(generate: GenerateFn, episodes: list[CompanyWorldEpisode]) -> dict[str, Any]:
    scores: list[float] = []
    parse_failures = 0
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        payload = _json_object(generate(_prompt("diagnostic", episode.public_payload())))
        if not payload:
            parse_failures += 1
        result = _claims(payload, episode.task.model_dump(mode="json"))
        score = verify_companyworld(result, episode).overall_reward
        scores.append(score)
        rows.append({"episode_id": episode.episode_id, "score": round(score, 6), "parsed": bool(payload)})
    return {
        "mean": round(mean(scores), 6) if scores else 0.0,
        "min": round(min(scores), 6) if scores else 0.0,
        "max": round(max(scores), 6) if scores else 0.0,
        "parse_failures": parse_failures,
        "episodes": rows,
    }


def select_frontier_examples(
    generate: GenerateFn,
    candidates: list[CompanyWorldEpisode],
    *,
    lower: float = 0.10,
    upper: float = 0.70,
    minimum: int = 8,
) -> dict[str, Any]:
    scored: list[tuple[float, CompanyWorldEpisode]] = []
    for episode in candidates:
        payload = _json_object(generate(_prompt("diagnostic", episode.public_payload())))
        result = _claims(payload, episode.task.model_dump(mode="json"))
        score = verify_companyworld(result, episode).overall_reward
        scored.append((score, episode))
    frontier = [(score, episode) for score, episode in scored if lower <= score <= upper]
    fallback = False
    if len(frontier) < minimum:
        fallback = True
        # If there is no learnability frontier yet, train on the easiest measured
        # cases rather than mislabeling impossible tasks as frontier matched.
        ranked = sorted(scored, key=lambda item: (-item[0], len(item[1].records), item[1].episode_id))
        frontier = ranked[: min(max(minimum, len(frontier)), len(ranked))]
    return {
        "episodes": [episode for _, episode in frontier],
        "scores": [round(score, 6) for score, _ in frontier],
        "frontier_matched": not fallback,
        "candidate_mean": round(mean(score for score, _ in scored), 6) if scored else 0.0,
        "candidate_success_rate": round(sum(score > 0 for score, _ in scored) / len(scored), 6) if scored else 0.0,
        "window": [lower, upper],
    }


def build_training_rows(frontier_episodes: list[CompanyWorldEpisode], *, target_count: int = 48) -> list[dict[str, Any]]:
    if not frontier_episodes:
        return []
    rows: list[dict[str, Any]] = []
    for index in range(target_count):
        episode = frontier_episodes[index % len(frontier_episodes)]
        rows.append(
            {
                "episode": episode,
                "prompt": _prompt("diagnostic", episode.public_payload()),
                "target": json.dumps(_target_payload(episode), sort_keys=True),
            }
        )
    return rows
