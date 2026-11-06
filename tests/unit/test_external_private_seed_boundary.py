from __future__ import annotations

import json

from investigation_world.foundry import (
    DistributionSplit,
    ExternalInvestigationBuildPlan,
    ExternalInvestigationWorldSpec,
    materialize_external_investigation_build_plan,
)
from investigation_world.world.generator import WorldGenerationConfig


def _distribution():
    spec = ExternalInvestigationWorldSpec(
        split=DistributionSplit.TRAIN,
        world_seed=987_654_321,
        evidence_seed=876_543_219,
        task_seed=765_432_198,
        task_count=2,
        config=WorldGenerationConfig(
            num_people=18,
            num_organizations=8,
            num_addresses=8,
            relationship_density=0.10,
            alias_rate=0.25,
            rename_rate=0.10,
            ownership_chain_depth=2,
        ),
    )
    return materialize_external_investigation_build_plan(
        ExternalInvestigationBuildPlan(
            distribution_id="private-seed-boundary-test",
            worlds=[spec],
        )
    )


def test_public_distribution_does_not_serialize_replayable_seed_material() -> None:
    distribution = _distribution()
    public = distribution.public_payload()
    public_text = json.dumps(public, sort_keys=True).casefold()

    assert '"world_seed"' not in public_text
    assert '"evidence_seed"' not in public_text
    assert '"task_seed"' not in public_text
    assert '"seeds"' not in public_text
    assert '"plan_hash"' not in public_text
    assert "987654321" not in public_text
    assert "876543219" not in public_text
    assert "765432198" not in public_text
    assert "world-987654321" not in public_text
    assert public["worlds"][0]["world_id"].startswith("EXT-")
    assert public["public_manifest_hash"]


def test_agent_episode_payload_redacts_task_and_foundry_generation_seeds() -> None:
    distribution = _distribution()
    payload = distribution.episodes[0].public_payload()
    text = json.dumps(payload, sort_keys=True).casefold()

    assert '"generator_seed"' not in text
    assert '"generator_parameters"' not in text
    assert '"world_seed"' not in text
    assert '"evidence_seed"' not in text
    assert '"task_seed"' not in text
    assert '"seed"' not in payload["foundry"]
    assert payload["task"]["world_id"].startswith("EXT-")


def test_private_bundle_retains_seed_provenance_for_replay() -> None:
    distribution = _distribution()
    private = distribution.private_payload()
    summary = private["world_summaries"][0]

    assert summary["world_seed"] == 987_654_321
    assert summary["evidence_seed"] == 876_543_219
    assert summary["task_seed"] == 765_432_198
    assert private["plan_hash"]
    assert private["manifest"]["partitions"][0]["seeds"]
