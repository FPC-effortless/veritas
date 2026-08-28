from __future__ import annotations

from pathlib import Path

from examples.environments import veritas_environment_examples as examples

EXAMPLE_ROOT = Path(__file__).parents[2] / "examples" / "environments"


def test_all_dependency_ready_examples_execute_with_perfect_canonical_verification() -> None:
    runners = (
        examples.run_minimal_typed_tool,
        examples.run_file_backed,
        examples.run_sql_backed,
        examples.run_network_api_backed,
        examples.run_native_artifact_backed,
        examples.run_hierarchical_observation,
        examples.run_structured_grader,
    )

    for runner in runners:
        first = runner()
        second = runner()
        assert first.overall_reward == 1.0
        assert second.model_dump(mode="json") == first.model_dump(mode="json")


def test_examples_package_has_installable_metadata_and_no_machine_experience_dependency() -> None:
    pyproject = (EXAMPLE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = (EXAMPLE_ROOT / "README.md").read_text(encoding="utf-8")

    assert 'name = "veritas-environment-examples"' in pyproject
    assert "MachineExperience" in readme
    assert "PR #149" in readme
