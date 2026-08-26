from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EvaluationManifest(BaseModel):
    schema_version: str = "0.1.0"
    run_id: str = Field(default_factory=lambda: f"VRUN-{uuid4().hex[:16].upper()}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    benchmark_name: str = "Veritas CompanyWorld"
    benchmark_version: str
    benchmark_hash: str | None = None
    model: str
    harness: str
    attempts_per_task: int = Field(default=1, ge=1)
    token_budget: int | None = Field(default=None, ge=1)
    tool_budget: int | None = Field(default=None, ge=1)
    wall_clock_seconds: int | None = Field(default=None, ge=1)
    endpoint_host: str | None = None
    customer_reference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
