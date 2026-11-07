from __future__ import annotations

import hashlib
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from investigation_world.sandbox import (
    SandboxAssetDeclaration,
    SandboxCapabilityPolicy,
    SandboxCreateRequest,
    SandboxExecutionKind,
    SandboxExecutionRequest,
    SandboxExecutionStatus,
    SandboxFailureCode,
    SandboxProviderProtocol,
    SandboxResourcePolicy,
    SandboxSecretRef,
)
from investigation_world.sandbox.providers.docker import (
    DockerCommandSpec,
    DockerNetworkPolicy,
    DockerSandboxProvider,
    DockerUnavailableError,
)
from investigation_world.sandbox.providers.local import (
    LocalCommandSpec,
    LocalNetworkPolicy,
    LocalSandboxProvider,
    LocalSandboxUnavailableError,
    SandboxProcessResult,
)
from investigation_world.sandbox.providers.local.workspace import run_process


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _request(*, secrets: bool = False) -> SandboxCreateRequest:
    return SandboxCreateRequest(
        seed=11,
        assets=(
            SandboxAssetDeclaration(
                asset_id="fixture",
                mount_path="inputs/fixture.txt",
                sha256=_digest(b"fixture"),
            ),
        ),
        writable_paths=("work",),
        capabilities=SandboxCapabilityPolicy(commands=("build",)),
        secret_refs=(
            (SandboxSecretRef(alias="api-token", opaque_id="secret://api-token"),)
            if secrets
            else ()
        ),
    )


def _flag_source(argv: Sequence[str], flag: str, target: str) -> Path:
    for index, value in enumerate(argv):
        if value == flag and index + 2 < len(argv) and argv[index + 2] == target:
            return Path(argv[index + 1])
    raise AssertionError(f"missing {flag} mount for {target}")


def _docker_mount_source(argv: Sequence[str], target: str) -> Path:
    for index, value in enumerate(argv):
        if value != "--mount" or index + 1 >= len(argv):
            continue
        fields = dict(item.split("=", 1) for item in argv[index + 1].split(",") if "=" in item)
        if fields.get("dst") == target:
            return Path(fields["src"])
    raise AssertionError(f"missing Docker mount for {target}")


def test_local_provider_runs_inside_fail_closed_bubblewrap_boundary() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...], stdin: bytes, timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        calls.append(argv)
        assert stdin == b"payload"
        assert timeout_ms == 5_000
        writable = _flag_source(argv, "--bind", "/workspace/work")
        (writable / "result.txt").write_bytes(b"done")
        return SandboxProcessResult(exit_code=0, stdout=b"ok")

    provider = LocalSandboxProvider(
        commands={"build": LocalCommandSpec(executable="/bin/sh")},
        bubblewrap_path=sys.executable,
        network=LocalNetworkPolicy.DENY,
        process_runner=runner,
    )
    session = provider.create(_request())
    assert isinstance(provider, SandboxProviderProtocol)
    session.mount("fixture", b"fixture")

    result = session.execute(
        SandboxExecutionRequest(
            kind=SandboxExecutionKind.COMMAND,
            name="build",
            argv=("arg",),
            stdin=b"payload",
        )
    )

    assert result.status is SandboxExecutionStatus.SUCCEEDED
    assert result.stdout == b"ok"
    assert session.capture(["work/result.txt"]).artifacts[0].content == b"done"
    argv = calls[0]
    assert "--unshare-all" in argv
    assert "--share-net" not in argv
    assert "--clearenv" in argv
    assert "--ro-bind" in argv
    assert argv[-2:] == ("/bin/sh", "arg")


def test_docker_provider_uses_pinned_image_and_hardened_networkless_run() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        calls.append(argv)
        writable = _docker_mount_source(argv, "/workspace/work")
        (writable / "result.txt").write_bytes(b"container-result")
        return SandboxProcessResult(exit_code=0, stdout=b"container-ok")

    image = f"registry.example/veritas-worker@sha256:{'a' * 64}"
    provider = DockerSandboxProvider(
        image=image,
        commands={"build": DockerCommandSpec(argv=("/worker", "build"))},
        docker_path="/usr/bin/docker",
        network=DockerNetworkPolicy.NONE,
        process_runner=runner,
    )
    session = provider.create(_request())
    session.mount("fixture", b"fixture")
    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    )

    assert result.status is SandboxExecutionStatus.SUCCEEDED
    assert session.capture(["work/result.txt"]).artifacts[0].content == b"container-result"
    argv = calls[0]
    assert argv[:3] == ("/usr/bin/docker", "run", "--rm")
    assert ("--network", "none") == (
        argv[argv.index("--network")],
        argv[argv.index("--network") + 1],
    )
    assert "--read-only" in argv
    assert ("--cap-drop", "ALL") == (
        argv[argv.index("--cap-drop")],
        argv[argv.index("--cap-drop") + 1],
    )
    assert "no-new-privileges" in argv
    assert image in argv


