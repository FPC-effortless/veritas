from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from investigation_world.sandbox.models import (
    SandboxCreateRequest,
    SandboxExecutionKind,
    SandboxExecutionRequest,
)
from investigation_world.sandbox.providers.local.workspace import (
    FilesystemSandboxSession,
    SandboxProcessResult,
    canonical_digest,
    run_process,
)

SandboxProcessRunner = Callable[[tuple[str, ...], bytes, int, int], SandboxProcessResult]
# This path names a fresh tmpfs inside Bubblewrap's namespace, not a host temp directory.
_ISOLATED_TMP = "/tmp"  # nosec B108


class LocalSandboxUnavailableError(RuntimeError):
    pass


class LocalNetworkPolicy(StrEnum):
    DENY = "deny"
    HOST = "host"


@dataclass(frozen=True)
class LocalCommandSpec:
    executable: str
    prefix_args: tuple[str, ...] = ()
    readonly_host_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not PurePosixPath(self.executable).is_absolute():
            raise ValueError("local command executable must be an absolute path")
        for path in self.readonly_host_paths:
            if not PurePosixPath(path).is_absolute():
                raise ValueError("local read-only host dependencies must be absolute paths")


def _default_process_runner(
    argv: tuple[str, ...], stdin: bytes, timeout_ms: int, max_output_bytes: int
) -> SandboxProcessResult:
    return run_process(argv, stdin, timeout_ms, max_output_bytes)


def _parent_directories(paths: tuple[str, ...]) -> tuple[str, ...]:
    parents: set[str] = set()
    for raw_path in paths:
        path = PurePosixPath(raw_path)
        parent = path if Path(raw_path).is_dir() else path.parent
        while parent != PurePosixPath("/"):
            parents.add(parent.as_posix())
            parent = parent.parent
    return tuple(sorted(parents, key=lambda item: (item.count("/"), item)))


