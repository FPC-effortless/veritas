from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from investigation_world.fidelity.schema import (
    FIDELITY_SCHEMA_VERSION,
    FidelityDeclaration,
    FidelityPolicyRef,
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


class FidelityRecord(BaseModel):
    """Content-addressed fidelity disclosure bound to an exact environment and policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = FIDELITY_SCHEMA_VERSION
    record_id: str = ""
    content_sha256: str = ""
    declaration: FidelityDeclaration
    assessment_policy: FidelityPolicyRef

    @model_validator(mode="after")
    def validate_identity(self) -> "FidelityRecord":
        if self.schema_version != FIDELITY_SCHEMA_VERSION:
            raise ValueError("unsupported fidelity record schema version")
        payload = {
            "schema_version": self.schema_version,
            "declaration": self.declaration.model_dump(mode="json"),
            "assessment_policy": self.assessment_policy.model_dump(mode="json"),
        }
        content_sha256 = _canonical_sha256(payload)
        record_id = f"FID-{content_sha256[:24].upper()}"
        if self.content_sha256 and self.content_sha256 != content_sha256:
            raise ValueError("fidelity content digest does not match immutable contents")
        if self.record_id and self.record_id != record_id:
            raise ValueError("fidelity record ID does not match immutable contents")
        object.__setattr__(self, "content_sha256", content_sha256)
        object.__setattr__(self, "record_id", record_id)
        return self


def revalidate_fidelity_record(record: FidelityRecord) -> FidelityRecord:
    """Reconstruct a record so copied or nested stale state fails closed."""

    return FidelityRecord.model_validate(record.model_dump(mode="python"))


def serialize_fidelity_record(record: FidelityRecord) -> bytes:
    """Serialize a revalidated fidelity record deterministically."""

    validated_record = revalidate_fidelity_record(record)
    return _canonical_bytes(validated_record.model_dump(mode="json"))
