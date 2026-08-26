from __future__ import annotations

import json
import sys

from investigation_world.companyworld.models import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    OperationalFactTarget,
)
from investigation_world.foundry.models import MutationKind
from investigation_world.observatory.intervention_suite import run_companyworld_intervention_suite
from investigation_world.observatory.interventions import InterventionMutation, InterventionSpec
from investigation_world.observatory.live import CompanyWorldLiveRunConfig
from investigation_world.observatory.models import ScenarioPool, ScenarioRef


SUITE_AGENT = r'''
import json
import sys
request = json.load(sys.stdin)
prompt = request["payload"]
order = "ORD-2" if "ORD-2" in prompt else "ORD-1"
record = "REC-2" if order == "ORD-2" else "REC-1"
if '"history": []' in prompt:
    print(json.dumps({"action": "search", "system": "ERP", "query": order}))
else:
    print(json.dumps({
        "action": "submit",
        "result": {
            "claims": [{
                "object_type": "ORDER",
                "object_id": order,
                "field_name": "status",
                "value": "OPEN"
            }],
            "evidence": [{"record_id": record}],
            "overall_confidence": 1.0
        }
    }))
'''


def _episode(index: int) -> CompanyWorldEpisode:
    order_id = f"ORD-{index}"
    record_id = f"REC-{index}"
    task_id = f"TASK-{index}"
    episode_id = f"EP-{index}"
    task = CompanyWorldTask(
        task_id=task_id,
        world_id="WORLD-1",
        task_type="STATUS_INVESTIGATION",
        objective=f"Determine verified status of {order_id}.",
        target_object_type="ORDER",
        target_object_id=order_id,
        permitted_systems=[CompanySystem.ERP],
        constraints={"budget": 10, "max_tool_calls": 5},
    )
    record = CompanyWorldRecord(
        record_id=record_id,
        system=CompanySystem.ERP,
        record_type="order_status",
        object_type="ORDER",
        object_id=order_id,
        fields={"status": "OPEN"},
        source_file=f"orders-{index}.json",
    )
    return CompanyWorldEpisode(
        episode_id=episode_id,
        world_id="WORLD-1",
        task=task,
        records=[record],
        oracle=CompanyWorldOracle(
            task_id=task_id,
            answer_class="status",
            expected_resolution="OPEN",
            facts=[
                OperationalFactTarget(
                    object_type="ORDER",
                    object_id=order_id,
                    field_name="status",
                    expected_value="OPEN",
                    supporting_record_ids=[record_id],
                )
            ],
        ),
    )


def _bundles(tmp_path):
    episodes = [_episode(1), _episode(2)]
    public = tmp_path / "public.json"
    oracle = tmp_path / "oracle.json"
    public.write_text(
        json.dumps(
            {
                "format": "veritas-companyworld-suite-test-v1",
                "episodes": [episode.public_payload() for episode in episodes],
                "splits": {"public_eval": [episode.episode_id for episode in episodes]},
            }
        ),
        encoding="utf-8",
    )
    oracle.write_text(
        json.dumps(
            {
                "oracles": [
                    {
                        "episode_id": episode.episode_id,
                        "world_id": episode.world_id,
                        "oracle": episode.oracle.model_dump(mode="json"),
                    }
                    for episode in episodes
                ]
            }
        ),
        encoding="utf-8",
    )
    return public, oracle


def test_intervention_suite_aggregates_paired_effects_across_scenarios(tmp_path):
    public, oracle = _bundles(tmp_path)
    config = CompanyWorldLiveRunConfig(
        public_bundle=public,
        oracle_bundle=oracle,
        store_root=tmp_path / "observatory",
        provider="local",
        model_id="suite-test-agent",
        model_snapshot="v1",
        time_snapshot="2026-08-26T12:00:00+00:00",
        local_command=[sys.executable, "-c", SUITE_AGENT],
        local_json_stdin=True,
        split_name="public_eval",
        max_agent_steps=3,
        max_attempts=1,
    )
    specs = [
        InterventionSpec(
            name="distractor-pressure",
            scenario=ScenarioRef(
                scenario_id=f"EP-{index}",
                task_id=f"TASK-{index}",
                seed=100 + index,
                pool=ScenarioPool.ANCHOR,
            ),
            mutations=[
                InterventionMutation(
                    kind=MutationKind.INJECT_DISTRACTOR,
                    seed=900 + index,
                    parameters={"note": "irrelevant record"},
                )
            ],
        )
        for index in (1, 2)
    ]

    suite = run_companyworld_intervention_suite(config, specs)

    assert suite.aggregate.reward.n == 2
    assert suite.aggregate.reward.mean == 0.0
    assert len(suite.intervention_report_ids) == 2
    assert (
        config.store_root / "intervention_suites" / f"{suite.suite_id}.json"
    ).exists()
