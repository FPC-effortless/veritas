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
from investigation_world.observatory.interventions import (
    InterventionMutation,
    InterventionSpec,
)
from investigation_world.observatory.live import (
    CompanyWorldLiveRunConfig,
    run_companyworld_intervention,
)
from investigation_world.observatory.models import ScenarioPool, ScenarioRef


LOCAL_AGENT = r'''
import json
import sys
request = json.load(sys.stdin)
prompt = request["payload"]
if '"history": []' in prompt:
    print(json.dumps({"action": "search", "system": "ERP", "query": "ORD-1"}))
else:
    print(json.dumps({
        "action": "submit",
        "result": {
            "claims": [{
                "object_type": "ORDER",
                "object_id": "ORD-1",
                "field_name": "status",
                "value": "OPEN"
            }],
            "evidence": [{"record_id": "REC-1"}],
            "overall_confidence": 1.0
        }
    }))
'''


def _bundles(tmp_path):
    task = CompanyWorldTask(
        task_id="TASK-1",
        world_id="WORLD-1",
        task_type="STATUS_INVESTIGATION",
        objective="Determine order status.",
        target_object_type="ORDER",
        target_object_id="ORD-1",
        permitted_systems=[CompanySystem.ERP],
        constraints={"budget": 10, "max_tool_calls": 5},
    )
    record = CompanyWorldRecord(
        record_id="REC-1",
        system=CompanySystem.ERP,
        record_type="order_status",
        object_type="ORDER",
        object_id="ORD-1",
        fields={"status": "OPEN"},
        source_file="test/orders.json",
    )
    episode = CompanyWorldEpisode(
        episode_id="EP-1",
        world_id="WORLD-1",
        task=task,
        records=[record],
        oracle=CompanyWorldOracle(
            task_id="TASK-1",
            answer_class="status",
            expected_resolution="OPEN",
            facts=[
                OperationalFactTarget(
                    object_type="ORDER",
                    object_id="ORD-1",
                    field_name="status",
                    expected_value="OPEN",
                    supporting_record_ids=["REC-1"],
                )
            ],
        ),
    )
    public = tmp_path / "public.json"
    oracle = tmp_path / "oracle.json"
    public.write_text(
        json.dumps(
            {
                "format": "veritas-companyworld-test-v1",
                "episodes": [episode.public_payload()],
                "splits": {"public_eval": ["EP-1"]},
            }
        ),
        encoding="utf-8",
    )
    oracle.write_text(
        json.dumps(
            {
                "oracles": [
                    {
                        "episode_id": "EP-1",
                        "world_id": "WORLD-1",
                        "oracle": episode.oracle.model_dump(mode="json"),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return public, oracle


def test_intervention_runner_executes_frozen_ab_arms(tmp_path):
    public, oracle = _bundles(tmp_path)
    config = CompanyWorldLiveRunConfig(
        public_bundle=public,
        oracle_bundle=oracle,
        store_root=tmp_path / "observatory",
        provider="local",
        model_id="deterministic-test-agent",
        model_snapshot="v1",
        time_snapshot="2026-08-26T12:00:00+00:00",
        local_command=[sys.executable, "-c", LOCAL_AGENT],
        local_json_stdin=True,
        split_name="public_eval",
        scenario_limit=1,
        max_agent_steps=3,
        max_attempts=1,
    )
    spec = InterventionSpec(
        name="distractor-pressure",
        scenario=ScenarioRef(
            scenario_id="EP-1",
            task_id="TASK-1",
            seed=1,
            pool=ScenarioPool.ANCHOR,
        ),
        mutations=[
            InterventionMutation(kind=MutationKind.INJECT_DISTRACTOR, seed=22),
            InterventionMutation(kind=MutationKind.REORDER_RECORDS, seed=23),
        ],
    )

    report = run_companyworld_intervention(config, spec)

    assert report.effect.baseline_run_id != report.effect.intervention_run_id
    assert report.materialization.source_world_version != report.materialization.intervention_world_version
    assert report.effect.reward.delta == 0.0
    assert (config.store_root / "interventions" / f"{report.report_id}.json").exists()
