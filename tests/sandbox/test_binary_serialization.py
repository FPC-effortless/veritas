from investigation_world.sandbox import (
    LocalDeterministicSandboxProvider,
    LocalSandboxHandlerResult,
    SandboxCapabilityPolicy,
    SandboxCaptureResult,
    SandboxCreateRequest,
    SandboxExecutionKind,
    SandboxExecutionRequest,
    SandboxExecutionResult,
)


def test_binary_execution_and_artifact_payloads_round_trip_through_json() -> None:
    payload = b"\xff\x00\x80binary"

    def binary_command(_request, _context):
        return LocalSandboxHandlerResult(
            stdout=payload,
            stderr=payload[::-1],
            artifacts={"outputs/blob.bin": payload},
        )

    provider = LocalDeterministicSandboxProvider(commands={"binary": binary_command})
    session = provider.create(
        SandboxCreateRequest(
            writable_paths=("outputs",),
            capabilities=SandboxCapabilityPolicy(commands=("binary",)),
        )
    )
    result = session.execute(
        SandboxExecutionRequest(kind=SandboxExecutionKind.COMMAND, name="binary")
    )
    captured = session.capture(["outputs/blob.bin"])

    restored_result = SandboxExecutionResult.model_validate_json(result.model_dump_json())
    restored_capture = SandboxCaptureResult.model_validate_json(captured.model_dump_json())

    assert restored_result.stdout == payload
    assert restored_result.stderr == payload[::-1]
    assert restored_capture.artifacts[0].content == payload
