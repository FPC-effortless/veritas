from __future__ import annotations

import hashlib
import json
import os
import selectors
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from investigation_world.sandbox.models import (
    SandboxArtifact,
    SandboxArtifactMetadata,
    SandboxCaptureResult,
    SandboxCreateRequest,
    SandboxCreateResult,
    SandboxDestroyResult,
    SandboxExecutionKind,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxExecutionStatus,
    SandboxFailureCode,
    SandboxFailureOrigin,
    SandboxFailureStatus,
    SandboxMountResult,
    SandboxReplayMetadata,
    SandboxResetResult,
)


@dataclass(frozen=True)
class SandboxProcessResult:
    exit_code: int | None
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    output_limited: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.stdout, bytes) or not isinstance(self.stderr, bytes):
            raise TypeError("sandbox process stdout and stderr must be bytes")
        interrupted = self.timed_out or self.output_limited
        if interrupted and self.exit_code is not None:
            raise ValueError("an interrupted process must not report an exit code")
        if not interrupted and self.exit_code is None:
            raise ValueError("a completed process must report an exit code")


class SandboxBackendUnavailableError(RuntimeError):
    pass


SandboxBackendExecutor = Callable[
    [SandboxExecutionRequest, Path, Path], SandboxProcessResult | None
]


def run_process(
    argv: tuple[str, ...],
    stdin: bytes,
    timeout_ms: int,
    max_output_bytes: int,
) -> SandboxProcessResult:
    """Run argv without a shell while bounding captured output during execution."""

    try:
        process = subprocess.Popen(  # noqa: S603 - argv is operator-configured, never shell text
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise SandboxBackendUnavailableError(f"sandbox process failed: {exc}") from exc

    if process.stdin is None or process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()
        raise SandboxBackendUnavailableError("sandbox process pipes were unavailable")

    selector = selectors.DefaultSelector()
    streams = {"stdout": process.stdout, "stderr": process.stderr}
    for name, stream in streams.items():
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
    os.set_blocking(process.stdin.fileno(), False)
    if stdin:
        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
    else:
        process.stdin.close()

    remaining_input = memoryview(stdin)
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    captured_bytes = 0
    timed_out = False
    output_limited = False
    deadline = time.monotonic() + timeout_ms / 1_000

    try:
        while selector.get_map():
            remaining_seconds = deadline - time.monotonic()
            if remaining_seconds <= 0:
                timed_out = True
                process.kill()
                break
            events = selector.select(min(remaining_seconds, 0.05))
            if not events and process.poll() is not None:
                for key in tuple(selector.get_map().values()):
                    if key.data == "stdin":
                        selector.unregister(process.stdin)
                        process.stdin.close()
                continue
            for key, _mask in events:
                if key.data == "stdin":
                    try:
                        written = os.write(key.fd, remaining_input[:65_536])
                        remaining_input = remaining_input[written:]
                    except BrokenPipeError:
                        remaining_input = remaining_input[:0]
                    if not remaining_input:
                        selector.unregister(process.stdin)
                        process.stdin.close()
                    continue
                chunk = os.read(key.fd, 65_536)
                if not chunk:
                    stream = streams[key.data]
                    selector.unregister(stream)
                    stream.close()
                    continue
                available = max_output_bytes - captured_bytes
                captured[key.data].extend(chunk[: max(available, 0)])
                captured_bytes += len(chunk)
                if captured_bytes > max_output_bytes:
                    output_limited = True
                    process.kill()
                    break
            if output_limited:
                break
    finally:
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            if not stream.closed:
                stream.close()
        return_code = process.wait()

    return SandboxProcessResult(
        exit_code=None if timed_out or output_limited else return_code,
        stdout=bytes(captured["stdout"]),
        stderr=bytes(captured["stderr"]),
        timed_out=timed_out,
        output_limited=output_limited,
    )


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_path(value: str) -> str:
    if not value:
        raise ValueError("path must not be empty")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("path must be a normalized relative POSIX path")
    normalized = path.as_posix()
    if normalized != value:
        raise ValueError("path must be a normalized relative POSIX path")
    return normalized


def path_is_within(path: str, root: str) -> bool:
    return path == root or path.startswith(f"{root}/")


class UnsafeWorkspacePathError(RuntimeError):
    pass


class FilesystemSandboxSession:
    """Provider-neutral workspace lifecycle shared by first-party process backends."""

    def __init__(
        self,
        *,
        request: SandboxCreateRequest,
        provider_name: str,
        provider_version: str,
        executor: SandboxBackendExecutor,
        secret_values: Mapping[str, bytes],
    ) -> None:
        self._request = SandboxCreateRequest.model_validate(request.model_dump(mode="python"))
        self._validate_workspace_topology()
        self._provider_name = provider_name
        self._provider_version = provider_version
        self._executor = executor
        self._secret_values = dict(secret_values)
        self._secret_refs = {ref.alias: ref.opaque_id for ref in self._request.secret_refs}
        missing = sorted(set(self._secret_refs.values()) - set(self._secret_values))
        if missing:
            raise ValueError(f"secret values are unavailable for opaque ids: {', '.join(missing)}")

        self._temporary = tempfile.TemporaryDirectory(prefix="veritas-sandbox-")
        self._session_root = Path(self._temporary.name)
        self._workspace = self._session_root / "workspace"
        self._secret_root = self._session_root / "secrets"
        self._workspace.mkdir(mode=0o700)
        self._secret_root.mkdir(mode=0o700)
        self._write_secret_files()

        self._session_id = uuid.uuid4().hex
        self._asset_by_id = {asset.asset_id: asset for asset in self._request.assets}
        self._baseline_files: dict[str, bytes] = {}
        self._reset_generation = 0
        self._execution_index = 0
        self._destroyed = False
        self._spec_digest = canonical_digest(self._request.model_dump(mode="json"))
        manifest = [
            asset.model_dump(mode="json")
            for asset in sorted(self._request.assets, key=lambda item: item.asset_id)
        ]
        self._asset_manifest_digest = canonical_digest(manifest)
        self._prepare_writable_roots()
        self._create_result = SandboxCreateResult(
            session_id=self._session_id,
            metadata=self.metadata(),
        )

    def _validate_workspace_topology(self) -> None:
        mount_paths = [asset.mount_path for asset in self._request.assets]
        for index, left in enumerate(mount_paths):
            for right in mount_paths[index + 1 :]:
                if path_is_within(left, right) or path_is_within(right, left):
                    raise ValueError(f"asset mount paths must not overlap: {left}, {right}")
        for mount_path in mount_paths:
            for writable in self._request.writable_paths:
                if path_is_within(writable, mount_path):
                    raise ValueError(
                        f"writable path must not be nested below an asset file: {writable}"
                    )

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def create_result(self) -> SandboxCreateResult:
        return self._create_result

    def _ensure_active(self) -> None:
        if self._destroyed:
            raise RuntimeError("sandbox session has been destroyed")

    def _write_secret_files(self) -> None:
        manifest: dict[str, str] = {}
        for alias, opaque_id in sorted(self._secret_refs.items()):
            filename = hashlib.sha256(alias.encode()).hexdigest()
            path = self._secret_root / filename
            path.write_bytes(self._secret_values[opaque_id])
            path.chmod(0o400)
            manifest[alias] = f"/run/veritas-secrets/{filename}"
        manifest_path = self._secret_root / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        manifest_path.chmod(0o400)

    def _prepare_writable_roots(self) -> None:
        for root in self._request.writable_paths:
            (self._workspace / root).mkdir(parents=True, exist_ok=True)

    def _redaction_values(self) -> tuple[bytes, ...]:
        values = [self._secret_values[opaque_id] for opaque_id in self._secret_refs.values()]
        return tuple(
            sorted({value for value in values if value}, key=lambda value: (-len(value), value))
        )

    def _redact(self, payload: bytes) -> bytes:
        result = bytes(payload)
        for secret in self._redaction_values():
            result = result.replace(secret, b"[REDACTED]")
        return result

    def _sanitize_message(self, message: str) -> str:
        without_session_path = message.replace(str(self._session_root), "[SESSION_ROOT]")
        return self._redact(without_session_path.encode()).decode(errors="replace")

    def _snapshot_files(self) -> dict[str, bytes]:
        files: dict[str, bytes] = {}
        for path in sorted(self._workspace.rglob("*")):
            relative = path.relative_to(self._workspace).as_posix()
            if path.is_symlink():
                raise UnsafeWorkspacePathError(f"symbolic links are forbidden: {relative}")
            if path.is_file():
                files[relative] = path.read_bytes()
            elif not path.is_dir():
                raise UnsafeWorkspacePathError(
                    f"non-regular workspace entry is forbidden: {relative}"
                )
        return files

    def _restore_files(self, files: Mapping[str, bytes]) -> None:
        if self._workspace.exists():
            shutil.rmtree(self._workspace)
        self._workspace.mkdir(mode=0o700)
        self._prepare_writable_roots()
        for relative, content in files.items():
            destination = self._workspace / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            declaration = next(
                (
                    asset
                    for asset in self._request.assets
                    if asset.mount_path == relative and asset.read_only
                ),
                None,
            )
            if declaration is not None:
                destination.chmod(0o400)

    def _filesystem_digest(self) -> str:
        manifest = {path: sha256(content) for path, content in self._snapshot_files().items()}
        return canonical_digest(manifest)

    def metadata(self) -> SandboxReplayMetadata:
        self._ensure_active()
        return SandboxReplayMetadata(
            provider_name=self._provider_name,
            provider_version=self._provider_version,
            spec_digest=self._spec_digest,
            asset_manifest_digest=self._asset_manifest_digest,
            seed=self._request.seed,
            reset_generation=self._reset_generation,
            execution_index=self._execution_index,
            filesystem_digest=self._filesystem_digest(),
        )

    def mount(self, asset_id: str, content: bytes) -> SandboxMountResult:
        self._ensure_active()
        declaration = self._asset_by_id.get(asset_id)
        if declaration is None:
            raise ValueError(f"asset is not declared: {asset_id}")
        payload = bytes(content)
        digest = sha256(payload)
        if digest != declaration.sha256:
            raise ValueError(f"asset digest mismatch: {asset_id}")
        destination = self._workspace / declaration.mount_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.chmod(0o600)
        destination.write_bytes(payload)
        if declaration.read_only:
            destination.chmod(0o400)
        self._baseline_files[declaration.mount_path] = payload
        return SandboxMountResult(
            asset_id=asset_id,
            mount_path=declaration.mount_path,
            size_bytes=len(payload),
            sha256=digest,
            metadata=self.metadata(),
        )

    def _failure(
        self,
        *,
        status: SandboxExecutionStatus,
        origin: SandboxFailureOrigin,
        code: SandboxFailureCode,
        message: str,
        retryable: bool = False,
        stdout: bytes = b"",
        stderr: bytes = b"",
        exit_code: int | None = None,
    ) -> SandboxExecutionResult:
        return SandboxExecutionResult(
            status=status,
            stdout=self._redact(stdout),
            stderr=self._redact(stderr),
            exit_code=exit_code,
            failure=SandboxFailureStatus(
                origin=origin,
                code=code,
                message=self._sanitize_message(message),
                retryable=retryable,
            ),
            metadata=self.metadata(),
        )

    def _capability_allowed(self, request: SandboxExecutionRequest) -> bool:
        if request.kind is SandboxExecutionKind.COMMAND:
            return request.name in self._request.capabilities.commands
        return request.name in self._request.capabilities.tools

    def _is_writable(self, path: str) -> bool:
        return any(path_is_within(path, root) for root in self._request.writable_paths)

    def _validate_post_execution(
        self,
        before: Mapping[str, bytes],
        after: Mapping[str, bytes],
    ) -> dict[str, bytes]:
        all_paths = set(before) | set(after)
        unexpected = sorted(
            path
            for path in all_paths
            if not self._is_writable(path) and before.get(path) != after.get(path)
        )
        if unexpected:
            raise UnsafeWorkspacePathError(
                f"execution changed a non-writable path: {unexpected[0]}"
            )
        return {
            path: content
            for path, content in after.items()
            if self._is_writable(path) and before.get(path) != content
        }

    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        self._ensure_active()
        try:
            request = SandboxExecutionRequest.model_validate(request.model_dump(mode="python"))
        except ValidationError:
            return self._failure(
                status=SandboxExecutionStatus.REJECTED,
                origin=SandboxFailureOrigin.REQUEST,
                code=SandboxFailureCode.INVALID_REQUEST,
                message="invalid sandbox execution request",
            )
        if self._execution_index >= self._request.resources.max_executions:
            return self._failure(
                status=SandboxExecutionStatus.REJECTED,
                origin=SandboxFailureOrigin.POLICY,
                code=SandboxFailureCode.EXECUTION_LIMIT,
                message="sandbox execution limit exhausted",
            )
        if not self._capability_allowed(request):
            return self._failure(
                status=SandboxExecutionStatus.REJECTED,
                origin=SandboxFailureOrigin.POLICY,
                code=SandboxFailureCode.CAPABILITY_NOT_ALLOWED,
                message=f"capability is not allowed: {request.name}",
            )

        before = self._snapshot_files()
        try:
            process = self._executor(request, self._workspace, self._secret_root)
        except SandboxBackendUnavailableError as exc:
            self._execution_index += 1
            self._restore_files(before)
            return self._failure(
                status=SandboxExecutionStatus.INFRASTRUCTURE_ERROR,
                origin=SandboxFailureOrigin.INFRASTRUCTURE,
                code=SandboxFailureCode.INFRASTRUCTURE_ERROR,
                message=str(exc),
                retryable=True,
            )
        except Exception as exc:
            self._execution_index += 1
            self._restore_files(before)
            return self._failure(
                status=SandboxExecutionStatus.INFRASTRUCTURE_ERROR,
                origin=SandboxFailureOrigin.INFRASTRUCTURE,
                code=SandboxFailureCode.INFRASTRUCTURE_ERROR,
                message=f"sandbox provider execution failed: {exc}",
                retryable=True,
            )

        if process is None:
            return self._failure(
                status=SandboxExecutionStatus.INFRASTRUCTURE_ERROR,
                origin=SandboxFailureOrigin.INFRASTRUCTURE,
                code=SandboxFailureCode.HANDLER_UNAVAILABLE,
                message=f"provider handler is unavailable: {request.name}",
                retryable=True,
            )
        if not isinstance(process, SandboxProcessResult):
            self._execution_index += 1
            self._restore_files(before)
            return self._failure(
                status=SandboxExecutionStatus.INFRASTRUCTURE_ERROR,
                origin=SandboxFailureOrigin.INFRASTRUCTURE,
                code=SandboxFailureCode.INFRASTRUCTURE_ERROR,
                message="sandbox process runner returned an invalid result",
                retryable=True,
            )

        self._execution_index += 1
        if process.timed_out:
            self._restore_files(before)
            return self._failure(
                status=SandboxExecutionStatus.TIMED_OUT,
                origin=SandboxFailureOrigin.POLICY,
                code=SandboxFailureCode.TIMEOUT,
                message="sandbox execution exceeded timeout policy",
            )
        if process.output_limited or (
            len(process.stdout) + len(process.stderr) > self._request.resources.max_output_bytes
        ):
            self._restore_files(before)
            return self._failure(
                status=SandboxExecutionStatus.REJECTED,
                origin=SandboxFailureOrigin.POLICY,
                code=SandboxFailureCode.OUTPUT_LIMIT,
                message="sandbox output exceeded resource policy",
            )

        try:
            after = self._snapshot_files()
            delta = self._validate_post_execution(before, after)
        except UnsafeWorkspacePathError as exc:
            self._restore_files(before)
            return self._failure(
                status=SandboxExecutionStatus.REJECTED,
                origin=SandboxFailureOrigin.POLICY,
                code=SandboxFailureCode.PATH_NOT_ALLOWED,
                message=str(exc),
            )

        if (
            sum(len(content) for content in delta.values())
            > self._request.resources.max_artifact_bytes
        ):
            self._restore_files(before)
            return self._failure(
                status=SandboxExecutionStatus.REJECTED,
                origin=SandboxFailureOrigin.POLICY,
                code=SandboxFailureCode.ARTIFACT_LIMIT,
                message="sandbox artifacts exceeded resource policy",
            )

        redacted_delta = {path: self._redact(content) for path, content in delta.items()}
        for relative, content in redacted_delta.items():
            (self._workspace / relative).write_bytes(content)
        artifacts = tuple(
            SandboxArtifactMetadata(path=path, size_bytes=len(content), sha256=sha256(content))
            for path, content in sorted(redacted_delta.items())
        )
        stdout = self._redact(process.stdout)
        stderr = self._redact(process.stderr)
        if process.exit_code not in {0, None}:
            return SandboxExecutionResult(
                status=SandboxExecutionStatus.WORKLOAD_FAILED,
                stdout=stdout,
                stderr=stderr,
                exit_code=process.exit_code,
                artifacts=artifacts,
                failure=SandboxFailureStatus(
                    origin=SandboxFailureOrigin.WORKLOAD,
                    code=SandboxFailureCode.WORKLOAD_FAILED,
                    message="sandbox workload returned a non-zero exit code",
                ),
                metadata=self.metadata(),
            )
        return SandboxExecutionResult(
            status=SandboxExecutionStatus.SUCCEEDED,
            stdout=stdout,
            stderr=stderr,
            exit_code=process.exit_code,
            artifacts=artifacts,
            metadata=self.metadata(),
        )

    def capture(self, paths: Iterable[str]) -> SandboxCaptureResult:
        self._ensure_active()
        artifacts = []
        for raw_path in paths:
            path = normalize_path(raw_path)
            if not self._is_writable(path):
                raise PermissionError(f"path is not a declared capturable artifact: {path}")
            source = self._workspace / path
            if source.is_symlink():
                raise PermissionError(f"symbolic-link artifacts are forbidden: {path}")
            if not source.exists():
                raise FileNotFoundError(path)
            if not source.is_file():
                raise PermissionError(f"artifact is not a regular file: {path}")
            content = self._redact(source.read_bytes())
            artifacts.append(
                SandboxArtifact(
                    path=path,
                    content=content,
                    size_bytes=len(content),
                    sha256=sha256(content),
                )
            )
        return SandboxCaptureResult(artifacts=tuple(artifacts), metadata=self.metadata())

    def reset(self) -> SandboxResetResult:
        self._ensure_active()
        self._restore_files(self._baseline_files)
        self._execution_index = 0
        self._reset_generation += 1
        return SandboxResetResult(metadata=self.metadata())

    def destroy(self) -> SandboxDestroyResult:
        self._ensure_active()
        self._secret_values.clear()
        self._baseline_files.clear()
        self._temporary.cleanup()
        self._destroyed = True
        return SandboxDestroyResult(session_id=self._session_id)