@pytest.mark.parametrize("provider_kind", ["local", "docker"])
def test_provider_reset_is_deterministic_and_discards_mutated_state(provider_kind: str) -> None:
    def local_runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        root = _flag_source(argv, "--bind", "/workspace/work")
        (root / "result.txt").write_bytes(b"changed")
        return SandboxProcessResult(exit_code=0)

    def docker_runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        root = _docker_mount_source(argv, "/workspace/work")
        (root / "result.txt").write_bytes(b"changed")
        return SandboxProcessResult(exit_code=0)

    if provider_kind == "local":
        provider = LocalSandboxProvider(
            commands={"build": LocalCommandSpec(executable="/bin/sh")},
            bubblewrap_path=sys.executable,
            process_runner=local_runner,
        )
    else:
        provider = DockerSandboxProvider(
            image=f"worker@sha256:{'b' * 64}",
            commands={"build": DockerCommandSpec(argv=("/worker",))},
            docker_path="/usr/bin/docker",
            process_runner=docker_runner,
        )

    left = provider.create(_request())
    right = provider.create(_request())
    assert left.create_result.metadata == right.create_result.metadata
    for session in (left, right):
        session.mount("fixture", b"fixture")
        session.execute(SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build"))
        reset = session.reset()
        assert reset.metadata.execution_index == 0
        assert reset.metadata.reset_generation == 1
        with pytest.raises(FileNotFoundError):
            session.capture(["work/result.txt"])


@pytest.mark.parametrize("provider_kind", ["local", "docker"])
def test_secret_bytes_are_redacted_and_never_mounted_in_workspace(provider_kind: str) -> None:
    secret = b"private-token"

    def local_runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        secret_root = _flag_source(argv, "--ro-bind", "/run/veritas-secrets")
        writable = _flag_source(argv, "--bind", "/workspace/work")
        value = next(
            path for path in secret_root.iterdir() if path.name != "manifest.json"
        ).read_bytes()
        (writable / "leak.txt").write_bytes(value)
        return SandboxProcessResult(exit_code=0, stdout=value, stderr=value)

    def docker_runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        secret_root = _docker_mount_source(argv, "/run/veritas-secrets")
        writable = _docker_mount_source(argv, "/workspace/work")
        value = next(
            path for path in secret_root.iterdir() if path.name != "manifest.json"
        ).read_bytes()
        (writable / "leak.txt").write_bytes(value)
        return SandboxProcessResult(exit_code=0, stdout=value, stderr=value)

    if provider_kind == "local":
        provider = LocalSandboxProvider(
            commands={"build": LocalCommandSpec(executable="/bin/sh")},
            secret_values={"secret://api-token": secret},
            bubblewrap_path=sys.executable,
            process_runner=local_runner,
        )
    else:
        provider = DockerSandboxProvider(
            image=f"worker@sha256:{'c' * 64}",
            commands={"build": DockerCommandSpec(argv=("/worker",))},
            secret_values={"secret://api-token": secret},
            docker_path="/usr/bin/docker",
            process_runner=docker_runner,
        )

    session = provider.create(_request(secrets=True))
    session.mount("fixture", b"fixture")
    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    )
    captured = session.capture(["work/leak.txt"])
    serialized = result.model_dump_json().encode() + captured.model_dump_json().encode()
    assert secret not in serialized
    assert result.stdout == b"[REDACTED]"
    assert captured.artifacts[0].content == b"[REDACTED]"


@pytest.mark.parametrize("provider_kind", ["local", "docker"])
def test_symlink_artifact_escape_is_rejected_and_rolled_back(
    provider_kind: str, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside")

    def local_runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        root = _flag_source(argv, "--bind", "/workspace/work")
        (root / "escape.txt").symlink_to(outside)
        return SandboxProcessResult(exit_code=0)

    def docker_runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        root = _docker_mount_source(argv, "/workspace/work")
        (root / "escape.txt").symlink_to(outside)
        return SandboxProcessResult(exit_code=0)

    if provider_kind == "local":
        provider = LocalSandboxProvider(
            commands={"build": LocalCommandSpec(executable="/bin/sh")},
            bubblewrap_path=sys.executable,
            process_runner=local_runner,
        )
    else:
        provider = DockerSandboxProvider(
            image=f"worker@sha256:{'d' * 64}",
            commands={"build": DockerCommandSpec(argv=("/worker",))},
            docker_path="/usr/bin/docker",
            process_runner=docker_runner,
        )

    session = provider.create(_request())
    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    )
    assert result.status is SandboxExecutionStatus.REJECTED
    assert result.failure is not None
    assert result.failure.code is SandboxFailureCode.PATH_NOT_ALLOWED
    with pytest.raises(FileNotFoundError):
        session.capture(["work/escape.txt"])


