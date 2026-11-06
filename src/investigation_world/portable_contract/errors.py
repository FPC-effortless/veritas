from __future__ import annotations

from typing import Any


class PortableContractError(ValueError):
    """Base error for portable operational contract failures."""


class UnsupportedOperationalSemanticError(PortableContractError):
    """Raised when source semantics cannot be represented without loss."""

    def __init__(self, *, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code} at {path}: {detail}")


class SemanticRoundTripError(PortableContractError):
    """Raised when a contract no longer preserves its source episode semantics."""

    def __init__(
        self,
        *,
        path: str,
        expected: Any,
        actual: Any,
    ) -> None:
        self.path = path
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"semantic mismatch at {path}: expected {expected!r}, got {actual!r}"
        )
