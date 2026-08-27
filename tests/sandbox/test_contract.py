from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from investigation_world.sandbox import (
    LocalDeterministicSandboxProvider,
    LocalSandboxHandlerResult,
    SandboxAssetDeclaration,
    SandboxCapabilityPolicy,
    SandboxCreateRequest,
    SandboxExecutionKind,
    SandboxExecutionRequest,
    SandboxExecutionStatus,
    SandboxFailureCode,
    SandboxFailureOrigin,
    SandboxProviderProtocol,
    SandboxResourcePolicy,
    SandboxSecretRef,
    SandboxSessionProtocol,
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def request(**overrides):
    values = {
        "seed": 17,
        "assets": (
            SandboxAssetDeclaration(
                asset_id="fixture",
                mount_path="inputs/fixture.txt",
                sha256=digest(b"fixture"),
            ),
        ),
        "writable_paths": ("work", "outputs"),
        "capabilities": SandboxCapabilityPolicy(commands=("echo",), tools=("inspect",)),
    }
    values.update(overrides)
    return SandboxCreateRequest(**values)


def test_protocols_are_runtime_checkable() -> None:
    provider = LocalDeterministicSandboxProvider()
    session = provider.create(request())
    assert isinstance(provider, SandboxProviderProtocol)
    assert isinstance(session, SandboxSessionProtocol)


def test_mount_accepts_only_declared_bytes_and_no_host_paths_exist() -> None:
    session = LocalDeterministicSandboxProvider().create(request())
    mounted = session.mount("fixture", b"fixture")
    assert mounted.mount_path == "inputs/fixture.txt"
    with pytest.raises(ValueError, match="not declared"):
        session.mount("host-file", b"anything")
    with pytest.raises(ValueError, match="digest mismatch"):
        session.mount("fixture", b"wrong")

    assert "host_path" not in SandboxAssetDeclaration.model_fields
    with pytest.raises(ValidationError):
        SandboxAssetDeclaration(
            asset_id="escape",
            mount_path="../etc/passwd",
            sha256=digest(b"x"),
        )


def test_reset_restores_mounted_baseline_and_removes_execution_state() -> None:
    def echo(_request, _context):
        return LocalSandboxHandlerResult(stdout="ok", artifacts={"work/result.txt": b"changed"})

    session = LocalDeterministicSandboxProvider(commands={"echo": echo}).create(request())
    session.mount("fixture", b"fixture")
    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="echo", argv=("hello",))
    )
    assert result.status is SandboxExecutionStatus.SUCCEEDED
    assert session.capture(["work/result.txt"]).artifacts[0].content == b"changed"

    reset = session.reset()
    assert reset.metadata.execution_index == 0
    assert reset.metadata.reset_generation == 1
    with pytest.raises(PermissionError):
        session.capture(["inputs/fixture.txt"])
    with pytest.raises(FileNotFoundError):
        session.capture(["work/result.txt"])

    def inspect_fixture(_request, context):
        return LocalSandboxHandlerResult(stdout=context.files["inputs/fixture.txt"])

    fresh = LocalDeterministicSandboxProvider(tools={"inspect": inspect_fixture}).create(request())
    fresh.mount("fixture", b"fixture")
    observed = fresh.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.TOOL, name="inspect")
    )
    assert observed.stdout == b"fixture"


def test_infrastructure_failure_is_distinct_from_workload_failure() -> None:
    missing_handler = LocalDeterministicSandboxProvider().create(request())
    infrastructure = missing_handler.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="echo")
    )
    assert infrastructure.status is SandboxExecutionStatus.INFRASTRUCTURE_ERROR
    assert infrastructure.failure is not None
    assert infrastructure.failure.origin is SandboxFailureOrigin.INFRASTRUCTURE
    assert infrastructure.failure.code is SandboxFailureCode.HANDLER_UNAVAILABLE

    def failed_command(_request, _context):
        return LocalSandboxHandlerResult(exit_code=3, stderr="bad invocation")

    workload_session = LocalDeterministicSandboxProvider(
        commands={"echo": failed_command}
    ).create(request())
    workload = workload_session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="echo")
    )
    assert workload.status is SandboxExecutionStatus.WORKLOAD_FAILED
    assert workload.failure is not None
    assert workload.failure.origin is SandboxFailureOrigin.WORKLOAD