@pytest.mark.parametrize("provider_kind", ["local", "docker"])
def test_read_only_asset_mutation_is_rejected_and_rolled_back(provider_kind: str) -> None:
    def local_runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        workspace = _flag_source(argv, "--ro-bind", "/workspace")
        (workspace / "inputs/fixture.txt").chmod(0o600)
        (workspace / "inputs/fixture.txt").write_bytes(b"mutated")
        return SandboxProcessResult(exit_code=0)

    def docker_runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        workspace = _docker_mount_source(argv, "/workspace")
        (workspace / "inputs/fixture.txt").chmod(0o600)
        (workspace / "inputs/fixture.txt").write_bytes(b"mutated")
        return SandboxProcessResult(exit_code=0)

    if provider_kind == "local":
        provider = LocalSandboxProvider(
            commands={"build": LocalCommandSpec(executable="/bin/sh")},
            bubblewrap_path=sys.executable,
            process_runner=local_runner,
        )
    else:
        provider = DockerSandboxProvider(
            image=f"worker@sha256:{'f' * 64}",
            commands={"build": DockerCommandSpec(argv=("/worker",))},
            docker_path="/usr/bin/docker",
            process_runner=docker_runner,
        )
    session = provider.create(_request())
    session.mount("fixture", b"fixture")
    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    )
    assert result.status is SandboxExecutionStatus.REJECTED
    assert result.failure is not None
    assert result.failure.code is SandboxFailureCode.PATH_NOT_ALLOWED
    reset = session.reset()
    assert reset.metadata.execution_index == 0


@pytest.mark.parametrize("provider_kind", ["local", "docker"])
@pytest.mark.parametrize(
    ("process_result", "resources", "expected_code"),
    [
        (
            SandboxProcessResult(exit_code=None, timed_out=True),
            SandboxResourcePolicy(timeout_ms=1),
            SandboxFailureCode.TIMEOUT,
        ),
        (
            SandboxProcessResult(exit_code=0, stdout=b"12345"),
            SandboxResourcePolicy(max_output_bytes=4),
            SandboxFailureCode.OUTPUT_LIMIT,
        ),
    ],
)
def test_process_resource_limits_fail_closed(
    provider_kind: str,
    process_result: SandboxProcessResult,
    resources: SandboxResourcePolicy,
    expected_code: SandboxFailureCode,
) -> None:
    calls = 0

    def runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        nonlocal calls
        calls += 1
        if provider_kind == "docker" and argv[1:3] == ("rm", "-f"):
            return SandboxProcessResult(exit_code=0)
        return process_result

    if provider_kind == "local":
        provider = LocalSandboxProvider(
            commands={"build": LocalCommandSpec(executable="/bin/sh")},
            bubblewrap_path=sys.executable,
            process_runner=runner,
        )
    else:
        provider = DockerSandboxProvider(
            image=f"worker@sha256:{'1' * 64}",
            commands={"build": DockerCommandSpec(argv=("/worker",))},
            docker_path="/usr/bin/docker",
            process_runner=runner,
        )
    request = _request().model_copy(update={"resources": resources})
    session = provider.create(request)
    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    )
    assert result.failure is not None
    assert result.failure.code is expected_code


def test_mutable_docker_image_is_rejected() -> None:
    with pytest.raises(ValueError, match="pinned"):
        DockerSandboxProvider(image="worker:latest")


@pytest.mark.parametrize("provider_kind", ["local", "docker"])
def test_artifact_limit_rejects_and_rolls_back(provider_kind: str) -> None:
    def local_runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        (_flag_source(argv, "--bind", "/workspace/work") / "large.bin").write_bytes(b"12345")
        return SandboxProcessResult(exit_code=0)

    def docker_runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout_ms: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        (_docker_mount_source(argv, "/workspace/work") / "large.bin").write_bytes(b"12345")
        return SandboxProcessResult(exit_code=0)

    if provider_kind == "local":
        provider = LocalSandboxProvider(
            commands={"build": LocalCommandSpec(executable="/bin/sh")},
            bubblewrap_path=sys.executable,
            process_runner=local_runner,
        )
    else:
        provider = DockerSandboxProvider(
            image=f"worker@sha256:{'2' * 64}",
            commands={"build": DockerCommandSpec(argv=("/worker",))},
            docker_path="/usr/bin/docker",
            process_runner=docker_runner,
        )
    request = _request().model_copy(
        update={"resources": SandboxResourcePolicy(max_artifact_bytes=4)}
    )
    session = provider.create(request)
    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    )
    assert result.failure is not None
    assert result.failure.code is SandboxFailureCode.ARTIFACT_LIMIT
    with pytest.raises(FileNotFoundError):
        session.capture(["work/large.bin"])


