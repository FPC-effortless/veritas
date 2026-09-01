from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path
from typing import Any, cast

from .acquisition import HTTPTransport, acquire_artifact, verify_receipt
from .catalog import catalog_digest, find_source, load_catalog
from .models import (
    AcquisitionArtifact,
    AcquisitionPolicy,
    ArtifactClass,
    ArtifactMethod,
    SourceCatalog,
    SourceSpec,
)


class QueuedAcquisitionError(RuntimeError):
    """Raised when a checked-in acquisition queue is inconsistent or unverifiable."""


def load_acquisition_queue(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QueuedAcquisitionError("acquisition queue must be a JSON object")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise QueuedAcquisitionError("acquisition queue must contain artifacts")
    return cast(dict[str, Any], value)


def build_queue_catalog(base_catalog: SourceCatalog, queue: dict[str, Any]) -> SourceCatalog:
    source_id = _required_string(queue, "source_id")
    source = find_source(base_catalog, source_id)
    if source.rights.acquisition is not AcquisitionPolicy.APPROVED:
        raise QueuedAcquisitionError(
            f"queue source {source_id!r} is not approved for automated acquisition"
        )

    queue_artifacts = _queue_artifacts(queue)
    declared_ids = {artifact.artifact_id for artifact in source.artifacts}
    overlay: list[AcquisitionArtifact] = list(source.artifacts)
    for entry in queue_artifacts:
        artifact_id = _required_string(entry, "artifact_id")
        if artifact_id in declared_ids:
            raise QueuedAcquisitionError(
                f"queue artifact {artifact_id!r} duplicates a catalog artifact"
            )
        expected_sha256 = entry.get("sha256")
        if expected_sha256 is not None and not isinstance(expected_sha256, str):
            raise QueuedAcquisitionError(f"invalid sha256 for {artifact_id!r}")
        acquisition_url = _acquisition_url(entry)
        overlay.append(
            AcquisitionArtifact(
                artifact_id=artifact_id,
                label=f"Gold-10 final report for {_required_string(entry, 'case_id')}",
                method=ArtifactMethod.HTTP_FILE,
                url=acquisition_url,
                artifact_class=ArtifactClass.DOCUMENT,
                filename=f"{artifact_id}.pdf",
                expected_sha256=expected_sha256,
                notes="Ephemeral queue overlay; source bytes are not committed to Git.",
            )
        )
        declared_ids.add(artifact_id)

    source_payload = source.model_dump(mode="json")
    source_payload["artifacts"] = [item.model_dump(mode="json") for item in overlay]
    replacement = SourceSpec.model_validate(source_payload)

    catalog_payload = base_catalog.model_dump(mode="json")
    catalog_payload["sources"] = [
        replacement.model_dump(mode="json")
        if item.source_id == source_id
        else item.model_dump(mode="json")
        for item in base_catalog.sources
    ]
    return SourceCatalog.model_validate(catalog_payload)


def acquire_queue_receipts(
    queue_path: Path,
    output_root: Path,
    receipts_out: Path,
    *,
    effective_catalog_out: Path | None = None,
    max_bytes: int = 256 * 1024 * 1024,
    timeout: float = 120.0,
    delay_seconds: float = 1.0,
    transport: HTTPTransport | None = None,
) -> dict[str, Any]:
    queue_bytes = queue_path.read_bytes()
    queue_sha256 = hashlib.sha256(queue_bytes).hexdigest()
    queue = load_acquisition_queue(queue_path)
    base_catalog = load_catalog()
    expanded_catalog = build_queue_catalog(base_catalog, queue)
    effective_catalog_bytes = _catalog_bytes(expanded_catalog)
    effective_catalog_sha256 = hashlib.sha256(effective_catalog_bytes).hexdigest()
    effective_catalog_target = effective_catalog_out or receipts_out.with_name(
        f"{receipts_out.stem}.effective-catalog.json"
    )
    source_id = _required_string(queue, "source_id")
    queue_artifacts = _queue_artifacts(queue)
    receipts: list[dict[str, Any]] = []

    output_root.mkdir(parents=True, exist_ok=True)
    receipts_out.parent.mkdir(parents=True, exist_ok=True)
    effective_catalog_target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="veritas-effective-catalog-") as temp_dir:
        effective_catalog_path = Path(temp_dir) / "source_catalog.json"
        effective_catalog_path.write_bytes(effective_catalog_bytes)
        for index, entry in enumerate(queue_artifacts):
            artifact_id = _required_string(entry, "artifact_id")
            raw_path, receipt_path = _queue_output_paths(output_root, source_id, artifact_id)
            _require_unclaimed_output_paths(artifact_id, raw_path, receipt_path)
            try:
                receipt = acquire_artifact(
                    expanded_catalog,
                    source_id,
                    artifact_id,
                    output_root,
                    catalog_path=effective_catalog_path,
                    max_bytes=max_bytes,
                    timeout=timeout,
                    transport=transport,
                )
                if receipt.catalog_sha256 != effective_catalog_sha256:
                    raise QueuedAcquisitionError(
                        f"receipt authority mismatch for {artifact_id!r}"
                    )
                if not verify_receipt(output_root, receipt):
                    raise QueuedAcquisitionError(
                        f"byte verification failed immediately after acquiring {artifact_id!r}"
                    )

                actual_raw_path = (output_root.resolve() / receipt.local_path).resolve()
                if actual_raw_path != raw_path:
                    raise QueuedAcquisitionError(
                        f"unexpected raw output path for {artifact_id!r}: {receipt.local_path!r}"
                    )
                actual_receipt_path = raw_path.with_name(raw_path.name + ".provenance.json")
                if actual_receipt_path != receipt_path or not receipt_path.is_file():
                    raise QueuedAcquisitionError(
                        f"missing provenance receipt for {artifact_id!r}"
                    )

                authority = _queue_artifact_authority(entry, source_id=source_id)
                item = receipt.model_dump(mode="json")
                item["canonical_source_url"] = authority["canonical_source_url"]
                item["acquisition_url"] = authority["acquisition_url"]
                item["expected_sha256"] = authority["expected_sha256"]
                item["queue_sha256"] = queue_sha256
                item["acquisition_spec_sha256"] = _authority_digest(authority)
                item["case_id"] = authority["case_id"]

                receipt_path.write_text(
                    json.dumps(item, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                item["receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
                receipts.append(item)
            finally:
                # Only the exact raw path reserved for this queue artifact belongs to this
                # invocation. Never recursively delete caller-owned files below output_root.
                raw_path.unlink(missing_ok=True)

            if index + 1 < len(queue_artifacts) and delay_seconds > 0:
                time.sleep(delay_seconds)

    effective_catalog_target.write_bytes(effective_catalog_bytes)
    retained_catalog_sha256 = hashlib.sha256(effective_catalog_target.read_bytes()).hexdigest()
    if retained_catalog_sha256 != effective_catalog_sha256:
        raise QueuedAcquisitionError("retained effective catalog identity changed after write")

    bundle = {
        "bundle_version": "1.2",
        "corpus_id": _required_string(queue, "corpus_id"),
        "source_id": source_id,
        "queue_sha256": queue_sha256,
        "base_catalog_sha256": catalog_digest(),
        "catalog_sha256": effective_catalog_sha256,
        "effective_catalog_sha256": effective_catalog_sha256,
        "effective_catalog_file": effective_catalog_target.name,
        "raw_payloads_retained": False,
        "artifacts": receipts,
    }
    encoded = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
    receipts_out.write_text(encoded, encoding="utf-8")
    print("VERITAS_RECEIPT_BUNDLE_BEGIN")
    print(encoded, end="")
    print("VERITAS_RECEIPT_BUNDLE_END")
    return bundle


def _queue_artifacts(queue: dict[str, Any]) -> list[dict[str, Any]]:
    raw = queue.get("artifacts")
    if not isinstance(raw, list):
        raise QueuedAcquisitionError("queue artifacts must be a list")
    result: list[dict[str, Any]] = []
    for index, value in enumerate(raw):
        if not isinstance(value, dict):
            raise QueuedAcquisitionError(f"queue artifact {index} must be an object")
        result.append(cast(dict[str, Any], value))
    return result


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise QueuedAcquisitionError(f"{key} must be a non-empty string")
    return item


def _acquisition_url(entry: dict[str, Any]) -> str:
    acquisition_url = entry.get("acquisition_url")
    if acquisition_url is None:
        return _required_string(entry, "source_url")
    if not isinstance(acquisition_url, str) or not acquisition_url.strip():
        artifact_id = _required_string(entry, "artifact_id")
        raise QueuedAcquisitionError(
            f"acquisition_url must be a non-empty string for {artifact_id!r}"
        )
    return acquisition_url


def _queue_artifact_authority(entry: dict[str, Any], *, source_id: str) -> dict[str, Any]:
    expected_sha256 = entry.get("sha256")
    if expected_sha256 is not None and not isinstance(expected_sha256, str):
        raise QueuedAcquisitionError(
            f"invalid sha256 for {_required_string(entry, 'artifact_id')!r}"
        )
    return {
        "source_id": source_id,
        "case_id": _required_string(entry, "case_id"),
        "artifact_id": _required_string(entry, "artifact_id"),
        "canonical_source_url": _required_string(entry, "source_url"),
        "acquisition_url": _acquisition_url(entry),
        "expected_sha256": expected_sha256,
    }


def _authority_digest(authority: dict[str, Any]) -> str:
    encoded = json.dumps(
        authority,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _queue_output_paths(root: Path, source_id: str, artifact_id: str) -> tuple[Path, Path]:
    resolved_root = root.resolve()
    raw_path = (
        resolved_root / source_id / artifact_id / f"{artifact_id}.pdf"
    ).resolve()
    if resolved_root not in raw_path.parents:
        raise QueuedAcquisitionError("queue output path escaped acquisition root")
    receipt_path = raw_path.with_name(raw_path.name + ".provenance.json")
    return raw_path, receipt_path


def _require_unclaimed_output_paths(
    artifact_id: str,
    raw_path: Path,
    receipt_path: Path,
) -> None:
    for path in (raw_path, receipt_path):
        if path.exists():
            raise QueuedAcquisitionError(
                f"refusing to overwrite pre-existing output for {artifact_id!r}: {path}"
            )


def _catalog_bytes(catalog: SourceCatalog) -> bytes:
    encoded = json.dumps(catalog.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    return encoded.encode("utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Acquire a checked-in artifact queue and retain provenance receipts only."
    )
    parser.add_argument("queue", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipts-out", type=Path, required=True)
    parser.add_argument("--effective-catalog-out", type=Path)
    parser.add_argument("--max-bytes", type=int, default=256 * 1024 * 1024)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    acquire_queue_receipts(
        args.queue,
        args.output,
        args.receipts_out,
        effective_catalog_out=args.effective_catalog_out,
        max_bytes=args.max_bytes,
        timeout=args.timeout,
        delay_seconds=args.delay_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())