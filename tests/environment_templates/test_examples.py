from __future__ import annotations

from pathlib import Path

import pytest
from examples.environments import veritas_environment_examples as examples
from examples.environments.veritas_environment_examples import (
    authority_sensitive,
    long_horizon_budgeted,
    sealed_private_evaluator,
)

from investigation_world.experience import ExperienceMaturity
from investigation_world.operational import EpisodeSubmission, OperationalRuntime

EXAMPLE_ROOT = Path(__file__).parents[2] / "examples" / "environments"


def test_operational_examples_execute_with_perfect_canonical_verification() -> None:
    runners = (
        examples.run_minimal_typed_tool,
        examples.run_file_backed,
        examples.run_sql_backed,
        examples.run_network_api_backed,
        examples.run_native_artifact_backed,
        examples.run_hierarchical_observation,
        examples.run_structured_grader,
        examples.run_authority_sensitive,
        examples.run_long_horizon_budgeted,
    )

    for runner in runners:
        first = runner()
        second = runner()
        assert first.overall_reward == 1.0
        assert second.model_dump(mode="json") == first.model_dump(mode="json")


def test_authority_sensitive_example_fails_closed_without_delegation() -> None:
    runtime = OperationalRuntime(authority_sensitive.build_environment())

    outcome = runtime.act("apply_change", change_id="CHANGE-1")
    result = runtime.submit(
        EpisodeSubmission(
            conclusion="The change was not authorized.",
            claimed_state={
                "CHANGE-1.authority_granted": False,
                "CHANGE-1.applied": False,
                "CHANGE-1.override_used": False,
            },
            evidence_ids=["authority-policy-001"],
            confidence=1.0,
        )
    )

    assert outcome == {
        "action": "apply_change",
        "system": "CHANGE_CONTROL",
        "submitted": True,
        "accepted": False,
        "reason": "authority_required",
    }
    assert result.overall_reward < 1.0


def test_long_horizon_example_enforces_declared_budget() -> None:
    assert examples.run_long_horizon_budgeted().overall_reward == 1.0

    with pytest.raises(ValueError, match="investigation budget exhausted"):
        long_horizon_budgeted.budget_falsifier_raises()


def test_sealed_evaluator_material_is_runtime_supplied_and_not_public() -> None:
    private_choice = "runtime-only-evaluator-choice-7f3a"
    episode = sealed_private_evaluator.build_environment(
        private_expected_choice=private_choice
    )

    public_payload = repr(episode.public_payload())
    source_path = (
        EXAMPLE_ROOT
        / "veritas_environment_examples"
        / "sealed_private_evaluator.py"
    )
    assert private_choice not in public_payload
    assert private_choice not in source_path.read_text(encoding="utf-8")

    result = examples.run_sealed_private_evaluator(
        private_expected_choice=private_choice
    )
    assert result.overall_reward == 1.0

    outcome, failed = sealed_private_evaluator.wrong_choice_fails(
        private_expected_choice=private_choice
    )
    assert outcome["accepted"] is False
    assert failed.overall_reward < 1.0


def test_machine_experience_example_uses_merged_canonical_adapter_without_overclaim() -> None:
    first = examples.run_machine_experience_ready()
    second = examples.run_machine_experience_ready()

    assert first.maturity is ExperienceMaturity.E0_TRACEABLE
    assert first.trajectory.original_evaluation.reward == 1.0
    assert first.experience_id.startswith("EXP-")
    assert second.experience_id == first.experience_id
    assert second.trajectory.trajectory_id == first.trajectory.trajectory_id
    assert "HiddenOracle" not in repr(first.public_payload())


def test_examples_package_has_installable_metadata_and_complete_template_docs() -> None:
    pyproject = (EXAMPLE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = (EXAMPLE_ROOT / "README.md").read_text(encoding="utf-8")

    assert 'name = "veritas-environment-examples"' in pyproject
    assert "authority_sensitive" in readme
    assert "long_horizon_budgeted" in readme
    assert "sealed_private_evaluator" in readme
    assert "machine_experience_ready" in readme
    assert "PR #149" in readme
    assert "E0_TRACEABLE" in readme
