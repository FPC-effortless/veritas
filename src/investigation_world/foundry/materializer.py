from __future__ import annotations

import copy
import random
from typing import Any

from pydantic import BaseModel, Field

from investigation_world.companyworld.models import CompanySystem, CompanyWorldEpisode, CompanyWorldRecord
from investigation_world.companyworld.runtime import CompanyWorldRuntime
from investigation_world.foundry.task_distribution import SampledTaskParameters
from investigation_world.foundry.models import stable_hash


class FoundryToolFailure(RuntimeError):
    """Observable transient tool failure with no access to the hidden failure schedule."""

    def __init__(self, system: CompanySystem, attempt: int):
        super().__init__(f"transient {system.value} tool failure; retry may succeed")
        self.system = system
        self.attempt = attempt
        self.retryable = True


class FoundryRuntimeConfig(BaseModel):
    total_cost: int = Field(ge=1)
    max_tool_calls: int = Field(ge=1)
    tool_failure_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    failure_seed: int


class MaterializedCompanyWorldTask(BaseModel):
    """Privileged compiled task. `sample` and `materialization` are evaluator-only."""

    sample: SampledTaskParameters
    episode: CompanyWorldEpisode
    runtime: FoundryRuntimeConfig
    materialization: dict[str, Any] = Field(default_factory=dict)


def _plausible_decoy(value: Any, rng: random.Random) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        candidates = [0, 1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000, 10000]
        candidates = [candidate for candidate in candidates if float(candidate) != float(value)]
        return rng.choice(candidates)
    if isinstance(value, str):
        candidates = [
            "OPEN", "CLOSED", "PENDING", "REVIEW", "MATCH", "LATE",
            "ON_TIME", "UNVERIFIED", "ESCALATE", "NO_ESCALATION",
        ]
        candidates = [candidate for candidate in candidates if candidate.casefold() != value.casefold()]
        return rng.choice(candidates) if candidates else "UNVERIFIED"
    return "UNVERIFIED"


def _support_record_ids(episode: CompanyWorldEpisode) -> set[str]:
    return {
        record_id
        for fact in episode.oracle.facts
        for record_id in fact.supporting_record_ids
    }


def _available_systems(episode: CompanyWorldEpisode) -> list[CompanySystem]:
    support = _support_record_ids(episode)
    support_systems = {
        record.system for record in episode.records if record.record_id in support
    }
    observed = {record.system for record in episode.records}
    remaining = [system for system in CompanySystem if system not in support_systems]
    return sorted(support_systems, key=lambda item: item.value) + sorted(
        observed.union(remaining) - support_systems,
        key=lambda item: item.value,
    )


def _alternate_system(
    support_system: CompanySystem | None,
    permitted_seed_system: CompanySystem,
    rng: random.Random,
) -> CompanySystem:
    candidates = [system for system in CompanySystem if system != support_system]
    if not candidates:
        return permitted_seed_system
    return rng.choice(candidates)


