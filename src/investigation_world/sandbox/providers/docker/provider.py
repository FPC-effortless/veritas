from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from investigation_world.sandbox.models import (
    SandboxCreateRequest,
    SandboxExecutionKind,
    SandboxExecutionRequest,
)
from investigation_world.sandbox.providers.local.workspace import (
    FilesystemSandboxSession,
    SandboxBackendUnavailableError,
    SandboxProcessResult,
    canonical_digest,
    run_process,
)

SandboxProcessRunner = Callable[[tuple[str, ...], bytes, int, int], SandboxProcessResult]
_PINNED_IMAGE_RE = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")
# This is a container-only tmpfs mount specification, not a host temp directory.
_CONTAINER_TMPFS = "/tmp:rw,noexec,nosuid,nodev"  # nosec B108


class DockerUnavailableError(RuntimeError):
    pass


class DockerNetworkPolicy(StrEnum):
    NONE = "none"
    BRIDGE = "bridge"


@dataclass(frozen=True)
class DockerCommandSpec:
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.argv or any(not item for item in self.argv):
            raise ValueError("Docker command argv must contain non-empty values")


def _default_process_runner(
    argv: tuple[str, ...], stdin: bytes, timeout_ms: int, max_output_bytes: int
) -> SandboxProcessResult:
    return run_process(argv, stdin, timeout_ms, max_output_bytes)


class DockerSandboxProvider:
    """Ephemeral Docker provider with a pinned image and fail-closed defaults."""

    provider_name = "docker"

    def __init__(
        self,
        *,
        image: str,
        commands: Mapping[str, DockerCommandSpec] | None = None,
        tools: Mapping[str, DockerCommandSpec] | None = None,
        secret_values: Mapping[str, bytes | str] | None = None,
        docker_path: str = "docker",
        network: DockerNetworkPolicy = DockerNetworkPolicy.NONE,
        process_runner: SandboxProcessRunner | None = None,
    ) -> None:
        if not _PINNED_IMAGE_RE.fullmatch(image):
            raise ValueError("Docker image must be pinned by a lowercase sha256 digest")
        self._image = image
        self._commands = dict(commands or {})
        self._tools = dict(tools or {})
        self._secret_values = {
            key: value.encode() if isinstance(value, str) else bytes(value)
            for key, value in (secret_values or {}).items()
        }
        self._docker_path = docker_path
        self._network = DockerNetworkPolicy(network)
        self._process_runner = process_runner or _default_process_runner
        self._custom_runner = process_runner is not None
        configuration = {
            "image": image,
            "commands": self._spec_manifest(self._commands),
            "tools": self._spec_manifest(self._tools),
            "docker_path": docker_path,
            "network": self._network.value,
            "runner": "injected" if self._custom_runner else "subprocess",
        }
        self.provider_version = f"1:{canonical_digest(configuration)[:16]}"

    @staticmethod
    def _spec_manifest(specs: Mapping[str, DockerCommandSpec]) -> dict[str, object]:
        return {name: spec.argv for name, spec in sorted(specs.items())}

    def _ensure_available(self) -> str:
        if self._custom_runner:
            return "injected-process-runner"
        path = Path(self._docker_path)
        if (path.is_absolute() and not path.is_file()) or (
            not path.is_absolute()
            and not any(
                (directory / path).is_file()
                for directory in (Path(item) for item in ("/usr/local/bin", "/usr/bin", "/bin"))
            )
        ):
            raise DockerUnavailableError(
                f"Docker is unavailable at {self._docker_path}; no semantic fallback was used"
            )
        probe = _default_process_runner(
            (self._docker_path, "version", "--format", "{{.Server.Version}}"),
            b"",
            5_000,
            16_384,
        )
        if probe.timed_out or probe.exit_code != 0:
            detail = probe.stderr.decode(errors="replace").strip() or "daemon probe failed"
            raise DockerUnavailableError(f"Docker is unavailable: {detail}; no fallback was used")
        return probe.stdout.decode(errors="replace").strip()

    def _spec_for(self, request: SandboxExecutionRequest) -> DockerCommandSpec | None:
        if request.kind is SandboxExecutionKind.COMMAND:
            return self._commands.get(request.name)
        return self._tools.get(request.name)

    @staticmethod
    def _mount(source: Path, target: str, *, readonly: bool) -> str:
        options = f"type=bind,src={source},dst={target}"
        return f"{options},readonly" if readonly else options

    def _execute(
        self,
        request: SandboxExecutionRequest,
        workspace: Path,
        secret_root: Path,
        create_request: SandboxCreateRequest,
        session_token: str,
    ) -> SandboxProcessResult | None:
        spec = self._spec_for(request)
        if spec is None:
            return None
        execution_token = os.urandom(4).hex()
        container_name = f"veritas-{session_token}-{create_request.seed}-{execution_token}"
        argv: list[str] = [
            self._docker_path,
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            self._network.value,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "256",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--workdir",
            "/workspace",
            "--tmpfs",
            _CONTAINER_TMPFS,
            "--mount",
            self._mount(workspace, "/workspace", readonly=True),
        ]
        for writable in create_request.writable_paths:
            argv.extend(
                (
                    "--mount",
                    self._mount(workspace / writable, f"/workspace/{writable}", readonly=False),
                )
            )
        if create_request.secret_refs:
            argv.extend(
                (
                    "--mount",
                    self._mount(secret_root, "/run/veritas-secrets", readonly=True),
                )
            )
        argv.append(self._image)
        argv.extend(spec.argv)
        stdin = request.stdin
        if request.kind is SandboxExecutionKind.COMMAND:
            argv.extend(request.argv)
        else:
            stdin = json.dumps(
                request.arguments,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
        result = self._process_runner(
            tuple(argv),
            stdin,
            create_request.resources.timeout_ms,
            create_request.resources.max_output_bytes,
        )
        if result.timed_out:
            try:
                self._process_runner(
                    (self._docker_path, "rm", "-f", container_name),
                    b"",
                    10_000,
                    16_384,
                )
            except Exception:
                pass
        elif result.exit_code in {125, 126, 127}:
            detail = result.stderr.decode(errors="replace").strip() or "container launch failed"
            raise SandboxBackendUnavailableError(f"Docker infrastructure failure: {detail}")
        return result

    def create(self, request: SandboxCreateRequest) -> FilesystemSandboxSession:
        request = SandboxCreateRequest.model_validate(request.model_dump(mode="python"))
        backend_identity = self._ensure_available()
        provider_version = f"{self.provider_version}:{canonical_digest(backend_identity)[:12]}"
        session_token = os.urandom(6).hex()

        def execute(
            execution_request: SandboxExecutionRequest,
            workspace: Path,
            secret_root: Path,
        ) -> SandboxProcessResult | None:
            return self._execute(
                execution_request,
                workspace,
                secret_root,
                request,
                session_token,
            )

        return FilesystemSandboxSession(
            request=request,
            provider_name=self.provider_name,
            provider_version=provider_version,
            executor=execute,
            secret_values=self._secret_values,
        )
