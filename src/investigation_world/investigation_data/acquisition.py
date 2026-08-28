from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol, cast
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .catalog import catalog_digest, find_source
from .models import (
    AcquisitionArtifact,
    AcquisitionPolicy,
    ArtifactMethod,
    ArtifactReceipt,
    SourceCatalog,
    SourceSpec,
)


class AcquisitionError(RuntimeError):
    pass


class HTTPResponse(Protocol):
    headers: object

    def read(self, size: int = -1) -> bytes: ...

    def geturl(self) -> str: ...

    def __enter__(self) -> "HTTPResponse": ...

    def __exit__(self, exc_type, exc, tb) -> None: ...


class HTTPTransport(Protocol):
    def open(self, request: Request, timeout: float) -> HTTPResponse: ...


class _AllowlistedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: tuple[str, ...]):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _assert_allowed_url(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UrllibTransport:
    def __init__(self, allowed_hosts: tuple[str, ...]):
        self.allowed_hosts = allowed_hosts
        self.opener = build_opener(_AllowlistedRedirectHandler(allowed_hosts))

    def open(self, request: Request, timeout: float) -> HTTPResponse:
        _assert_allowed_url(request.full_url, self.allowed_hosts)
        return self.opener.open(request, timeout=timeout)  # type: ignore[return-value]


@dataclass(frozen=True)
class AcquisitionPlan:
    source_id: str
    artifact_id: str
    allowed: bool
    reason: str
    source_url: str


def plan_artifact(
    catalog: SourceCatalog,
    source_id: str,
    artifact_id: str,
    *,
    rights_review_id: str | None = None,
) -> AcquisitionPlan:
    source = find_source(catalog, source_id)
    artifact = _find_artifact(source, artifact_id)
    policy = source.rights.acquisition
    if policy is AcquisitionPolicy.BLOCKED:
        return AcquisitionPlan(source_id, artifact_id, False, "source is blocked", artifact.url)
    if policy is AcquisitionPolicy.METADATA_ONLY and artifact.artifact_class.value != "metadata":
        return AcquisitionPlan(
            source_id,
            artifact_id,
            False,
            "source policy permits metadata acquisition only",
            artifact.url,
        )
    if policy is AcquisitionPolicy.REVIEW_REQUIRED and not rights_review_id:
        return AcquisitionPlan(
            source_id,
            artifact_id,
            False,
            "rights review identifier is required",
            artifact.url,
        )
    if artifact.method is not ArtifactMethod.HTTP_FILE:
        return AcquisitionPlan(
            source_id,
            artifact_id,
            False,
            f"artifact uses {artifact.method.value}; generic downloader only handles http_file",
            artifact.url,
        )
    return AcquisitionPlan(source_id, artifact_id, True, "approved", artifact.url)


def acquire_artifact(
    catalog: SourceCatalog,
    source_id: str,
    artifact_id: str,
    destination_root: Path,
    *,
    catalog_path: Path | None = None,
    rights_review_id: str | None = None,
    identified_user_agent: str | None = None,
    max_bytes: int = 2 * 1024 * 1024 * 1024,
    timeout: float = 60.0,
    transport: HTTPTransport | None = None,
) -> ArtifactReceipt:
    source = find_source(catalog, source_id)
    artifact = _find_artifact(source, artifact_id)
    plan = plan_artifact(catalog, source_id, artifact_id, rights_review_id=rights_review_id)
    if not plan.allowed:
        raise AcquisitionError(plan.reason)
    if source.requires_identified_user_agent and not identified_user_agent:
        raise AcquisitionError("source requires an identified user agent")

    _assert_allowed_url(artifact.url, source.allowed_hosts)
    filename = artifact.filename or Path(urlparse(artifact.url).path).name
    if not filename or not _SAFE_FILENAME.fullmatch(filename):
        raise AcquisitionError(
            "artifact URL does not yield a safe filename; catalog must set filename"
        )

    root = destination_root.resolve()
    target_dir = (root / source.source_id / artifact.artifact_id).resolve()
    if root != target_dir and root not in target_dir.parents:
        raise AcquisitionError("destination escaped acquisition root")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename
    receipt_path = target_path.with_name(target_path.name + ".provenance.json")

    headers = {"User-Agent": identified_user_agent or "Veritas-Investigation-Data/1.0"}
    request = Request(artifact.url, headers=headers)
    client = transport or UrllibTransport(source.allowed_hosts)

    temp_name: str | None = None
    try:
        with client.open(request, timeout=timeout) as response:
            resolved_url = response.geturl()
            _assert_allowed_url(resolved_url, source.allowed_hosts)
            content_length = _content_length(response.headers)
            if content_length is not None and content_length > max_bytes:
                raise AcquisitionError(
                    f"artifact Content-Length {content_length} exceeds max_bytes={max_bytes}"
                )
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=target_dir, prefix=f".{filename}.", suffix=".part", delete=False
            ) as tmp:
                temp_name = tmp.name
                output = cast(BinaryIO, tmp.file)
                digest, byte_count = _stream_and_hash(response, output, max_bytes=max_bytes)

            if artifact.expected_sha256 and digest != artifact.expected_sha256:
                raise AcquisitionError(
                    f"checksum mismatch for {artifact.artifact_id}: expected "
                    f"{artifact.expected_sha256}, got {digest}"
                )
            os.replace(temp_name, target_path)
            temp_name = None
            receipt = ArtifactReceipt.now(
                source_id=source.source_id,
                artifact_id=artifact.artifact_id,
                source_url=artifact.url,
                resolved_url=resolved_url,
                sha256=digest,
                byte_count=byte_count,
                content_type=_header_get(response.headers, "Content-Type"),
                local_path=str(target_path.relative_to(root)),
                catalog_sha256=catalog_digest(catalog_path),
                rights_review_id=rights_review_id,
            )
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)

    receipt_path.write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def verify_receipt(root: Path, receipt: ArtifactReceipt) -> bool:
    path = (root.resolve() / receipt.local_path).resolve()
    if root.resolve() not in path.parents:
        raise AcquisitionError("receipt path escaped acquisition root")
    if not path.is_file() or path.stat().st_size != receipt.byte_count:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == receipt.sha256


def _find_artifact(source: SourceSpec, artifact_id: str) -> AcquisitionArtifact:
    for artifact in source.artifacts:
        if artifact.artifact_id == artifact_id:
            return artifact
    raise AcquisitionError(f"unknown artifact_id {artifact_id!r} for source {source.source_id!r}")


def _assert_allowed_url(url: str, allowed_hosts: tuple[str, ...]) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise AcquisitionError("resolved URL must use HTTPS")
    if not any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts):
        raise AcquisitionError(f"resolved host {host!r} is not allowlisted")


def _stream_and_hash(
    response: HTTPResponse, output: BinaryIO, *, max_bytes: int
) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise AcquisitionError(f"artifact exceeded max_bytes={max_bytes} while streaming")
        digest.update(chunk)
        output.write(chunk)
    output.flush()
    os.fsync(output.fileno())
    return digest.hexdigest(), total


def _header_get(headers: object, key: str) -> str | None:
    getter = getattr(headers, "get", None)
    return getter(key) if callable(getter) else None


def _content_length(headers: object) -> int | None:
    raw = _header_get(headers, "Content-Length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


_SAFE_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}")