class LocalSandboxProvider:
    """Bubblewrap-backed local process provider with explicit host dependencies."""

    provider_name = "local-bubblewrap"

    def __init__(
        self,
        *,
        commands: Mapping[str, LocalCommandSpec] | None = None,
        tools: Mapping[str, LocalCommandSpec] | None = None,
        secret_values: Mapping[str, bytes | str] | None = None,
        bubblewrap_path: str = "bwrap",
        network: LocalNetworkPolicy = LocalNetworkPolicy.DENY,
        process_runner: SandboxProcessRunner | None = None,
    ) -> None:
        self._commands = dict(commands or {})
        self._tools = dict(tools or {})
        self._secret_values = {
            key: value.encode() if isinstance(value, str) else bytes(value)
            for key, value in (secret_values or {}).items()
        }
        self._bubblewrap_path = bubblewrap_path
        self._network = LocalNetworkPolicy(network)
        self._process_runner = process_runner or _default_process_runner
        self._custom_runner = process_runner is not None
        configuration = {
            "commands": self._spec_manifest(self._commands),
            "tools": self._spec_manifest(self._tools),
            "bubblewrap_path": bubblewrap_path,
            "network": self._network.value,
            "runner": "injected" if self._custom_runner else "subprocess",
        }
        self.provider_version = f"1:{canonical_digest(configuration)[:16]}"

    @staticmethod
    def _spec_manifest(specs: Mapping[str, LocalCommandSpec]) -> dict[str, object]:
        return {
            name: {
                "executable": spec.executable,
                "prefix_args": spec.prefix_args,
                "readonly_host_paths": spec.readonly_host_paths,
            }
            for name, spec in sorted(specs.items())
        }

    def _ensure_available(self) -> str:
        path = Path(self._bubblewrap_path)
        if (path.is_absolute() and not path.is_file()) or (
            not path.is_absolute()
            and not any(
                (directory / path).is_file()
                for directory in (Path(item) for item in ("/usr/local/bin", "/usr/bin", "/bin"))
            )
        ):
            raise LocalSandboxUnavailableError(
                f"bubblewrap is unavailable at {self._bubblewrap_path}; no local fallback was used"
            )
        for name, spec in (*self._commands.items(), *self._tools.items()):
            for dependency in (spec.executable, *spec.readonly_host_paths):
                if not Path(dependency).exists():
                    raise LocalSandboxUnavailableError(
                        f"local capability {name} declares unavailable host dependency: "
                        f"{dependency}"
                    )
        if self._custom_runner:
            return "injected-process-runner"
        probe = _default_process_runner(
            (
                self._bubblewrap_path,
                "--unshare-all",
                "--die-with-parent",
                "--new-session",
                "--clearenv",
                "--ro-bind",
                "/",
                "/",
                "/bin/true",
            ),
            b"",
            5_000,
            16_384,
        )
        if probe.timed_out or probe.exit_code != 0:
            detail = probe.stderr.decode(errors="replace").strip() or "isolation probe failed"
            raise LocalSandboxUnavailableError(
                f"bubblewrap cannot establish the local sandbox: {detail}; no fallback was used"
            )
        version = _default_process_runner(
            (self._bubblewrap_path, "--version"),
            b"",
            5_000,
            16_384,
        )
        if version.timed_out or version.exit_code != 0:
            raise LocalSandboxUnavailableError(
                "bubblewrap version probe failed; no fallback was used"
            )
        return version.stdout.decode(errors="replace").strip()

    def _spec_for(self, request: SandboxExecutionRequest) -> LocalCommandSpec | None:
        if request.kind is SandboxExecutionKind.COMMAND:
            return self._commands.get(request.name)
        return self._tools.get(request.name)

    def _execute(
        self,
        request: SandboxExecutionRequest,
        workspace: Path,
        secret_root: Path,
        create_request: SandboxCreateRequest,
    ) -> SandboxProcessResult | None:
        spec = self._spec_for(request)
        if spec is None:
            return None
        dependency_paths = tuple(dict.fromkeys((spec.executable, *spec.readonly_host_paths)))
        argv: list[str] = [
            self._bubblewrap_path,
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--clearenv",
        ]
        if self._network is LocalNetworkPolicy.HOST:
            argv.append("--share-net")
        argv.extend(("--proc", "/proc", "--dev", "/dev", "--tmpfs", _ISOLATED_TMP))
        for directory in _parent_directories(dependency_paths):
            argv.extend(("--dir", directory))
        for dependency in dependency_paths:
            argv.extend(("--ro-bind", dependency, dependency))
        argv.extend(("--ro-bind", str(workspace), "/workspace"))
        for writable in create_request.writable_paths:
            argv.extend(("--bind", str(workspace / writable), f"/workspace/{writable}"))
        if create_request.secret_refs:
            argv.extend(("--dir", "/run", "--ro-bind", str(secret_root), "/run/veritas-secrets"))
        argv.extend(
            (
                "--chdir",
                "/workspace",
                "--setenv",
                "HOME",
                _ISOLATED_TMP,
                "--setenv",
                "PATH",
                "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                spec.executable,
                *spec.prefix_args,
            )
        )
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
        return self._process_runner(
            tuple(argv),
            stdin,
            create_request.resources.timeout_ms,
            create_request.resources.max_output_bytes,
        )

    def create(self, request: SandboxCreateRequest) -> FilesystemSandboxSession:
        request = SandboxCreateRequest.model_validate(request.model_dump(mode="python"))
        backend_identity = self._ensure_available()
        provider_version = f"{self.provider_version}:{canonical_digest(backend_identity)[:12]}"

        def execute(
            execution_request: SandboxExecutionRequest,
            workspace: Path,
            secret_root: Path,
        ) -> SandboxProcessResult | None:
            return self._execute(execution_request, workspace, secret_root, request)

        return FilesystemSandboxSession(
            request=request,
            provider_name=self.provider_name,
            provider_version=provider_version,
            executor=execute,
            secret_values=self._secret_values,
        )
