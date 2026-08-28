from __future__ import annotations

from pathlib import Path

import pytest

from investigation_world.operational.env_cli import (
    EnvironmentAdapter,
    compile_environment_cmd,
    env_app,
    export_environment_cmd,
    reverify_environment_cmd,
    validate_environment_cmd,
)


def test_compile_delegates_exactly_to_portability_cli(monkeypatch) -> None:
    captured: list[tuple[str, ...]] = []

    def fake_main(arguments):
        captured.append(tuple(arguments))
        return 0

    monkeypatch.setattr("investigation_world.operational.env_cli.portability_main", fake_main)

    compile_environment_cmd(
        episode=Path("episode.json"),
        output=Path("contract.json"),
        public_output=Path("public.json"),
    )

    assert captured == [
        (
            "compile",
            "--episode",
            "episode.json",
            "--output",
            "contract.json",
            "--public-output",
            "public.json",
        )
    ]


def test_export_delegates_adapter_and_optional_runtime_fields(monkeypatch) -> None:
    captured: list[tuple[str, ...]] = []

    def fake_main(arguments):
        captured.append(tuple(arguments))
        return 0

    monkeypatch.setattr("investigation_world.operational.env_cli.portability_main", fake_main)

    export_environment_cmd(
        adapter=EnvironmentAdapter.HARBOR,
        contract=Path("contract.json"),
        output=Path("harbor-package"),
        seed=17,
        veritas_requirement=None,
        task_name="supplier-approval",
        agent_image=None,
        runtime_image="runtime:sha256",
        verifier_image="verifier:sha256",
    )

    assert captured == [
        (
            "export",
            "--adapter",
            "harbor",
            "--contract",
            "contract.json",
            "--output",
            "harbor-package",
            "--seed",
            "17",
            "--task-name",
            "supplier-approval",
            "--runtime-image",
            "runtime:sha256",
            "--verifier-image",
            "verifier:sha256",
        )
    ]


def test_reverify_uses_existing_trajectory_replay_command(monkeypatch) -> None:
    captured: list[tuple[str, ...]] = []

    def fake_main(arguments):
        captured.append(tuple(arguments))
        return 0

    monkeypatch.setattr("investigation_world.operational.env_cli.portability_main", fake_main)

    reverify_environment_cmd(
        trajectory=Path("trace.jsonl"),
        contract=Path("contract.json"),
        include_private_identities=False,
        include_operator_metadata=True,
    )

    assert captured == [
        (
            "trajectory",
            "--trajectory",
            "trace.jsonl",
            "--contract",
            "contract.json",
            "--reverify",
            "--include-operator-metadata",
        )
    ]


def test_nonzero_portability_exit_is_preserved(monkeypatch) -> None:
    def fake_main(arguments):
        assert tuple(arguments) == ("validate-partition", "--contract", "bad.json")
        return 2

    monkeypatch.setattr("investigation_world.operational.env_cli.portability_main", fake_main)

    with pytest.raises(BaseException) as exc_info:
        validate_environment_cmd(contract=Path("bad.json"))

    assert getattr(exc_info.value, "exit_code", None) == 2


def test_command_registry_exposes_only_supported_unified_environment_commands() -> None:
    commands = {command.name for command in env_app.registered_commands}

    assert commands == {
        "compile",
        "inspect",
        "validate",
        "run",
        "export",
        "conformance",
        "reverify",
    }
