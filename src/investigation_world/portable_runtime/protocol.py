from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from investigation_world.portable_contract import PortableOperationalContract
from investigation_world.portable_runtime.models import (
    PortableBudgetStatus,
    PortableResetResult,
    PortableStepRequest,
    PortableStepResult,
    PortableSubmission,
)


@runtime_checkable
class PortableRuntimeProtocol(Protocol):
    """Runtime-neutral API consumed by C-wave external-runtime adapters."""

    @property
    def contract(self) -> PortableOperationalContract: ...

    def reset(self, *, seed: int | None = 0) -> PortableResetResult: ...

    def step(
        self,
        request: PortableStepRequest | Mapping[str, Any] | str,
        arguments: Mapping[str, Any] | None = None,
    ) -> PortableStepResult: ...

    def verify(
        self,
        submission: PortableSubmission | Mapping[str, Any] | None = None,
    ) -> PortableStepResult: ...

    def submit(
        self,
        submission: PortableSubmission | Mapping[str, Any] | None = None,
    ) -> PortableStepResult: ...

    def public_state(self) -> dict[str, Any]: ...

    def state_digest(self) -> str: ...

    def budget_state(self) -> PortableBudgetStatus: ...
