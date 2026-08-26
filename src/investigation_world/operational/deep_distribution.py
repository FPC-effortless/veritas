from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Iterator

from investigation_world.foundry.models import DifficultyVector, stable_hash
import investigation_world.operational.distribution as base
from investigation_world.operational.models import OperationalEpisode
from investigation_world.operational.realism import apply_domain_realism


class OperationalDistributionConfig(base.OperationalDistributionConfig):
    """Production-scale v2 distribution with domain-native realism enabled."""

    version: str = "operational-production-v2"


OperationalDistributionCase = base.OperationalDistributionCase
OperationalDistributionManifest = base.OperationalDistributionManifest
SCENARIO_FAMILIES = base.SCENARIO_FAMILIES


def _strip_private_generator_labels(episode: OperationalEpisode) -> None:
    """Remove generator labels that may have been useful while constructing public records."""

    for record in episode.records:
        record.fields.pop("scenario", None)
        record.fields.pop("scenario_family", None)


def _opaque_new_record_ids(episode: OperationalEpisode) -> OperationalEpisode:
    """Remap realism-layer record IDs after the base compiler has already remapped its records."""

    new_ids = [record.record_id for record in episode.records if "-deep-" in record.record_id]
    record_map = {
        record_id: f"deep-{stable_hash({'task': episode.task.task_id, 'record': record_id})[:20]}"
        for record_id in new_ids
    }
    if not record_map:
        return episode
    for record in episode.records:
        record.record_id = record_map.get(record.record_id, record.record_id)
        record.provenance_ids = [record_map.get(item, item) for item in record.provenance_ids]
    episode.oracle.required_evidence_ids = [
        record_map.get(record_id, record_id) for record_id in episode.oracle.required_evidence_ids
    ]
    for effect in episode.oracle.action_effects:
        if "record_id" in effect.required_parameters:
            value = effect.required_parameters["record_id"]
            if value in record_map:
                effect.required_parameters["record_id"] = record_map[value]
    return OperationalEpisode.model_validate(episode.model_dump(mode="python"))


def _deep_difficulty(case: OperationalDistributionCase) -> DifficultyVector:
    episode = case.episode
    entity_ids = {record.object_id for record in episode.records} | {
        related for record in episode.records for related in record.related_object_ids
    }
    required_steps = sum(
        max(1, episode.oracle.required_action_counts.get(action, 1))
        for action in set(episode.oracle.required_actions) | set(episode.oracle.required_action_counts)
    )
    return DifficultyVector(
        entities=max(1, len(entity_ids)),
        tools=len(episode.task.available_actions),
        steps=max(1, required_steps),
        distractors=case.difficulty.distractors,
        missing_probability=case.difficulty.missing_probability,
        conflict_probability=case.difficulty.conflict_probability,
        dependency_depth=max(
            case.difficulty.dependency_depth,
            len(episode.oracle.required_action_order),
            required_steps,
        ),
        budget_ratio=round(
            episode.oracle.max_cost
            / max(1, sum(action.cost for action in episode.task.available_actions)),
            3,
        ),
        stochasticity=case.difficulty.stochasticity,
        adversarial_pressure=case.difficulty.adversarial_pressure,
    )


def _deepen_case(case: OperationalDistributionCase) -> OperationalDistributionCase:
    realism_rng = random.Random(case.seed ^ 0x5A17C0DE)
    episode = apply_domain_realism(
        case.episode,
        rng=realism_rng,
        index=case.seed % 10_000,
        scenario_family=case.scenario_family,
    )
    _strip_private_generator_labels(episode)
    case.episode = _opaque_new_record_ids(episode)
    case.difficulty = _deep_difficulty(case)
    return case


def iter_operational_distribution(
    config: OperationalDistributionConfig | None = None,
) -> Iterator[OperationalDistributionCase]:
    config = config or OperationalDistributionConfig()
    for case in base.iter_operational_distribution(config):
        yield _deepen_case(case)


def compile_operational_distribution(
    config: OperationalDistributionConfig | None = None,
) -> list[OperationalDistributionCase]:
    return list(iter_operational_distribution(config))


def distribution_manifest(
    cases: list[OperationalDistributionCase],
    *,
    config: OperationalDistributionConfig,
    include_private_hash: bool = True,
) -> OperationalDistributionManifest:
    manifest = base.distribution_manifest(
        cases,
        config=config,
        include_private_hash=include_private_hash,
    )
    manifest.metadata.update(
        {
            "realism_profile": "domain_native_operational_v2",
            "stateful_action_preconditions": True,
            "ordered_process_verification": True,
            "temporal_provenance_records": True,
            "trajectory_invariants": True,
        }
    )
    return manifest