def test_docker_reserved_launch_exit_is_infrastructure_not_workload() -> None:
    exposed_path: list[str] = []

    def runner(
        argv: tuple[str, ...], _stdin: bytes, _timeout: int, _max_output_bytes: int
    ) -> SandboxProcessResult:
        workspace = _docker_mount_source(argv, "/workspace")
        exposed_path.append(str(workspace))
        return SandboxProcessResult(
            exit_code=125,
            stderr=f"mount {workspace} failed".encode(),
        )

    provider = DockerSandboxProvider(
        image=f"worker@sha256:{'3' * 64}",
        commands={"build": DockerCommandSpec(argv=("/missing",))},
        docker_path="/usr/bin/docker",
        process_runner=runner,
    )
    result = provider.create(_request()).execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    )
    assert result.status is SandboxExecutionStatus.INFRASTRUCTURE_ERROR
    assert result.failure is not None
    assert result.failure.origin.value == "infrastructure"
    assert exposed_path[0] not in result.failure.message
    assert "[SESSION_ROOT]" in result.failure.message


def test_missing_secret_value_is_rejected_before_execution() -> None:
    provider = LocalSandboxProvider(
        commands={"build": LocalCommandSpec(executable="/bin/sh")},
        bubblewrap_path=sys.executable,
        process_runner=lambda _argv, _stdin, _timeout, _max_output: SandboxProcessResult(
            exit_code=0
        ),
    )
    with pytest.raises(ValueError, match="secret values are unavailable"):
        provider.create(_request(secrets=True))


def test_stale_copied_requests_are_revalidated_fail_closed() -> None:
    provider = LocalSandboxProvider(
        commands={"build": LocalCommandSpec(executable="/bin/sh")},
        bubblewrap_path=sys.executable,
        process_runner=lambda _argv, _stdin, _timeout, _max_output: SandboxProcessResult(
            exit_code=0
        ),
    )
    stale_create = _request().model_copy(update={"writable_paths": ("../escape",)})
    with pytest.raises(ValidationError, match="traversal or dot segments"):
        provider.create(stale_create)

    session = provider.create(_request())
    valid = SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="build")
    stale_execution = valid.model_copy(update={"arguments": {"unexpected": True}})
    result = session.execute(stale_execution)
    assert result.status is SandboxExecutionStatus.REJECTED
    assert result.failure is not None
    assert result.failure.code is SandboxFailureCode.INVALID_REQUEST


def test_workspace_rejects_file_directory_mount_topology_conflicts() -> None:
    provider = LocalSandboxProvider(
        bubblewrap_path=sys.executable,
        process_runner=lambda _argv, _stdin, _timeout, _max_output: SandboxProcessResult(
            exit_code=0
        ),
    )
    request = SandboxCreateRequest(
        assets=(
            SandboxAssetDeclaration(
                asset_id="file",
                mount_path="shared",
                sha256=_digest(b"file"),
            ),
        ),
        writable_paths=("shared/output",),
    )
    with pytest.raises(ValueError, match="nested below an asset file"):
        provider.create(request)


def test_unavailable_backends_fail_cleanly_without_semantic_fallback() -> None:
    local = LocalSandboxProvider(
        commands={"build": LocalCommandSpec(executable="/bin/sh")},
        bubblewrap_path="/definitely/missing/bwrap",
    )
    with pytest.raises(LocalSandboxUnavailableError, match="bubblewrap"):
        local.create(_request())

    docker = DockerSandboxProvider(
        image=f"worker@sha256:{'e' * 64}",
        commands={"build": DockerCommandSpec(argv=("/worker",))},
        docker_path="/definitely/missing/docker",
    )
    with pytest.raises(DockerUnavailableError, match="Docker"):
        docker.create(_request())


def test_real_process_runner_terminates_at_output_and_time_limits() -> None:
    output_limited = run_process(
        (sys.executable, "-c", "import sys; sys.stdout.write('x' * 10000)"),
        b"",
        5_000,
        32,
    )
    assert output_limited.output_limited
    assert len(output_limited.stdout) <= 32

    timed_out = run_process(
        (sys.executable, "-c", "import time; time.sleep(10)"),
        b"",
        10,
        32,
    )
    assert timed_out.timed_out


def test_destroy_removes_provider_workspace_and_invalidates_session() -> None:
    provider = LocalSandboxProvider(
        commands={"build": LocalCommandSpec(executable="/bin/sh")},
        bubblewrap_path=sys.executable,
        process_runner=lambda _argv, _stdin, _timeout, _max_output: SandboxProcessResult(
            exit_code=0
        ),
    )
    session = provider.create(_request())
    destroyed = session.destroy()
    assert destroyed.destroyed
    with pytest.raises(RuntimeError, match="destroyed"):
        session.metadata()