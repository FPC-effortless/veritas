from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.companyworld.models import CompanySystem, CompanyWorldEpisode
from investigation_world.foundry.models import MutationKind, MutationLineage, stable_hash
from investigation_world.foundry.mutations import apply_mutation
from investigation_world.observatory.companyworld import CompanyWorldBundleRepository
from investigation_world.observatory.models import CapabilityRun, DimensionDelta, ScenarioRef
from investigation_world.observatory.runtime_interventions import (
    ScheduledPermissionChange,
    ScheduledToolFailure,
)


TRUTH_PRESERVING_COMPANYWORLD_MUTATIONS: frozenset[MutationKind] = frozenset(
    {
        MutationKind.REORDER_RECORDS,
        MutationKind.INJECT_DISTRACTOR,
        MutationKind.REDACT_OPTIONAL_FIELD,
        MutationKind.TIGHTEN_BUDGET,
        MutationKind.TOOL_FAILURE,
        MutationKind.PERMISSION_CHANGE,
    }
)


class InterventionMutation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: MutationKind
    seed: int
    parameters: dict[str, Any] = Field(default_factory=dict)


class InterventionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    scenario: ScenarioRef
    mutations: list[InterventionMutation] = Field(min_length=1)
    truth_preserving: bool = True
    intervention_id: str = ""

    @model_validator(mode="after")
    def validate_id(self) -> "InterventionSpec":
        if self.truth_preserving:
            unsupported = [
                mutation.kind
                for mutation in self.mutations
                if mutation.kind not in TRUTH_PRESERVING_COMPANYWORLD_MUTATIONS
            ]
            if unsupported:
                raise ValueError(
                    "truth-preserving CompanyWorld interventions do not support: "
                    + ", ".join(item.value for item in unsupported)
                )
        payload = {
            "name": self.name,
            "scenario": self.scenario.model_dump(mode="json"),
            "mutations": [item.model_dump(mode="json") for item in self.mutations],
            "truth_preserving": self.truth_preserving,
        }
        expected = f"INT-{stable_hash(payload)[:20].upper()}"
        if self.intervention_id and self.intervention_id != expected:
            raise ValueError("intervention_id does not match intervention contents")
        object.__setattr__(self, "intervention_id", expected)
        return self


class InterventionMaterialization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    intervention_id: str
    source_episode_id: str
    source_world_version: str
    intervention_world_version: str
    truth_preserving: bool
    lineages: list[MutationLineage] = Field(default_factory=list)
    protected_record_ids: list[str] = Field(default_factory=list)


class InterventionEffectReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    intervention_id: str
    baseline_run_id: str
    intervention_run_id: str
    reward: DimensionDelta
    cost: DimensionDelta
    steps: DimensionDelta
    dimensions: dict[str, DimensionDelta] = Field(default_factory=dict)
    degraded_dimensions: list[str] = Field(default_factory=list)
    improved_dimensions: list[str] = Field(default_factory=list)
    interpretation: str = (
        "This report measures sensitivity to a deliberate environment intervention. It must not "
        "be interpreted as longitudinal model drift."
    )


def _supporting_record_ids(episode: CompanyWorldEpisode) -> list[str]:
    return sorted(
        {
            record_id
            for fact in episode.oracle.facts
            for record_id in fact.supporting_record_ids
        }
    )


def _permitted_system(
    episode: CompanyWorldEpisode,
    value: Any | None,
    *,
    label: str,
) -> CompanySystem:
    if value is None:
        if not episode.task.permitted_systems:
            raise ValueError(f"{label} requires a permitted CompanyWorld system")
        return episode.task.permitted_systems[0]
    system = CompanySystem(str(value))
    if system not in episode.task.permitted_systems:
        raise ValueError(
            f"{label} system {system.value!r} is not permitted by source task"
        )
    return system


def _companyworld_parameters(
    episode: CompanyWorldEpisode,
    mutation: InterventionMutation,
) -> dict[str, Any]:
    parameters = dict(mutation.parameters)
    if mutation.kind == MutationKind.INJECT_DISTRACTOR:
        parameters["system"] = _permitted_system(
            episode,
            parameters.get("system"),
            label="distractor intervention",
        ).value
    elif mutation.kind == MutationKind.TOOL_FAILURE:
        schedule = ScheduledToolFailure.model_validate(
            {
                "system": _permitted_system(
                    episode,
                    parameters.get("system"),
                    label="tool-failure intervention",
                ).value,
                "at_step": parameters.get("at_step", 0),
                "persistent": parameters.get("persistent", False),
            }
        )
        parameters.update(schedule.model_dump(mode="json"))
    elif mutation.kind == MutationKind.PERMISSION_CHANGE:
        schedule = ScheduledPermissionChange.model_validate(
            {
                "system": _permitted_system(
                    episode,
                    parameters.get("system"),
                    label="permission intervention",
                ).value,
                "at_step": parameters.get("at_step", 0),
                "action": parameters.get("action", "revoke"),
            }
        )
        parameters.update(schedule.model_dump(mode="json"))
    return parameters


