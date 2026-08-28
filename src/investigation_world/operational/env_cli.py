from __future__ import annotations

import enum
import pathlib
import typer


env_app = typer.Typer(
    help="Unified environment compile, validation, execution, export, and replay commands.",
    no_args_is_help=True,
)


class EnvironmentAdapter(enum.StrEnum):
    NEMO = "nemo"
    OPENENV = "openenv"
    HUD = "hud"
    PRIME = "prime"
    HARBOR = "harbor"


def _portability_main(arguments: list[str] | tuple[str, ...]) -> int:
    module = __import__("investigation_world.world_portability", fromlist=("main",))
    entrypoint = getattr(module, "main")
    return int(entrypoint(tuple(arguments)))


def _run_portability(arguments: list[str] | tuple[str, ...]) -> None:
    """Delegate to the canonical portability CLI and preserve its exit status."""

    exit_code = _portability_main(arguments)
    if exit_code:
        raise typer.Exit(exit_code)


def _append_optional_path(
    arguments: list[str],
    flag: str,
    value: pathlib.Path | None,
) -> None:
    if value is not None:
        arguments.extend((flag, str(value)))


def _append_optional_text(arguments: list[str], flag: str, value: str | None) -> None:
    if value is not None:
        arguments.extend((flag, value))


@env_app.command("compile")
def compile_environment_cmd(
    episode: pathlib.Path = typer.Option(..., "--episode"),
    output: pathlib.Path = typer.Option(..., "--output"),
    public_output: pathlib.Path | None = typer.Option(None, "--public-output"),
) -> None:
    """Compile a canonical OperationalEpisode into a portable operational contract."""

    arguments = ["compile", "--episode", str(episode), "--output", str(output)]
    _append_optional_path(arguments, "--public-output", public_output)
    _run_portability(arguments)


@env_app.command("inspect")
def inspect_environment_cmd(
    contract: pathlib.Path = typer.Option(..., "--contract"),
    include_private_identities: bool = typer.Option(
        False,
        "--include-private-identities",
    ),
) -> None:
    """Inspect a portable contract without exposing evaluator-private state."""

    arguments = ["inspect", "--contract", str(contract)]
    if include_private_identities:
        arguments.append("--include-private-identities")
    _run_portability(arguments)


@env_app.command("validate")
def validate_environment_cmd(
    contract: pathlib.Path = typer.Option(..., "--contract"),
) -> None:
    """Validate the public/evaluator-private contract partition."""

    _run_portability(("validate-partition", "--contract", str(contract)))


@env_app.command("run")
def run_environment_cmd(
    contract: pathlib.Path = typer.Option(..., "--contract"),
    vector: pathlib.Path | None = typer.Option(None, "--vector"),
    seed: int | None = typer.Option(None, "--seed"),
    include_operator_metadata: bool = typer.Option(
        False,
        "--include-operator-metadata",
    ),
) -> None:
    """Run the canonical portable operational runtime."""

    arguments = ["run", "--contract", str(contract)]
    _append_optional_path(arguments, "--vector", vector)
    if seed is not None:
        arguments.extend(("--seed", str(seed)))
    if include_operator_metadata:
        arguments.append("--include-operator-metadata")
    _run_portability(arguments)


@env_app.command("export")
def export_environment_cmd(
    adapter: EnvironmentAdapter = typer.Option(..., "--adapter"),
    contract: pathlib.Path = typer.Option(..., "--contract"),
    output: pathlib.Path = typer.Option(..., "--output"),
    seed: int = typer.Option(0, "--seed"),
    veritas_requirement: str | None = typer.Option(None, "--veritas-requirement"),
    task_name: str | None = typer.Option(None, "--task-name"),
    agent_image: str | None = typer.Option(None, "--agent-image"),
    runtime_image: str | None = typer.Option(None, "--runtime-image"),
    verifier_image: str | None = typer.Option(None, "--verifier-image"),
) -> None:
    """Export one portable contract through an existing runtime adapter."""

    arguments = [
        "export",
        "--adapter",
        adapter.value,
        "--contract",
        str(contract),
        "--output",
        str(output),
        "--seed",
        str(seed),
    ]
    _append_optional_text(arguments, "--veritas-requirement", veritas_requirement)
    _append_optional_text(arguments, "--task-name", task_name)
    _append_optional_text(arguments, "--agent-image", agent_image)
    _append_optional_text(arguments, "--runtime-image", runtime_image)
    _append_optional_text(arguments, "--verifier-image", verifier_image)
    _run_portability(arguments)


@env_app.command("conformance")
def conformance_environment_cmd(
    adapter: EnvironmentAdapter = typer.Option(..., "--adapter"),
    contract: pathlib.Path = typer.Option(..., "--contract"),
    vector: pathlib.Path = typer.Option(..., "--vector"),
) -> None:
    """Run fail-closed semantic conformance for one runtime adapter."""

    _run_portability(
        (
            "conformance",
            "--adapter",
            adapter.value,
            "--contract",
            str(contract),
            "--vector",
            str(vector),
        )
    )


@env_app.command("reverify")
def reverify_environment_cmd(
    trajectory: pathlib.Path = typer.Option(..., "--trajectory"),
    contract: pathlib.Path = typer.Option(..., "--contract"),
    include_private_identities: bool = typer.Option(
        False,
        "--include-private-identities",
    ),
    include_operator_metadata: bool = typer.Option(
        False,
        "--include-operator-metadata",
    ),
) -> None:
    """Reverify a recorded trajectory through the existing deterministic replay path."""

    arguments = [
        "trajectory",
        "--trajectory",
        str(trajectory),
        "--contract",
        str(contract),
        "--reverify",
    ]
    if include_private_identities:
        arguments.append("--include-private-identities")
    if include_operator_metadata:
        arguments.append("--include-operator-metadata")
    _run_portability(arguments)
