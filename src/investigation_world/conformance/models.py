from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.portable_runtime import PortableResetResult, PortableStepResult


class SemanticSnapshot(BaseModel):
    """Normalized semantic evidence captured from one runtime execution path."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    values: dict[str, Any]


class OperatorReplayTrace(BaseModel):
    """Evaluator-side evidence captured while an adapter executes a canonical vector.

    This model is deliberately absent from every agent-facing adapter schema.  It carries
    budget and verifier details that are necessary for conformance, but are not public task
    observations.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter: str
    invocations: tuple[dict[str, Any], ...]
    reset_result: PortableResetResult
    step_results: tuple[PortableStepResult, ...]


class AdapterConformanceReport(BaseModel):
    """Loss-accounting report for one adapter against a canonical test vector.

    ``passed`` is deliberately derived rather than serialized: the externally durable report
    contains exactly the semantic accounting fields, while the policy remains impossible to
    override per adapter.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    mapped_fields: dict[str, str] = Field(default_factory=dict)
    preserved_fields: tuple[str, ...] = ()
    generated_fields: tuple[str, ...] = ()
    excluded_private_fields: tuple[str, ...] = ()
    unsupported_fields: tuple[str, ...] = ()
    semantic_losses: tuple[str, ...] = ()
    test_vector_hash: str

    @property
    def passed(self) -> bool:
        """Default conformance policy: any semantic loss is a failure."""

        return not self.semantic_losses