def materialize_companyworld_intervention(
    repository: CompanyWorldBundleRepository,
    spec: InterventionSpec,
) -> tuple[CompanyWorldBundleRepository, InterventionMaterialization]:
    episode = repository.episode(spec.scenario)
    public_payload = episode.public_payload()
    protected = _supporting_record_ids(episode) if spec.truth_preserving else []
    lineages: list[MutationLineage] = []
    mutated = public_payload
    for mutation in spec.mutations:
        mutated, lineage = apply_mutation(
            mutated,
            task_id=episode.task.task_id,
            kind=mutation.kind,
            seed=mutation.seed,
            parameters=_companyworld_parameters(episode, mutation),
            protected_record_ids=protected,
        )
        lineages.append(lineage)

    intervention_episode = CompanyWorldEpisode.model_validate(
        {**mutated, "oracle": episode.oracle.model_dump(mode="json")}
    )
    taskset_version = f"{repository.taskset_version}+{spec.intervention_id}"
    variant = CompanyWorldBundleRepository(
        [intervention_episode],
        taskset_version=taskset_version,
        splits={"intervention": [intervention_episode.episode_id]},
    )
    materialization = InterventionMaterialization(
        intervention_id=spec.intervention_id,
        source_episode_id=episode.episode_id,
        source_world_version=repository.bundle_version,
        intervention_world_version=variant.bundle_version,
        truth_preserving=spec.truth_preserving,
        lineages=lineages,
        protected_record_ids=protected,
    )
    return variant, materialization


def _delta(before: float, after: float, tolerance: float) -> DimensionDelta:
    change = after - before
    relative = change / abs(before) if abs(before) > tolerance else None
    return DimensionDelta(
        baseline=before,
        current=after,
        delta=change,
        relative_delta=relative,
    )


def compare_intervention_runs(
    spec: InterventionSpec,
    baseline: CapabilityRun,
    intervention: CapabilityRun,
    *,
    tolerance: float = 1e-9,
) -> InterventionEffectReport:
    if baseline.cell.model != intervention.cell.model:
        raise ValueError("intervention comparison requires the same ModelSpec")
    if baseline.cell.harness != intervention.cell.harness:
        raise ValueError("intervention comparison requires the same HarnessSpec")
    if baseline.cell.verifier != intervention.cell.verifier:
        raise ValueError("intervention comparison requires the same VerifierSpec")
    if baseline.cell.execution != intervention.cell.execution:
        raise ValueError("intervention comparison requires the same ExecutionSpec")
    if baseline.cell.time_snapshot != intervention.cell.time_snapshot:
        raise ValueError("intervention comparison requires the same time snapshot")
    if baseline.cell.scenario.scenario_id != intervention.cell.scenario.scenario_id:
        raise ValueError("intervention comparison requires the same source scenario")
    if baseline.cell.scenario.task_id != intervention.cell.scenario.task_id:
        raise ValueError("intervention comparison requires the same task identity")
    if baseline.cell.scenario.seed != intervention.cell.scenario.seed:
        raise ValueError("intervention comparison requires the same scenario seed")

    dimensions: dict[str, DimensionDelta] = {}
    degraded: list[str] = []
    improved: list[str] = []
    for name in sorted(set(baseline.capability.dimensions) | set(intervention.capability.dimensions)):
        if name not in baseline.capability.dimensions or name not in intervention.capability.dimensions:
            continue
        delta = _delta(
            baseline.capability.dimensions[name],
            intervention.capability.dimensions[name],
            tolerance,
        )
        dimensions[name] = delta
        if delta.delta < -tolerance:
            degraded.append(name)
        elif delta.delta > tolerance:
            improved.append(name)

    return InterventionEffectReport(
        intervention_id=spec.intervention_id,
        baseline_run_id=baseline.run_id,
        intervention_run_id=intervention.run_id,
        reward=_delta(baseline.total_reward, intervention.total_reward, tolerance),
        cost=_delta(baseline.total_cost, intervention.total_cost, tolerance),
        steps=_delta(
            float(baseline.behavior.total_steps),
            float(intervention.behavior.total_steps),
            tolerance,
        ),
        dimensions=dimensions,
        degraded_dimensions=degraded,
        improved_dimensions=improved,
    )
