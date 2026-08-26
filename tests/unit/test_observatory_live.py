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
from investigation_world.observatory.companyworld import CompanyWorldBundleRepository
from investigation_world.observatory.live import (
    CompanyWorldLiveRunConfig,
    run_companyworld_observation,
)
from investigation_world.observatory.providers import OpenAIResponsesProvider
from investigation_world.observatory.execution import ModelRequest
from investigation_world.observatory.models import ModelSpec


def _episode() -> CompanyWorldEpisode:
    task = CompanyWorldTask(
        task_id="TASK-1",
        world_id="WORLD-1",
        task_type="STATUS_INVESTIGATION",
        objective="Determine the verified status of order ORD-1.",
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
    oracle = CompanyWorldOracle(
        task_id=task.task_id,
        answer_class="status",
        expected_resolution="OPEN",
        facts=[
            OperationalFactTarget(
                object_type="ORDER",
                object_id="ORD-1",
                field_name="status",
                expected_value="OPEN",
                supporting_record_ids=[record.record_id],
            )
        ],
    )
    return CompanyWorldEpisode(
        episode_id="EP-1",
        world_id="WORLD-1",
        task=task,
        records=[record],
        oracle=oracle,
    )


def _write_bundle(tmp_path):
    episode = _episode()
    public = tmp_path / "public.json"
    oracle = tmp_path / "oracle.json"
    public.write_text(
        json.dumps(
            {
                "format": "veritas-companyworld-test-v1",
                "episodes": [episode.public_payload()],
                "splits": {"public_eval": [episode.episode_id]},
            },
            default=str,
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
                ]
            },
            default=str,
        ),
        encoding="utf-8",
    )
    return public, oracle


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


def test_bundle_repository_fingerprints_and_selects_scenarios(tmp_path):
    public, oracle = _write_bundle(tmp_path)
    repository = CompanyWorldBundleRepository.from_files(public, oracle)

    refs = repository.scenario_refs(split_name="public_eval")

    assert repository.world_id == "WORLD-1"
    assert repository.bundle_version.startswith("CW-")
    assert len(refs) == 1
    assert refs[0].scenario_id == "EP-1"
    assert refs[0].task_id == "TASK-1"


def test_live_subprocess_cycle_executes_and_then_reports_drift(tmp_path):
    public, oracle = _write_bundle(tmp_path)
    store = tmp_path / "observatory"
    base = dict(
        public_bundle=public,
        oracle_bundle=oracle,
        store_root=store,
        provider="local",
        model_id="deterministic-test-agent",
        model_snapshot="v1",
        local_command=[sys.executable, "-c", LOCAL_AGENT],
        local_json_stdin=True,
        split_name="public_eval",
        scenario_limit=1,
        max_agent_steps=3,
        max_attempts=1,
    )

    first = run_companyworld_observation(
        CompanyWorldLiveRunConfig(**base, time_snapshot="2026-08-19T00:00:00+00:00")
    )
    second = run_companyworld_observation(
        CompanyWorldLiveRunConfig(**base, time_snapshot="2026-08-26T00:00:00+00:00")
    )

    assert first.scheduler.succeeded == 1
    assert first.scheduler.failed == 0
    assert first.aggregates[0].reward.mean > 0.9
    assert first.drift == []
    assert second.scheduler.succeeded == 1
    assert len(second.drift) == 1
    assert second.drift[0].regressions == []
    assert (store / "runs.jsonl").exists()
    assert len(list((store / "cycles").glob("CYCLE-*.json"))) == 2


def test_openai_provider_forces_store_false(monkeypatch):
    import investigation_world.observatory.providers as providers

    captured = {}

    def fake_post(url, payload, *, headers, timeout_s):
        captured.update({"url": url, "payload": payload, "headers": headers})
        return (
            {
                "id": "resp-1",
                "status": "completed",
                "model": "test-model",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            },
            0.01,
        )

    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setattr(providers, "_json_post", fake_post)
    adapter = OpenAIResponsesProvider()
    request = ModelRequest(
        request_id="REQ-1",
        cell_id="CELL-1",
        call_index=0,
        model=ModelSpec(
            provider="openai",
            model_id="test-model",
            config={"provider_parameters": {"store": True}},
        ),
        payload="hello",
        parameters={"store": True},
    )

    response = adapter.invoke(request)

    assert response.output == "ok"
    assert response.usage.total_tokens == 5
    assert captured["payload"]["store"] is False
    assert captured["headers"]["Authorization"] == "Bearer secret"
