from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from investigation_world.sandbox.models import (
    SandboxCaptureResult,
    SandboxCreateRequest,
    SandboxCreateResult,
    SandboxDestroyResult,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxMountResult,
    SandboxReplayMetadata,
    SandboxResetResult,
)


@runtime_checkable
class SandboxSessionProtocol(Protocol):
    """Provider-neutral lifecycle for one infrastructure sandbox session."""

    @property
    def session_id(self) -> str: ...

    @property
    def create_result(self) -> SandboxCreateResult: ...

    def mount(self, asset_id: str, content: bytes) -> SandboxMountResult: ...

    def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult: ...

    def capture(self, paths: Iterable[str]) -> SandboxCaptureResult: ...

    def reset(self) -> SandboxResetResult: ...

    def metadata(self) -> SandboxReplayMetadata: ...

    def destroy(self) -> SandboxDestroyResult: ...


@runtime_checkable
class SandboxProviderProtocol(Protocol):
    """Factory boundary implemented by local or remote sandbox providers."""

    def create(self, request: SandboxCreateRequest) -> SandboxSessionProtocol: ...
