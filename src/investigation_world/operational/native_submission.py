"""Evaluator-private native submission snapshots; deliberately independent of trajectory."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NATIVE_VERIFIER_ID = "investigation_world.operational.parameterized_artifacts"
NATIVE_VERIFIER_VERSION = "native-artifact-v1"
NATIVE_ARTIFACT_SOURCES = (
    ("artifacts.py", "d7dc477d9603817ce87d7cc47e03d024106202fa"),
    ("parameterized_artifacts.py", "ba463ac4ffaea807513c911d835b2b53bdb58fb9"),
)


def canonical_native_json(value: Any) -> str:
    """Same JSON canonicalization as trajectory, without importing its package.

    Callers pass JSON-mode model dumps, never Python objects with implicit string coercion.
    """
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def native_source_identities() -> tuple[tuple[str, str], ...]:
    """Read identities of the fixed local implementations, not a supplied entrypoint."""
    identities = []
    for filename, _ in NATIVE_ARTIFACT_SOURCES:
        content = Path(__file__).with_name(filename).read_bytes().replace(b"\r\n", b"\n")
        header = f"blob {len(content)}\0".encode()
        digest = hashlib.sha1(header + content, usedforsecurity=False).hexdigest()
        identities.append((filename, digest))
    return tuple(identities)


class NativeSubmissionReceipt(BaseModel):
    """Immutable content binding, not a signature or proof of truthful verifier checks.

    Nested snapshots are canonical JSON strings rather than mutable model/dict fields.
    Only offline inspection using the authorized pinned verifier can establish validity.
    The retained artifact path and all snapshot contents are evaluator-private.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["veritas.native-submission.v1"] = "veritas.native-submission.v1"
    receipt_id: str = ""
    receipt_digest: str = ""
    verifier_id: str = NATIVE_VERIFIER_ID
    verifier_version: str = NATIVE_VERIFIER_VERSION
    artifact_sources: tuple[tuple[str, str], ...] = NATIVE_ARTIFACT_SOURCES
    artifact_path: str
    episode_json: str
    initial_state_json: str
    pre_state_json: str
    final_state_json: str
    action_events_json: str
    submission_json: str
    verification_json: str
    descriptor_json: str
    tool_calls: int = Field(ge=0)
    cost_spent: int = Field(ge=0)

    def digest_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"receipt_id", "receipt_digest"})

    @model_validator(mode="after")
    def bind_identity(self) -> NativeSubmissionReceipt:
        for field in (
            "episode_json", "initial_state_json", "pre_state_json", "final_state_json",
            "action_events_json", "submission_json", "verification_json", "descriptor_json",
        ):
            raw = getattr(self, field)
            if canonical_native_json(json.loads(raw)) != raw:
                raise ValueError(f"{field} must contain canonical JSON")
        digest = hashlib.sha256(canonical_native_json(self.digest_payload()).encode()).hexdigest()
        receipt_id = f"NATIVE-SUBMISSION-{digest[:24].upper()}"
        if self.receipt_digest and self.receipt_digest != digest:
            raise ValueError("receipt_digest does not match native submission contents")
        if self.receipt_id and self.receipt_id != receipt_id:
            raise ValueError("receipt_id does not match native submission contents")
        object.__setattr__(self, "receipt_digest", digest)
        object.__setattr__(self, "receipt_id", receipt_id)
        return self