def materialize_companyworld_task(
    base_episode: CompanyWorldEpisode,
    sample: SampledTaskParameters,
) -> MaterializedCompanyWorldTask:
    """Turn latent foundry parameters into an executable partially-observed task.

    The public episode never receives the task split, seed, difficulty vector,
    adversarial pressure, conflict probability or stochastic failure schedule.
    Those remain on the privileged `MaterializedCompanyWorldTask`.
    """

    rng = random.Random(sample.seed)
    episode = copy.deepcopy(base_episode)
    support_ids = _support_record_ids(episode)
    records = list(episode.records)

    distractor_count = max(sample.difficulty.distractors, sample.difficulty.entities - 1)
    permitted_seed_system = episode.task.permitted_systems[0] if episode.task.permitted_systems else CompanySystem.ERP
    distractor_ids: list[str] = []
    for index in range(distractor_count):
        record_id = f"REC-{stable_hash([sample.sample_id, 'distractor', index])[:16].upper()}"
        distractor_ids.append(record_id)
        records.append(
            CompanyWorldRecord(
                record_id=record_id,
                system=permitted_seed_system,
                record_type="operational_note",
                object_type="OPERATIONAL_ENTITY",
                object_id=f"ENT-{stable_hash([sample.sample_id, index])[:12].upper()}",
                fields={"note": "Operational record associated with a different case."},
                source_file="derived/operational_snapshot",
                related_object_ids=[],
            )
        )

    redacted: list[tuple[str, str]] = []
    for record in records:
        if record.record_id in support_ids or rng.random() >= sample.difficulty.missing_probability:
            continue
        optional_fields = sorted(record.fields)
        if optional_fields:
            field_name = rng.choice(optional_fields)
            record.fields.pop(field_name, None)
            redacted.append((record.record_id, field_name))

    # Competing observations are deliberately indistinguishable by naming from
    # ordinary system snapshots. The decoy value is sampled with a private seed
    # rather than being an invertible arithmetic transform of ground truth.
    competing_ids: list[str] = []
    for fact_index, fact in enumerate(episode.oracle.facts):
        if rng.random() >= sample.difficulty.conflict_probability:
            continue
        record_id = f"REC-{stable_hash([sample.sample_id, 'snapshot', fact_index])[:16].upper()}"
        support_record = next((r for r in records if r.record_id in fact.supporting_record_ids), None)
        support_system = support_record.system if support_record is not None else None
        system = _alternate_system(support_system, permitted_seed_system, rng)
        records.append(
            CompanyWorldRecord(
                record_id=record_id,
                system=system,
                record_type="operational_snapshot",
                object_type=fact.object_type,
                object_id=fact.object_id,
                fields={fact.field_name: _plausible_decoy(fact.expected_value, rng)},
                source_file="derived/system_snapshot",
                related_object_ids=[fact.object_id],
            )
        )
        competing_ids.append(record_id)

    systems = _available_systems(episode)
    support_systems = {
        record.system for record in records if record.record_id in support_ids
    }
    target_tool_count = max(len(support_systems), sample.difficulty.tools)
    permitted = systems[: min(len(systems), target_tool_count)]
    for support_system in support_systems:
        if support_system not in permitted:
            permitted.append(support_system)
    # Ensure systems containing newly materialized competing evidence are usable.
    for record in records:
        if record.record_id in competing_ids and record.system not in permitted:
            permitted.append(record.system)
    permitted = sorted(set(permitted), key=lambda item: item.value)

    total_cost = max(5, round(40 * sample.difficulty.budget_ratio))
    max_calls = max(3, sample.difficulty.steps * max(1, len(permitted)) + sample.difficulty.dependency_depth)
    constraints = dict(episode.task.constraints)
    # Only constraints an agent could legitimately know are public.
    constraints.update({"budget": total_cost, "max_tool_calls": max_calls})

    episode.task = episode.task.model_copy(
        update={
            "task_id": f"{episode.task.task_id}-{sample.sample_id[-8:]}",
            "permitted_systems": permitted,
            "constraints": constraints,
        }
    )
    episode.episode_id = f"{episode.episode_id}-{sample.sample_id[-8:]}"
    episode.records = records
    episode.oracle.task_id = episode.task.task_id

    runtime = FoundryRuntimeConfig(
        total_cost=total_cost,
        max_tool_calls=max_calls,
        tool_failure_probability=sample.difficulty.stochasticity,
        failure_seed=sample.seed,
    )
    return MaterializedCompanyWorldTask(
        sample=sample,
        episode=episode,
        runtime=runtime,
        materialization={
            "distractor_record_ids": distractor_ids,
            "redacted_fields": redacted,
            "competing_record_ids": competing_ids,
            "permitted_systems": [item.value for item in permitted],
            "latent_difficulty": sample.difficulty.model_dump(mode="json"),
            "capability_tags": list(sample.capability_tags),
        },
    )


class FoundryCompanyWorldRuntime(CompanyWorldRuntime):
    """CompanyWorld runtime with private, deterministic failure randomness."""

    def __init__(self, task: MaterializedCompanyWorldTask):
        super().__init__(
            task.episode,
            total_cost=task.runtime.total_cost,
            max_tool_calls=task.runtime.max_tool_calls,
        )
        self.foundry_task = task
        self._failure_rng = random.Random(task.runtime.failure_seed)
        self._tool_attempt = 0

    def search_system(self, system: CompanySystem, query: str, limit: int = 10) -> list[dict]:
        if system not in self.episode.task.permitted_systems:
            return []
        self._tool_attempt += 1
        if self._failure_rng.random() < self.foundry_task.runtime.tool_failure_probability:
            from investigation_world.companyworld.runtime import SYSTEM_TOOL_COSTS

            self._charge(SYSTEM_TOOL_COSTS[system])
            raise FoundryToolFailure(system, self._tool_attempt)
        return super().search_system(system, query, limit=limit)
