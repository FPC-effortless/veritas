from __future__ import annotations

import copy
import random
from typing import Any

from pydantic import BaseModel, Field

from investigation_world.companyworld.models import CompanySystem, CompanyWorldEpisode, CompanyWorldRecord
from investigation_world.companyworld.runtime import CompanyWorldRuntime
from investigation_world.foundry.task_distribution import SampledTaskParameters
from investigation_world.foundry.models import stable_hash


class FoundryRuntimeConfig(BaseModel):
    total_cost: int = Field(ge=1)
    max_tool_calls: int = Field(ge=1)
    tool_failure_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    failure_seed: int


class MaterializedCompanyWorldTask(BaseModel):
    sample: SampledTaskParameters
    episode: CompanyWorldEpisode
    runtime: FoundryRuntimeConfig
    materialization: dict[str, Any] = Field(default_factory=dict)


def _perturb_value(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return round(value + max(1.0, abs(value) * 0.1), 6)
    if isinstance(value, str):
        upper = value.upper()
        if upper in {"LATE", "REVIEW", "BREACH", "OPEN", "DUPLICATE"}:
            return "ALTERNATE"
        return f"conflicting-{value}"
    return "conflicting-observation"


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


def materialize_companyworld_task(
    base_episode: CompanyWorldEpisode,
    sample: SampledTaskParameters,
) -> MaterializedCompanyWorldTask:
    """Turn sampled foundry parameters into an executable CompanyWorld episode.

    The oracle remains private and unchanged. Materialization only changes the
    public observation/tool surface and runtime conditions. Long-horizon control
    depth is handled by the interactive/sequential/dynamic compilers, not faked
    as decorative diagnostic metadata.
    """

    rng = random.Random(sample.seed)
    episode = copy.deepcopy(base_episode)
    support_ids = _support_record_ids(episode)
    records = list(episode.records)

    # Materialize entity count and distractor count into actual searchable records.
    distractor_count = max(sample.difficulty.distractors, sample.difficulty.entities - 1)
    permitted_seed_system = episode.task.permitted_systems[0] if episode.task.permitted_systems else CompanySystem.ERP
    for index in range(distractor_count):
        record_id = f"FR-{stable_hash([sample.sample_id, 'distractor', index])[:16].upper()}"
        records.append(
            CompanyWorldRecord(
                record_id=record_id,
                system=permitted_seed_system,
                record_type="foundry_distractor",
                object_type="DISTRACTOR_ENTITY",
                object_id=f"DIST-{sample.sample_id}-{index}",
                fields={
                    "note": "Plausible but unrelated operational record.",
                    "sample_id": sample.sample_id,
                },
                source_file="foundry/materialized",
                related_object_ids=[],
            )
        )

    # Materialize missingness by redacting optional, non-oracle fields only.
    redacted: list[tuple[str, str]] = []
    for record in records:
        if record.record_id in support_ids or rng.random() >= sample.difficulty.missing_probability:
            continue
        optional_fields = sorted(record.fields)
        if optional_fields:
            field_name = rng.choice(optional_fields)
            record.fields.pop(field_name, None)
            redacted.append((record.record_id, field_name))

    # Materialize contradiction/noise as explicit competing observations. These
    # are never oracle-listed supporting records, so the verifier cannot reward
    # trusting them blindly.
    conflicts: list[str] = []
    for fact_index, fact in enumerate(episode.oracle.facts):
        if rng.random() >= sample.difficulty.conflict_probability:
            continue
        record_id = f"FC-{stable_hash([sample.sample_id, 'conflict', fact_index])[:16].upper()}"
        system = permitted_seed_system
        support_record = next((r for r in records if r.record_id in fact.supporting_record_ids), None)
        if support_record is not None:
            system = support_record.system
        records.append(
            CompanyWorldRecord(
                record_id=record_id,
                system=system,
                record_type="foundry_conflicting_observation",
                object_type=fact.object_type,
                object_id=fact.object_id,
                fields={fact.field_name: _perturb_value(fact.expected_value)},
                source_file="foundry/adversarial",
                related_object_ids=[fact.object_id],
            )
        )
        conflicts.append(record_id)

    # Tool-count control never removes a system containing required supporting
    # evidence. Extra systems increase tool-selection burden.
    systems = _available_systems(episode)
    support_systems = {
        record.system for record in records if record.record_id in support_ids
    }
    target_tool_count = max(len(support_systems), sample.difficulty.tools)
    permitted = systems[: min(len(systems), target_tool_count)]
    for support_system in support_systems:
        if support_system not in permitted:
            permitted.append(support_system)
    permitted = sorted(set(permitted), key=lambda item: item.value)

    constraints = dict(episode.task.constraints)
    total_cost = max(5, round(40 * sample.difficulty.budget_ratio))
    max_calls = max(3, sample.difficulty.steps * max(1, len(permitted)) + sample.difficulty.dependency_depth)
    constraints.update(
        {
            "foundry_sample_id": sample.sample_id,
            "foundry_capabilities": list(sample.capability_tags),
            "foundry_budget": total_cost,
            "foundry_max_tool_calls": max_calls,
            "foundry_failure_probability": sample.difficulty.stochasticity,
            "foundry_adversarial_pressure": sample.difficulty.adversarial_pressure,
            "foundry_dependency_depth": sample.difficulty.dependency_depth,
        }
    )

    episode.task = episode.task.model_copy(
        update={
            "task_id": f"{episode.task.task_id}-{sample.sample_id[-8:]}",
            "permitted_systems": permitted,
            "constraints": constraints,
            "metadata": {
                **episode.task.metadata,
                "foundry_distribution_id": sample.distribution_id,
                "foundry_split": sample.split.value,
            },
        }
    )
    episode.episode_id = f"{episode.episode_id}-{sample.sample_id[-8:]}"
    episode.records = records
    episode.metadata = {
        **episode.metadata,
        "foundry_sample_id": sample.sample_id,
        "foundry_seed": sample.seed,
        "foundry_capabilities": list(sample.capability_tags),
    }
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
            "distractors_added": distractor_count,
            "redacted_fields": redacted,
            "conflict_records": conflicts,
            "permitted_systems": [item.value for item in permitted],
        },
    )


class FoundryCompanyWorldRuntime(CompanyWorldRuntime):
    """CompanyWorld runtime with deterministic foundry tool failures."""

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
            # Failure still consumes a call/cost because the attempted external
            # operation consumed resources, but reveals no hidden state.
            from investigation_world.companyworld.runtime import SYSTEM_TOOL_COSTS

            self._charge(SYSTEM_TOOL_COSTS[system])
            return []
        return super().search_system(system, query, limit=limit)
