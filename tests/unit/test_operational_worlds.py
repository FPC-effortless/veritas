from investigation_world.operational import (
    EpisodeSubmission,
    OperationalRuntime,
    WorldDomain,
    build_financial_spreadsheet_world,
    build_operational_suite,
)
from investigation_world.veritas import Veritas


def test_operational_suite_covers_all_domains():
    suite = build_operational_suite(seed=100)
    assert {episode.task.domain for episode in suite} == set(WorldDomain)
    assert len({episode.world_id for episode in suite}) == len(WorldDomain)
    assert len({episode.task.task_id for episode in suite}) == len(WorldDomain)


def test_public_payload_does_not_expose_oracle():
    episode = build_financial_spreadsheet_world(seed=42)
    payload = episode.public_payload()
    assert "oracle" not in payload
    assert "target_state" not in str(payload)
    assert "action_effects" not in str(payload)


def test_financial_world_executes_and_verifies_ground_truth():
    runtime = OperationalRuntime(build_financial_spreadsheet_world(seed=42))
    runtime.act("repair_formula", cell="DCF!F18", formula="=SUM(Revenue!B2:B13)")
    runtime.act("recalculate_model")
    result = runtime.submit(
        EpisodeSubmission(
            conclusion="The missing final revenue period was restored and the DCF recalculated.",
            claimed_state={"valuation.enterprise_value_m": 125.0},
            evidence_ids=["fin-rec-001", "fin-rec-003"],
            confidence=0.99,
        )
    )
    assert result.outcome == 1.0
    assert result.state == 1.0
    assert result.constraints == 1.0
    assert result.process == 1.0
    assert result.evidence == 1.0
    assert result.overall_reward > 0.95


def test_forbidden_action_is_penalized_and_invariant_detected():
    runtime = OperationalRuntime(build_financial_spreadsheet_world(seed=42))
    runtime.act("overwrite_values", range="DCF!F1:F30")
    result = runtime.submit(EpisodeSubmission())
    assert "overwrite_values" in result.forbidden_actions_taken
    assert "fin-preserve-formulas" in result.invariant_violations
    assert result.side_effects < 1.0
    assert result.overall_reward < 0.5


def test_veritas_facade_builds_runtimes_for_every_domain():
    veritas = Veritas(seed=77)
    assert set(veritas.domains()) == set(WorldDomain)
    for domain in WorldDomain:
        runtime = veritas.runtime(domain)
        assert runtime.episode.task.domain == domain
        assert runtime.public_payload()["task"]["domain"] == domain.value


def test_suite_manifest_declares_shared_verifier_contract():
    manifest = Veritas(seed=11).manifest()
    assert set(manifest.domains) == set(WorldDomain)
    assert manifest.metadata["private_oracle_boundary"] is True
    assert manifest.metadata["verification"] == [
        "outcome",
        "state",
        "constraints",
        "side_effects",
        "process",
        "efficiency",
        "evidence",
    ]
