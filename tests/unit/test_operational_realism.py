from investigation_world.foundry.models import DistributionSplit
from investigation_world.operational import (
    ActionKind,
    EpisodeSubmission,
    OperationalDistributionConfig,
    OperationalInvariant,
    OperationalRuntime,
    StateAssertion,
    WorldDomain,
    compile_operational_distribution,
    validate_operational_distribution,
)
from investigation_world.operational.models import ActionEvent, HiddenOracle
from investigation_world.operational.verifier import verify_operational_episode


def _small_distribution():
    config = OperationalDistributionConfig(
        seed=77,
        train_per_domain=2,
        iid_per_domain=1,
        ood_per_domain=1,
        adversarial_per_domain=1,
    )
    return config, compile_operational_distribution(config)


def test_deep_distribution_preserves_scale_contract_with_realism():
    config, cases = _small_distribution()
    validation = validate_operational_distribution(cases, config=config)
    assert validation["valid"] is True, validation["errors"]
    assert len(cases) == config.total_cases
    assert {case.episode.task.domain for case in cases} == set(WorldDomain)
    for case in cases:
        episode = case.episode
        assert episode.metadata["realism_profile"] == "domain_native_operational_v2"
        assert episode.task.metadata["stateful_preconditions"] is True
        assert len(episode.records) >= 8
        assert len(episode.task.available_actions) >= 5
        assert len(episode.oracle.required_action_order) >= 5
        assert any(effect.required_state for effect in episode.oracle.action_effects)
        assert any(invariant.scope == "always" for invariant in episode.oracle.invariants)
        assert all("-deep-" not in record.record_id for record in episode.records)
        assert case.difficulty.dependency_depth >= 5


def test_financial_repair_is_blocked_until_diagnostic_preconditions_are_met():
    config, cases = _small_distribution()
    case = next(
        case
        for case in cases
        if case.episode.task.domain == WorldDomain.FINANCIAL_SPREADSHEET
        and case.split == DistributionSplit.TRAIN
    )
    episode = case.episode
    runtime = OperationalRuntime(episode)
    effects = {effect.action_name: effect for effect in episode.oracle.action_effects}

    repair = effects["repair_formula"]
    blocked = runtime.act("repair_formula", **repair.required_parameters)
    assert blocked["accepted"] is False
    assert runtime.trace()[-1]["blocked"] is True
    assert runtime.trace()[-1]["effect_applied"] is False

    inspect = effects["inspect_formula_lineage"]
    reconcile = effects["reconcile_source_balance"]
    recalc = effects["recalculate_model"]
    validate = effects["validate_model_controls"]
    runtime.act("inspect_formula_lineage", **inspect.required_parameters)
    runtime.act("reconcile_source_balance", **reconcile.required_parameters)
    runtime.act("repair_formula", **repair.required_parameters)
    runtime.act("recalculate_model", **recalc.required_parameters)
    runtime.act("validate_model_controls", **validate.required_parameters)

    result = runtime.submit(
        EpisodeSubmission(
            conclusion="Model lineage, source reconciliation, repair, recalculation and controls completed.",
            evidence_ids=list(episode.oracle.required_evidence_ids),
            confidence=0.99,
        )
    )
    assert result.outcome == 1.0
    assert result.state == 1.0
    assert result.process == 1.0
    assert result.constraints == 1.0


def test_temporal_invariant_detects_transient_damage_even_if_final_state_is_repaired():
    oracle = HiddenOracle(
        task_id="temporal-invariant-test",
        initial_state={"asset.integrity": True},
        invariants=[
            OperationalInvariant(
                invariant_id="asset-integrity-always",
                description="Asset integrity must remain true throughout execution.",
                assertion=StateAssertion(
                    object_id="asset",
                    field_name="integrity",
                    expected_value=True,
                ),
                severity="critical",
                scope="always",
            )
        ],
    )
    events = [
        ActionEvent(
            sequence=1,
            action_name="damage",
            kind=ActionKind.WRITE,
            system="TEST",
            state_changes={"asset.integrity": False},
        ),
        ActionEvent(
            sequence=2,
            action_name="repair",
            kind=ActionKind.WRITE,
            system="TEST",
            state_changes={"asset.integrity": True},
        ),
    ]
    result = verify_operational_episode(
        oracle=oracle,
        state={"asset.integrity": True},
        events=events,
        submission=EpisodeSubmission(),
        tool_calls=2,
        cost_spent=2,
    )
    assert "asset-integrity-always" in result.invariant_violations
    assert result.constraints < 0.5


def test_blocked_required_action_does_not_satisfy_process_verifier():
    oracle = HiddenOracle(
        task_id="blocked-process-test",
        initial_state={},
        required_actions=["approve"],
        required_action_order=["approve"],
    )
    event = ActionEvent(
        sequence=1,
        action_name="approve",
        kind=ActionKind.WRITE,
        system="TEST",
        effect_applied=False,
        blocked=True,
        blocked_reason="state:approval.ready",
    )
    result = verify_operational_episode(
        oracle=oracle,
        state={},
        events=[event],
        submission=EpisodeSubmission(),
        tool_calls=1,
        cost_spent=1,
    )
    assert result.process == 0.0
    assert result.missing_required_actions == ["approve"]
    assert "blocked_required:approve" in result.process_violations
