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
    ("interrupted", "expected_status", "expected_failure"),
    [
        (
            SandboxProcessResult(exit_code=None, timed_out=True),
            SandboxExecutionStatus.TIMED_OUT,
            SandboxFailureCode.TIMEOUT,
        ),
        (
            SandboxProcessResult(exit_code=None, output_limited=True),
            SandboxExecutionStatus.REJECTED,
            SandboxFailureCode.OUTPUT_LIMIT,
        ),
    ],
)
def test_docker_never_pulls_and_force_removes_interrupted_container(
    interrupted: SandboxProcessResult,
    expected_status: SandboxExecutionStatus,
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

    assert result.status is expected_status
    assert result.failure is not None
    assert result.failure.code is expected_failure
    assert len(calls) == 2

    run_argv, cleanup_argv = calls
    assert run_argv[:3] == ("/usr/bin/docker", "run", "--rm")
    pull_index = run_argv.index("--pull")
    assert run_argv[pull_index : pull_index + 2] == ("--pull", "never")
    name_index = run_argv.index("--name")
    container_name = run_argv[name_index + 1]
    assert cleanup_argv == ("/usr/bin/docker", "rm", "-f", container_name)


@pytest.mark.parametrize(
    "cleanup_failure",
    [
        SandboxProcessResult(exit_code=1, stderr=b"cleanup failed"),
        SandboxProcessResult(exit_code=None, timed_out=True),
        SandboxProcessResult(exit_code=None, output_limited=True),
    ],
)
def test_failed_interruption_cleanup_poison_session(
    cleanup_failure: SandboxProcessResult,
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
            return SandboxProcessResult(exit_code=None, timed_out=True)
        return cleanup_failure

    provider = DockerSandboxProvider(
        image=f"worker@sha256:{'b' * 64}",
        commands={"build": DockerCommandSpec(argv=("/worker",))},
        docker_path="/usr/bin/docker",
        process_runner=runner,
    )
    session = provider.create(
        SandboxCreateRequest(
            seed=23,
            writable_paths=("work",),
            capabilities=SandboxCapabilityPolicy(commands=("build",)),
        )
    )

    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    )

    assert result.status is SandboxExecutionStatus.INFRASTRUCTURE_ERROR
    assert result.failure is not None
    assert result.failure.code is SandboxFailureCode.INFRASTRUCTURE_ERROR
    assert "container absence is unverified" in result.failure.message
    assert len(calls) == 2

    with pytest.raises(RuntimeError, match="non-reusable"):
        session.execute(
            SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
        )
    with pytest.raises(RuntimeError, match="non-reusable"):
        session.reset()

    session.destroy()


def test_cached_public_operations_cannot_bypass_poison() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        _stdin: bytes,
        _timeout_ms: int,
        _max_output_bytes: int,
    ) -> SandboxProcessResult:
        calls.append(argv)
        if len(calls) == 1:
            return SandboxProcessResult(exit_code=None, timed_out=True)
        return SandboxProcessResult(exit_code=1, stderr=b"cleanup failed")

    provider = DockerSandboxProvider(
        image=f"worker@sha256:{'d' * 64}",
        commands={"build": DockerCommandSpec(argv=("/worker",))},
        docker_path="/usr/bin/docker",
        process_runner=runner,
    )
    session = provider.create(
        SandboxCreateRequest(
            seed=31,
            writable_paths=("work",),
            capabilities=SandboxCapabilityPolicy(commands=("build",)),
        )
    )
    cached_reset = session.reset
    cached_capture = session.capture
    cached_metadata = session.metadata

    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    )

    assert result.status is SandboxExecutionStatus.INFRASTRUCTURE_ERROR
    assert result.failure is not None
    assert result.failure.code is SandboxFailureCode.INFRASTRUCTURE_ERROR

    with pytest.raises(RuntimeError, match="non-reusable"):
        cached_reset()
    with pytest.raises(RuntimeError, match="non-reusable"):
        cached_capture(("work/result.txt",))
    with pytest.raises(RuntimeError, match="non-reusable"):
        cached_metadata()

    session.destroy()


def test_cleanup_exception_poison_session() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        _stdin: bytes,
        _timeout_ms: int,
        _max_output_bytes: int,
    ) -> SandboxProcessResult:
        calls.append(argv)
        if len(calls) == 1:
            return SandboxProcessResult(exit_code=None, output_limited=True)
        raise OSError("daemon connection lost")

    provider = DockerSandboxProvider(
        image=f"worker@sha256:{'c' * 64}",
        commands={"build": DockerCommandSpec(argv=("/worker",))},
        docker_path="/usr/bin/docker",
        process_runner=runner,
    )
    session = provider.create(
        SandboxCreateRequest(
            seed=29,
            writable_paths=("work",),
            capabilities=SandboxCapabilityPolicy(commands=("build",)),
        )
    )

    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    )

    assert result.status is SandboxExecutionStatus.INFRASTRUCTURE_ERROR
    assert result.failure is not None
    assert result.failure.code is SandboxFailureCode.INFRASTRUCTURE_ERROR
    assert "container absence is unverified" in result.failure.message

    with pytest.raises(RuntimeError, match="non-reusable"):
        session.metadata()

    session.destroy()
