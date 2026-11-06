from __future__ import annotations

from investigation_world.foundry.capability_families import (
    external_investigation_capability_contract,
)
from investigation_world.foundry.external_distribution import (
    ExternalInvestigationBuildPlan,
    ExternalInvestigationWorldSpec,
    materialize_external_investigation_build_plan,
)
from investigation_world.foundry.models import DistributionSplit
from investigation_world.foundry.training_corpus import (
    generate_training_demonstration_set,
)
from investigation_world.world.generator import WorldGenerationConfig


_SEARCH_EVENTS = {
    "web_search",
    "document_search",
    "registry_search",
    "filing_search",
    "archive_search",
}


def test_training_expert_opens_only_observed_or_explicit_documents() -> None:
    distribution = materialize_external_investigation_build_plan(
        ExternalInvestigationBuildPlan(
            distribution_id="observable-expert-test",
            worlds=[
                ExternalInvestigationWorldSpec(
                    split=DistributionSplit.TRAIN,
                    world_seed=71_001,
                    evidence_seed=71_101,
                    task_seed=71_201,
                    task_count=6,
                    config=WorldGenerationConfig(
                        num_people=24,
                        num_organizations=12,
                        num_addresses=12,
                        relationship_density=0.12,
                        alias_rate=0.35,
                        rename_rate=0.20,
                        ownership_chain_depth=3,
                    ),
                )
            ],
        )
    )
    demonstrations = generate_training_demonstration_set(
        distribution.episodes,
        capability_contract_id=external_investigation_capability_contract().capability_id,
        expert_threshold=0.70,
        include_counterfactuals=False,
    )

    assert demonstrations.metadata["observation_complete_reference_policy"] == (
        "oracle-observable-expert-v1"
    )
    for trajectory in demonstrations.trajectories:
        observed: set[str] = set()
        public_task = trajectory.annotations["public_task"]
        explicitly_supplied = set(public_task.get("target_refs", []))
        for event in trajectory.trace.events:
            if event.event_type in _SEARCH_EVENTS:
                results = event.payload.get("result", [])
                if isinstance(results, list):
                    for result in results:
                        if isinstance(result, dict) and result.get("document_id"):
                            observed.add(str(result["document_id"]))
            elif event.event_type == "open_document":
                args = event.payload.get("args", [])
                assert args
                document_id = str(args[0])
                assert document_id in observed or document_id in explicitly_supplied