def validate_operational_distribution(
    cases: list[OperationalDistributionCase],
    *,
    config: OperationalDistributionConfig,
) -> dict[str, Any]:
    result = base.validate_operational_distribution(cases, config=config)
    errors = list(result["errors"])
    required_artifact_contracts = {
        "financial_spreadsheet": "xlsx_formula_dependency_graph_v2",
        "enterprise_operations": "crm_cpq_erp_control_graph_v2",
        "devops_incident_response": "incident_telemetry_dependency_graph_v2",
        "investigation_osint": "multi_source_provenance_casefile_v2",
        "gis_operations": "vector_crs_topology_lineage_v2",
    }
    for case in cases:
        episode = case.episode
        domain = episode.task.domain.value
        if episode.metadata.get("realism_profile") != "domain_native_operational_v2":
            errors.append(f"{episode.task.task_id}: missing deep realism profile")
            break
        if episode.task.metadata.get("artifact_contract") != required_artifact_contracts[domain]:
            errors.append(f"{episode.task.task_id}: missing domain artifact contract")
            break
        if len(episode.records) < 8:
            errors.append(f"{episode.task.task_id}: insufficient domain records")
            break
        if len({record.system for record in episode.records}) < 3:
            errors.append(f"{episode.task.task_id}: insufficient system heterogeneity")
            break
        if len(episode.task.available_actions) < 5:
            errors.append(f"{episode.task.task_id}: insufficient action surface")
            break
        if len(episode.oracle.required_action_order) < 5:
            errors.append(f"{episode.task.task_id}: insufficient procedural depth")
            break
        if not any(effect.required_state for effect in episode.oracle.action_effects):
            errors.append(f"{episode.task.task_id}: no stateful preconditions")
            break
        if not any(invariant.scope == "always" for invariant in episode.oracle.invariants):
            errors.append(f"{episode.task.task_id}: no trajectory invariant")
            break
        if not any(record.observed_at and record.source_authority for record in episode.records):
            errors.append(f"{episode.task.task_id}: missing temporal/provenance records")
            break
        if any(
            "scenario" in record.fields or "scenario_family" in record.fields
            for record in episode.records
        ):
            errors.append(f"{episode.task.task_id}: private generator field leaked publicly")
            break
        public_text = json.dumps(episode.public_payload(), sort_keys=True, default=str)
        if "required_action_order" in public_text or "required_state" in public_text:
            errors.append(f"{episode.task.task_id}: hidden process truth leaked publicly")
            break
        literal_family = f'"{case.scenario_family.casefold()}"'
        if literal_family in public_text.casefold():
            errors.append(f"{episode.task.task_id}: literal scenario-family label leaked publicly")
            break

    manifest = distribution_manifest(cases, config=config)
    result["valid"] = not errors
    result["errors"] = errors
    result["manifest"] = manifest.model_dump(mode="json")
    return result


def public_distribution_payload(
    cases: list[OperationalDistributionCase],
    *,
    config: OperationalDistributionConfig,
) -> dict[str, Any]:
    payload = base.public_distribution_payload(cases, config=config)
    payload["format"] = "veritas-operational-public-v2"
    payload["manifest"] = distribution_manifest(
        cases, config=config, include_private_hash=False
    ).model_dump(mode="json")
    return payload


def private_oracle_payload(
    cases: list[OperationalDistributionCase],
    *,
    config: OperationalDistributionConfig,
) -> dict[str, Any]:
    payload = base.private_oracle_payload(cases, config=config)
    payload["format"] = "veritas-operational-private-oracles-v2"
    payload["manifest"] = distribution_manifest(
        cases, config=config, include_private_hash=True
    ).model_dump(mode="json")
    return payload


def write_operational_distribution_bundle(
    *,
    output: str | Path,
    oracle_output: str | Path,
    config: OperationalDistributionConfig | None = None,
) -> dict[str, Any]:
    config = config or OperationalDistributionConfig()
    cases = compile_operational_distribution(config)
    validation = validate_operational_distribution(cases, config=config)
    if not validation["valid"]:
        raise ValueError(f"invalid operational distribution: {validation['errors']}")
    public_target = Path(output)
    private_target = Path(oracle_output)
    public_target.parent.mkdir(parents=True, exist_ok=True)
    private_target.parent.mkdir(parents=True, exist_ok=True)
    public_target.write_text(
        json.dumps(
            public_distribution_payload(cases, config=config),
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    private_target.write_text(
        json.dumps(
            private_oracle_payload(cases, config=config),
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    return validation