def test_secret_material_is_redacted_from_results_artifacts_and_errors() -> None:
    create = request(secret_refs=(SandboxSecretRef(alias="token", opaque_id="secret://token"),))

    def leaking_tool(_request, context):
        secret = context.read_secret("token")
        return LocalSandboxHandlerResult(
            stdout=b"token=" + secret,
            stderr=secret,
            artifacts={"outputs/leak.txt": b"copied:" + secret},
        )

    provider = LocalDeterministicSandboxProvider(
        tools={"inspect": leaking_tool},
        secret_values={"secret://token": b"super-secret"},
    )
    session = provider.create(create)
    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.TOOL, name="inspect")
    )
    captured = session.capture(["outputs/leak.txt"])
    serialized = result.model_dump_json().encode() + captured.model_dump_json().encode()
    assert b"super-secret" not in serialized
    assert result.stdout == b"token=[REDACTED]"
    assert captured.artifacts[0].content == b"copied:[REDACTED]"

    def crashing_tool(_request, context):
        raise RuntimeError(context.read_secret("token").decode())

    crashed = LocalDeterministicSandboxProvider(
        tools={"inspect": crashing_tool},
        secret_values={"secret://token": b"super-secret"},
    ).create(create)
    failure = crashed.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.TOOL, name="inspect")
    )
    assert failure.failure is not None
    assert "super-secret" not in failure.failure.message
    assert "[REDACTED]" in failure.failure.message


def test_execution_cannot_write_outside_declared_virtual_paths() -> None:
    def bad(_request, _context):
        return LocalSandboxHandlerResult(artifacts={"../escape": b"x"})

    session = LocalDeterministicSandboxProvider(commands={"echo": bad}).create(request())
    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="echo")
    )
    assert result.status is SandboxExecutionStatus.REJECTED
    assert result.failure is not None
    assert result.failure.origin is SandboxFailureOrigin.POLICY
    assert result.failure.code is SandboxFailureCode.PATH_NOT_ALLOWED


def test_resource_policies_reject_without_committing_artifact_delta() -> None:
    def slow(_request, _context):
        return LocalSandboxHandlerResult(
            artifacts={"work/late.txt": b"late"},
            duration_ms=50,
        )

    timed = LocalDeterministicSandboxProvider(commands={"echo": slow}).create(
        request(resources=SandboxResourcePolicy(timeout_ms=5))
    )
    timeout_result = timed.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="echo")
    )
    assert timeout_result.status is SandboxExecutionStatus.TIMED_OUT
    with pytest.raises(FileNotFoundError):
        timed.capture(["work/late.txt"])

    def noisy(_request, _context):
        return LocalSandboxHandlerResult(stdout=b"12345")

    output_limited = LocalDeterministicSandboxProvider(commands={"echo": noisy}).create(
        request(resources=SandboxResourcePolicy(max_output_bytes=4))
    )
    output_result = output_limited.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="echo")
    )
    assert output_result.failure is not None
    assert output_result.failure.code is SandboxFailureCode.OUTPUT_LIMIT

    def large_artifact(_request, _context):
        return LocalSandboxHandlerResult(artifacts={"work/large.bin": b"12345"})

    artifact_limited = LocalDeterministicSandboxProvider(commands={"echo": large_artifact}).create(
        request(resources=SandboxResourcePolicy(max_artifact_bytes=4))
    )
    artifact_result = artifact_limited.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="echo")
    )
    assert artifact_result.failure is not None
    assert artifact_result.failure.code is SandboxFailureCode.ARTIFACT_LIMIT
    with pytest.raises(FileNotFoundError):
        artifact_limited.capture(["work/large.bin"])


def test_replay_metadata_is_deterministic_for_same_spec_mounts_and_execution() -> None:
    def deterministic(_request, context):
        body = f"{context.seed}:{context.execution_index}".encode()
        return LocalSandboxHandlerResult(stdout=body, artifacts={"work/result.txt": body})

    provider = LocalDeterministicSandboxProvider(commands={"echo": deterministic})
    left = provider.create(request())
    right = provider.create(request())
    assert left.session_id != right.session_id
    assert left.create_result.metadata == right.create_result.metadata

    for session in (left, right):
        session.mount("fixture", b"fixture")
    left_result = left.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="echo")
    )
    right_result = right.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="echo")
    )
    assert left_result.stdout == right_result.stdout
    assert left_result.metadata == right_result.metadata


def test_sandbox_results_have_no_operational_ground_truth_or_reward_surface() -> None:
    forbidden = {"reward", "reward_components", "world_state", "ground_truth", "oracle"}
    from investigation_world.sandbox import SandboxExecutionResult, SandboxReplayMetadata

    assert forbidden.isdisjoint(SandboxExecutionResult.model_fields)
    assert forbidden.isdisjoint(SandboxReplayMetadata.model_fields)


def test_destroy_invalidates_session_and_clears_access() -> None:
    session = LocalDeterministicSandboxProvider().create(request())
    session.mount("fixture", b"fixture")
    destroyed = session.destroy()
    assert destroyed.destroyed
    with pytest.raises(RuntimeError, match="destroyed"):
        session.metadata()
