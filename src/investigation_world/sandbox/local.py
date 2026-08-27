from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

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

LocalSandboxHandler = Callable[[SandboxExecutionRequest, "LocalSandboxContext"], "LocalSandboxHandlerResult"]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return _sha256(encoded)


def _path_is_within(path: str, root: str) -> bool:
    return path == root or path.startswith(f"{root}/")


def _normalize_path(path: str) -> str:
    if not path or path.startswith("/"):
        raise ValueError("path must be a non-empty relative POSIX path")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path must not contain traversal or dot segments")
    return path


@dataclass(frozen=True)
class LocalSandboxHandlerResult:
    stdout: bytes | str = b""
    stderr: bytes | str = b""
    exit_code: int = 0
    artifacts: Mapping[str, bytes | str] = field(default_factory=dict)


class LocalSandboxContext:
    """Read-only execution snapshot supplied to deterministic local handlers."""

    def __init__(
        self,
        *,
        files: Mapping[str, bytes],
        seed: int,
        execution_index: int,
        secret_refs: Mapping[str, str],
        secret_values: Mapping[str, bytes],
    ) -> None:
        self._files = MappingProxyType(dict(files))
        self._seed = seed
        self._execution_index = execution_index
        self._secret_refs = dict(secret_refs)
        self._secret_values = secret_values

    @property
    def files(self) -> Mapping[str, bytes]:
        return self._files

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def execution_index(self) -> int:
        return self._execution_index

    def read_secret(self, alias: str) -> bytes:
        opaque_id = self._secret_refs.get(alias)
        if opaque_id is None or opaque_id not in self._secret_values:
            raise KeyError(alias)
        return self._secret_values[opaque_id]


class LocalDeterministicSandboxProvider:
    """Cheap deterministic test double with no host-filesystem or subprocess access."""

    provider_name = "local-deterministic"
    provider_version = "1"

    def __init__(
        self,
        *,
        commands: Mapping[str, LocalSandboxHandler] | None = None,
        tools: Mapping[str, LocalSandboxHandler] | None = None,
        secret_values: Mapping[str, bytes | str] | None = None,
    ) -> None:
        self._commands = dict(commands or {})
        self._tools = dict(tools or {})
        self._secret_values = {
            key: value.encode() if isinstance(value, str) else bytes(value)
            for key, value in (secret_values or {}).items()
        }

    def create(self, request: SandboxCreateRequest) -> "LocalDeterministicSandboxSession":
        return LocalDeterministicSandboxSession(
            request=request,
            commands=self._commands,
            tools=self._tools,
            secret_values=self._secret_values,
        )


