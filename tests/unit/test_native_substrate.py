from __future__ import annotations

import pytest
from openpyxl import load_workbook

from investigation_world.operational import (
    EpisodeSubmission,
    NativeOperationalRuntime,
    OperationalDistributionConfig,
    WorldDomain,
    compile_operational_distribution,
)
from investigation_world.operational.substrate import PersistentOperationalSubstrate


@pytest.fixture(scope="module")
def episodes():
    config = OperationalDistributionConfig(
        seed=73,
        train_per_domain=1,
        iid_per_domain=1,
        ood_per_domain=1,
        adversarial_per_domain=1,
    )
    return {
        case.episode.task.domain: case.episode
        for case in compile_operational_distribution(config)
        if case.split.value == "train"
    }


def _execute(runtime):
    oracle = runtime.episode.oracle
    for action in oracle.required_action_order:
        effects = [effect for effect in oracle.action_effects if effect.action_name == action]
        for ordinal in range(oracle.required_action_counts.get(action, 1)):
            runtime.act(action, **effects[min(ordinal, len(effects) - 1)].required_parameters)
    return EpisodeSubmission(
        conclusion="Native artifact checked",
        evidence_ids=oracle.required_evidence_ids,
    )


@pytest.mark.parametrize("domain", list(WorldDomain))
def test_native_submission_persists_verifier_checks_without_agent_actions(
    episodes, tmp_path, domain
):
    standalone = NativeOperationalRuntime(
        episodes[domain].model_copy(deep=True),
        artifact_root=tmp_path / "standalone",
    )
    substrate = PersistentOperationalSubstrate()
    persistent = NativeOperationalRuntime(
        episodes[domain].model_copy(deep=True),
        artifact_root=tmp_path / "persistent",
        substrate=substrate,
    )
    expected = standalone.submit(_execute(standalone))
    submission = _execute(persistent)
    events = persistent.trace()
    budget = persistent.budget_snapshot()
    before_sequence = substrate.sequence
    actual = persistent.submit(submission)

    assert persistent.last_artifact_verification.valid
    assert actual == expected
    assert actual.state == actual.outcome == 1.0
    checks = {
        f"native_artifact.{key}": value
        for key, value in persistent.last_artifact_verification.checks.items()
    }
    assert all(substrate.state[key] == value for key, value in checks.items())
    assert substrate.sequence == before_sequence + 1
    assert substrate.history()[-1].actor == "verifier"
    assert substrate.history()[-1].changes == checks
    assert substrate.state_at(substrate.sequence) == persistent.state_snapshot()
    assert substrate.validate_integrity()
    assert persistent.trace() == events
    assert persistent.budget_snapshot() == budget
    final_state = persistent.state_snapshot()
    with pytest.raises(ValueError, match="already submitted"):
        persistent.submit(submission)
    assert substrate.sequence == before_sequence + 1
    assert persistent.state_snapshot() == final_state


def test_tampered_artifact_is_rejected_with_and_without_substrate(episodes, tmp_path):
    scores = []
    for persistent in (False, True):
        substrate = PersistentOperationalSubstrate() if persistent else None
        runtime = NativeOperationalRuntime(
            episodes[WorldDomain.FINANCIAL_SPREADSHEET].model_copy(deep=True),
            artifact_root=tmp_path / str(persistent),
            substrate=substrate,
        )
        submission = _execute(runtime)
        path = runtime.materialize_artifact()
        workbook = load_workbook(path)
        target = next(a for a in runtime.episode.oracle.target_state if a.field_name == "formula")
        sheet, cell = target.object_id.split("!")
        workbook[sheet][cell] = "=0"
        workbook.save(path)
        result = runtime.submit(submission)
        assert not runtime.last_artifact_verification.valid
        assert result.state < 1.0 and result.outcome < 1.0
        assert "native_artifact:target_formula_present" in result.process_violations
        assert runtime.state_snapshot()["native_artifact.target_formula_present"] is False
        scores.append(result)
        if substrate is not None:
            assert substrate.validate_integrity()
    assert scores[0] == scores[1]
