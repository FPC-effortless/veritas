from __future__ import annotations

import pytest

from investigation_world.sandbox import (
    SandboxCapabilityPolicy,
    SandboxCreateRequest,
    SandboxExecutionKind,
    SandboxExecutionRequest,
    SandboxExecutionStatus,
    SandboxFailureCode,
)
from investigation_world.sandbox.providers.docker import DockerCommandSpec, DockerSandboxProvider
from investigation_world.sandbox.providers.local import SandboxProcessResult


@pytest.mark.parametrize(
    ("interrupted", "expected_failure"),
    [
        (
            SandboxProcessResult(exit_code=None, timed_out=True),
            SandboxFailureCode.TIMEOUT,
        ),
        (
            SandboxProcessResult(exit_code=None, output_limited=True),
            SandboxFailureCode.OUTPUT_LIMIT,
        ),
    ],
)
def test_docker_never_pulls_and_force_removes_interrupted_container(
    interrupted: SandboxProcessResult,
    expected_failure: SandboxFailureCode,
) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        _stdin: bytes,
        _timeout_ms: int,
        _max_output_bytes: int,
    ) -> SandboxProcessResult:
        calls.append(argv)
        if len(calls) == 1:
            return interrupted
        return SandboxProcessResult(exit_code=0)

    provider = DockerSandboxProvider(
        image=f"worker@sha256:{'a' * 64}",
        commands={"build": DockerCommandSpec(argv=("/worker",))},
        docker_path="/usr/bin/docker",
        process_runner=runner,
    )
    session = provider.create(
        SandboxCreateRequest(
            seed=17,
            writable_paths=("work",),
            capabilities=SandboxCapabilityPolicy(commands=("build",)),
        )
    )

    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    )

    assert result.status is SandboxExecutionStatus.REJECTED
    assert result.failure is not None
    assert result.failure.code is expected_failure
    assert len(calls) == 2

    run_argv, cleanup_argv = calls
    pull_index = run_argv.index("--pull")
    assert run_argv[pull_index : pull_index + 2] == ("--pull", "never")
    name_index = run_argv.index("--name")
    container_name = run_argv[name_index + 1]
    assert cleanup_argv == ("/usr/bin/docker", "rm", "-f", container_name)