class LocalDeterministicSandboxSession:
    def __init__(
        self,
        *,
        request: SandboxCreateRequest,
        commands: Mapping[str, LocalSandboxHandler],
        tools: Mapping[str, LocalSandboxHandler],
        secret_values: Mapping[str, bytes],
    ) -> None:
        self._request = request
        self._session_id = uuid.uuid4().hex
        self._commands = dict(commands)
        self._tools = dict(tools)
        self._secret_values = dict(secret_values)
        self._secret_refs = {ref.alias: ref.opaque_id for ref in request.secret_refs}
        self._asset_by_id = {asset.asset_id: asset for asset in request.assets}
        self._baseline_files: dict[str, bytes] = {}
        self._files: dict[str, bytes] = {}
        self._reset_generation = 0
        self._execution_index = 0
        self._destroyed = False
        self._spec_digest = _canonical_digest(request.model_dump(mode="json"))
        manifest = [
            asset.model_dump(mode="json")
            for asset in sorted(request.assets, key=lambda item: item.asset_id)
        ]
        self._asset_manifest_digest = _canonical_digest(manifest)
        self._create_result = SandboxCreateResult(
            session_id=self._session_id,
            metadata=self.metadata(),
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

    def _filesystem_digest(self) -> str:
        manifest = {path: _sha256(content) for path, content in sorted(self._files.items())}
        return _canonical_digest(manifest)

    def metadata(self) -> SandboxReplayMetadata:
        self._ensure_active()
        return SandboxReplayMetadata(
            provider_name=LocalDeterministicSandboxProvider.provider_name,
            provider_version=LocalDeterministicSandboxProvider.provider_version,
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
        digest = _sha256(payload)
        if digest != declaration.sha256:
            raise ValueError(f"asset digest mismatch: {asset_id}")
        self._baseline_files[declaration.mount_path] = payload
        self._files[declaration.mount_path] = payload
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
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            failure=SandboxFailureStatus(
                origin=origin,
                code=code,
                message=self._redact_bytes(message.encode()).decode(errors="replace"),
                retryable=retryable,
            ),
            metadata=self.metadata(),
        )

    def _redaction_values(self) -> tuple[bytes, ...]:
        values = []
        for opaque_id in self._secret_refs.values():
            value = self._secret_values.get(opaque_id)
            if value:
                values.append(value)
        return tuple(sorted(set(values), key=lambda item: (-len(item), item)))

    def _redact_bytes(self, payload: bytes) -> bytes:
        redacted = bytes(payload)
        for secret in self._redaction_values():
            redacted = redacted.replace(secret, b"[REDACTED]")
        return redacted

    def _handler_for(self, request: SandboxExecutionRequest) -> LocalSandboxHandler | None:
        if request.kind is SandboxExecutionKind.COMMAND:
            return self._commands.get(request.name)
        return self._tools.get(request.name)

    def _capability_allowed(self, request: SandboxExecutionRequest) -> bool:
        if request.kind is SandboxExecutionKind.COMMAND:
            return request.name in self._request.capabilities.commands
        return request.name in self._request.capabilities.tools

    def _artifact_path_allowed(self, path: str) -> bool:
        if not any(_path_is_within(path, root) for root in self._request.writable_paths):
            return False
        for declaration in self._request.assets:
            if declaration.read_only and _path_is_within(path, declaration.mount_path):
                return False
        return True

    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        self._ensure_active()
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
        handler = self._handler_for(request)
        if handler is None:
            return self._failure(
                status=SandboxExecutionStatus.INFRASTRUCTURE_ERROR,
                origin=SandboxFailureOrigin.INFRASTRUCTURE,
                code=SandboxFailureCode.HANDLER_UNAVAILABLE,
                message=f"provider handler is unavailable: {request.name}",
                retryable=True,
            )

        context = LocalSandboxContext(
            files=self._files,
            seed=self._request.seed,
            execution_index=self._execution_index,
            secret_refs=self._secret_refs,
            secret_values=self._secret_values,
        )
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="veritas-sandbox")
        future = executor.submit(handler, request, context)
        try:
            raw = future.result(timeout=self._request.resources.timeout_ms / 1000)
        except FutureTimeoutError:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            self._execution_index += 1
            return self._failure(
                status=SandboxExecutionStatus.TIMED_OUT,
                origin=SandboxFailureOrigin.POLICY,
                code=SandboxFailureCode.TIMEOUT,
                message="sandbox execution exceeded timeout policy",
            )
        except Exception as exc:
            executor.shutdown(wait=False, cancel_futures=True)
            self._execution_index += 1
            return self._failure(
                status=SandboxExecutionStatus.INFRASTRUCTURE_ERROR,
                origin=SandboxFailureOrigin.INFRASTRUCTURE,
                code=SandboxFailureCode.INFRASTRUCTURE_ERROR,
                message=f"sandbox provider execution failed: {exc}",
                retryable=True,
            )
        else:
            executor.shutdown(wait=True)

        self._execution_index += 1
        if not isinstance(raw, LocalSandboxHandlerResult):
            return self._failure(
                status=SandboxExecutionStatus.INFRASTRUCTURE_ERROR,
                origin=SandboxFailureOrigin.INFRASTRUCTURE,
                code=SandboxFailureCode.INFRASTRUCTURE_ERROR,
                message="sandbox provider handler returned an invalid result",
                retryable=True,
            )

        stdout = raw.stdout.encode() if isinstance(raw.stdout, str) else bytes(raw.stdout)
        stderr = raw.stderr.encode() if isinstance(raw.stderr, str) else bytes(raw.stderr)
        stdout = self._redact_bytes(stdout)
        stderr = self._redact_bytes(stderr)
        if len(stdout) + len(stderr) > self._request.resources.max_output_bytes:
            return self._failure(
                status=SandboxExecutionStatus.REJECTED,
                origin=SandboxFailureOrigin.POLICY,
                code=SandboxFailureCode.OUTPUT_LIMIT,
                message="sandbox output exceeded resource policy",
            )

        sanitized_artifacts: dict[str, bytes] = {}
        for raw_path, raw_content in raw.artifacts.items():
            try:
                path = _normalize_path(raw_path)
            except ValueError as exc:
                return self._failure(
                    status=SandboxExecutionStatus.REJECTED,
                    origin=SandboxFailureOrigin.POLICY,
                    code=SandboxFailureCode.PATH_NOT_ALLOWED,
                    message=str(exc),
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=raw.exit_code,
                )
            if not self._artifact_path_allowed(path):
                return self._failure(
                    status=SandboxExecutionStatus.REJECTED,
                    origin=SandboxFailureOrigin.POLICY,
                    code=SandboxFailureCode.PATH_NOT_ALLOWED,
                    message=f"artifact path is not writable: {path}",
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=raw.exit_code,
                )
            content = raw_content.encode() if isinstance(raw_content, str) else bytes(raw_content)
            sanitized_artifacts[path] = self._redact_bytes(content)

        total_artifact_bytes = sum(len(content) for content in sanitized_artifacts.values())
        if total_artifact_bytes > self._request.resources.max_artifact_bytes:
            return self._failure(
                status=SandboxExecutionStatus.REJECTED,
                origin=SandboxFailureOrigin.POLICY,
                code=SandboxFailureCode.ARTIFACT_LIMIT,
                message="sandbox artifacts exceeded resource policy",
                stdout=stdout,
                stderr=stderr,
                exit_code=raw.exit_code,
            )

        self._files.update(sanitized_artifacts)
        artifact_meta = tuple(
            SandboxArtifactMetadata(path=path, size_bytes=len(content), sha256=_sha256(content))
            for path, content in sorted(sanitized_artifacts.items())
        )
        if raw.exit_code != 0:
            return SandboxExecutionResult(
                status=SandboxExecutionStatus.WORKLOAD_FAILED,
                stdout=stdout,
                stderr=stderr,
                exit_code=raw.exit_code,
                artifacts=artifact_meta,
                failure=SandboxFailureStatus(
                    origin=SandboxFailureOrigin.WORKLOAD,
                    code=SandboxFailureCode.WORKLOAD_FAILED,
                    message="sandbox workload returned a non-zero exit code",
                    retryable=False,
                ),
                metadata=self.metadata(),
            )
        return SandboxExecutionResult(
            status=SandboxExecutionStatus.SUCCEEDED,
            stdout=stdout,
            stderr=stderr,
            exit_code=raw.exit_code,
            artifacts=artifact_meta,
            metadata=self.metadata(),
        )

    def capture(self, paths: Iterable[str]) -> SandboxCaptureResult:
        self._ensure_active()
        artifacts = []
        for raw_path in paths:
            path = _normalize_path(raw_path)
            if not any(_path_is_within(path, root) for root in self._request.writable_paths):
                raise PermissionError(f"path is not a declared capturable artifact: {path}")
            if path not in self._files:
                raise FileNotFoundError(path)
            content = self._redact_bytes(self._files[path])
            artifacts.append(
                SandboxArtifact(
                    path=path,
                    content=content,
                    size_bytes=len(content),
                    sha256=_sha256(content),
                )
            )
        return SandboxCaptureResult(artifacts=tuple(artifacts), metadata=self.metadata())

    def reset(self) -> SandboxResetResult:
        self._ensure_active()
        self._files = dict(self._baseline_files)
        self._execution_index = 0
        self._reset_generation += 1
        return SandboxResetResult(metadata=self.metadata())

    def destroy(self) -> SandboxDestroyResult:
        self._ensure_active()
        self._files.clear()
        self._baseline_files.clear()
        self._secret_values.clear()
        self._destroyed = True
        return SandboxDestroyResult(session_id=self._session_id)
