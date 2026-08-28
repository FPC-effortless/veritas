from __future__ import annotations

from typer.testing import CliRunner

from investigation_world.operational.env_cli import env_app


runner = CliRunner()


def test_compile_delegates_exactly_to_portability_cli(monkeypatch) -> None:
    captured: list[tuple[str, ...]] = []

    def fake_main(arguments):
        captured.append(tuple(arguments))
        return 0

    monkeypatch.setattr("investigation_world.operational.env_cli.portability_main", fake_main)

    result = runner.invoke(
        env_app,
        [
            "compile",
            "--episode",
            "episode.json",
            "--output",
            "contract.json",
            "--public-output",
            "public.json",
        ],
    )

    assert result.exit_code == 0
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

    result = runner.invoke(
        env_app,
        [
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
        ],
    )

    assert result.exit_code == 0
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

    result = runner.invoke(
        env_app,
        [
            "reverify",
            "--trajectory",
            "trace.jsonl",
            "--contract",
            "contract.json",
            "--include-operator-metadata",
        ],
    )

    assert result.exit_code == 0
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

    result = runner.invoke(env_app, ["validate", "--contract", "bad.json"])

    assert result.exit_code == 2


def test_help_exposes_only_supported_unified_environment_commands() -> None:
    result = runner.invoke(env_app, ["--help"])

    assert result.exit_code == 0
    for command in (
        "compile",
        "inspect",
        "validate",
        "run",
        "export",
        "conformance",
        "reverify",
    ):
        assert command in result.stdout
