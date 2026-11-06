"""Bounded byte-integrity checks for external results, never execution attestation.

No commands or receipt-selected paths are executed/resolved. The caller supplies
its pre-run manifest and explicit local artifact paths. Constructed fixture bytes
can pass these checks; that does not establish that training occurred.
"""

from __future__ import annotations

import hashlib
import math
import os
import stat
from pathlib import Path
from typing import Literal

from pydantic import Field

from investigation_world.foundry.training_product import (
    TrainerKind,
    TrainingBundle,
    TrainingRunManifest,
    TrainingRunResult,
)
from investigation_world.trajectory import canonical_hash
from investigation_world.trajectory.models import CanonicalModel


class ExternalRunReceipt(CanonicalModel):
    result: TrainingRunResult
    status: Literal["completed", "failed", "not_run", "unknown", "incomplete"]
    base_model_revision: str = Field(min_length=1)
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    elapsed_s: float | None = Field(default=None, ge=0, allow_inf_nan=False, strict=True)
    cost: float | None = Field(default=None, ge=0, allow_inf_nan=False, strict=True)
    peak_memory_bytes: int | None = Field(default=None, ge=0, strict=True)


class ReceiptValidation(CanonicalModel):
    """Observed bytes plus external declarations; not an unforgeable credential."""

    status: Literal["byte_integrity_checked"] = "byte_integrity_checked"
    expected_manifest: TrainingRunManifest
    run_id: str
    manifest_digest: str
    bundle_digest: str
    input_digest: str
    checkpoint_digest: str
    base_model_revision: str
    elapsed_s: float | None
    cost: float | None
    peak_memory_bytes: int | None
    independent_execution_attestation: Literal["unknown"] = "unknown"
    training_validated: Literal[False] = False


def _read_artifact(path: Path, limit: int) -> bytes:
    # Open the caller-selected path once; inspect/read that same descriptor.
    # O_NONBLOCK prevents a substituted FIFO from blocking before fstat rejects it.
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("ARTIFACT_UNAVAILABLE: regular file required")
            if not 0 < info.st_size <= limit:
                raise ValueError("ARTIFACT_SIZE: nonempty bounded file required")
            data = stream.read(limit + 1)
            if not 0 < len(data) <= limit:
                raise ValueError("ARTIFACT_SIZE: nonempty bounded file required")
            return data
    except OSError as error:
        raise ValueError("ARTIFACT_UNAVAILABLE") from error


def validate_external_receipt(
    receipt: ExternalRunReceipt,
    *,
    bundle: TrainingBundle,
    expected_manifest: TrainingRunManifest,
    expected_base_model_revision: str,
    expected_input_bytes: bytes,
    input_path: str | Path,
    checkpoint_path: str | Path,
    max_artifact_bytes: int = 64 * 1024 * 1024,
) -> ReceiptValidation:
    """Validate against preselected expectations and independently read local bytes.

    ``base_model_revision`` is an external declaration checked against the caller's
    pinned expectation, not proof that model bytes were executed. Resource numbers
    are likewise declarations; omitted measurements remain unknown. The output
    checkpoint digest identifies observed bytes, not their producer or quality.
    """
    if type(max_artifact_bytes) is not int or max_artifact_bytes <= 0:
        raise ValueError("ARTIFACT_SIZE: positive integer bound required")
    if not isinstance(expected_input_bytes, bytes) or not expected_input_bytes:
        raise ValueError("INPUT_BYTES_MISMATCH: nonempty expected bytes required")
    if len(expected_input_bytes) > max_artifact_bytes:
        raise ValueError("ARTIFACT_SIZE: expected input exceeds bound")
    if (
        "seed" not in expected_manifest.model_fields_set
        or type(expected_manifest.seed) is not int
        or not expected_manifest.run_id.strip()
        or not expected_manifest.base_model.strip()
        or expected_manifest.trainer_version.strip() in {"", "unspecified", "unknown"}
    ):
        raise ValueError("MANIFEST_IDENTITY_INCOMPLETE")
    expected = TrainingRunManifest.model_validate(expected_manifest.model_dump(mode="python"))
    checked = ExternalRunReceipt.model_validate(receipt.model_dump(mode="python"))
    if checked.status != "completed":
        raise ValueError("RUN_NOT_COMPLETED")
    if checked.result.metadata.get("status", "completed") != "completed":
        raise ValueError("RUN_NOT_COMPLETED: contradictory result status")
    if not checked.result.post_training_evaluation_required:
        raise ValueError("EVALUATION_STILL_REQUIRED")
    if any(not math.isfinite(value) for value in checked.result.metrics.values()):
        raise ValueError("NONFINITE_METRIC")
    # canonical_hash also rejects nonfinite arbitrary parameter/metadata values.
    canonical_hash(checked.result.model_dump(mode="python"))
    manifest_digest = canonical_hash(expected.model_dump(mode="python"))
    if manifest_digest != canonical_hash(checked.result.manifest.model_dump(mode="python")):
        raise ValueError("MANIFEST_MISMATCH")
    if (
        expected.trainer != TrainerKind.SFT
        or bundle.recipe.trainer != expected.trainer
        or expected.bundle_id != bundle.bundle_id
    ):
        raise ValueError("BUNDLE_MISMATCH")
    bundle_digest = canonical_hash(bundle.model_dump(mode="python"))
    if bundle_digest != checked.bundle_digest:
        raise ValueError("BUNDLE_MISMATCH")
    if (
        not expected_base_model_revision.strip()
        or expected_base_model_revision.casefold() in {"main", "master", "latest", "unknown"}
        or expected_base_model_revision != checked.base_model_revision
    ):
        raise ValueError("BASE_REVISION_MISMATCH")
    input_bytes = _read_artifact(Path(input_path), max_artifact_bytes)
    input_digest = hashlib.sha256(input_bytes).hexdigest()
    if input_bytes != expected_input_bytes or input_digest != checked.input_digest:
        raise ValueError("INPUT_BYTES_MISMATCH")
    checkpoint_bytes = _read_artifact(Path(checkpoint_path), max_artifact_bytes)
    checkpoint_digest = hashlib.sha256(checkpoint_bytes).hexdigest()
    if checkpoint_digest != checked.checkpoint_digest:
        raise ValueError("CHECKPOINT_BYTES_MISMATCH")
    if checked.result.artifact_ref != str(checkpoint_path):
        raise ValueError("CHECKPOINT_REFERENCE_MISMATCH")
    return ReceiptValidation(
        expected_manifest=expected.model_copy(deep=True),
        run_id=expected.run_id,
        manifest_digest=manifest_digest,
        bundle_digest=bundle_digest,
        input_digest=input_digest,
        checkpoint_digest=checkpoint_digest,
        base_model_revision=checked.base_model_revision,
        elapsed_s=checked.elapsed_s,
        cost=checked.cost,
        peak_memory_bytes=checked.peak_memory_bytes,
    )
