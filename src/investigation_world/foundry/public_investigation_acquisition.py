from __future__ import annotations

import collections.abc
import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.public_investigation_data import (
    PublicInvestigationDataset,
    PublicSourceDefinition,
    PublicSourceRegistry,
    SourceArtifact,
)


_EXTERNAL_MEDIA_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be"}
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")
_MEDIA_SUFFIXES = {
    "application/json": ".json",
    "application/pdf": ".pdf",
    "application/xml": ".xml",
    "audio/mpeg": ".mp3",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "text/csv": ".csv",
    "text/html": ".html",
    "text/plain": ".txt",
}


class MaterializedArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    source_url: str
    local_path: str | None = None
    media_type: str
    sha256: str | None = None
    byte_count: int = Field(default=0, ge=0)
    reference_only: bool = False


class MaterializedCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    source_id: str
    public_artifacts: list[MaterializedArtifact] = Field(default_factory=list)
    verifier_artifacts: list[MaterializedArtifact] = Field(default_factory=list)


class DatasetMaterializationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    dataset_version: str
    source_registry_id: str
    cases: list[MaterializedCase]
    public_artifacts_downloaded: int = Field(default=0, ge=0)
    verifier_artifacts_downloaded: int = Field(default=0, ge=0)
    reference_only_artifacts: int = Field(default=0, ge=0)


ArtifactFetcher = collections.abc.Callable[[SourceArtifact, set[str], float, int], bytes]


def validate_dataset_registry(
    dataset: PublicInvestigationDataset,
    registry: PublicSourceRegistry,
) -> dict[str, PublicSourceDefinition]:
    if dataset.source_registry_id != registry.registry_id:
        raise ValueError(
            "dataset source_registry_id does not match the supplied source registry"
        )
    sources = {source.source_id: source for source in registry.sources}
    unknown = sorted({case.source_id for case in dataset.cases} - set(sources))
    if unknown:
        raise ValueError(f"dataset references unknown source ids: {unknown}")
    return sources


def _host(value: str) -> str:
    return (urllib.parse.urlparse(value).hostname or "").casefold()


def _require_https(value: str, *, artifact_id: str, context: str) -> None:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme.casefold() != "https":
        raise ValueError(
            f"{context} for {artifact_id} must use https, got {parsed.scheme!r}"
        )


def _allowed_hosts(source: PublicSourceDefinition) -> set[str]:
    candidates = [source.index_url, source.bulk_url, source.media_index_url]
    allowed = {_host(str(value)) for value in candidates if value is not None}
    for template in (source.case_url_template, source.docket_url_template):
        if template:
            allowed.add(_host(template.replace("{case_id}", "case")))
    return {host for host in allowed if host}


def _is_reference_only(artifact: SourceArtifact) -> bool:
    return artifact.media_type.casefold() in {"video/youtube"}


def _safe_component(value: str) -> str:
    cleaned = _SAFE_COMPONENT.sub("-", value).strip(".-")
    if not cleaned:
        raise ValueError("artifact identifiers must contain a safe filename component")
    return cleaned


def _suffix_for(artifact: SourceArtifact) -> str:
    suffix = _MEDIA_SUFFIXES.get(artifact.media_type.casefold())
    if suffix:
        return suffix
    path_suffix = Path(urllib.parse.urlparse(str(artifact.url)).path).suffix
    if path_suffix and len(path_suffix) <= 10:
        return path_suffix.casefold()
    return ".bin"


def fetch_artifact_bytes(
    artifact: SourceArtifact,
    allowed_hosts: set[str],
    timeout_seconds: float,
    max_bytes: int,
) -> bytes:
    source_url = str(artifact.url)
    _require_https(source_url, artifact_id=artifact.artifact_id, context="artifact URL")
    source_host = _host(source_url)
    if source_host not in allowed_hosts:
        raise ValueError(
            f"artifact host {source_host!r} is not authorized for {artifact.artifact_id}"
        )
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "VeritasPublicInvestigationDataset/1.0"},
    )
    # B310 is mitigated by HTTPS-only URLs plus registry host allowlisting
    # before and after redirects.
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
        final_url = response.geturl()
        _require_https(
            final_url, artifact_id=artifact.artifact_id, context="artifact redirect URL"
        )
        final_host = _host(final_url)
        if final_host not in allowed_hosts:
            raise ValueError(
                f"artifact redirect host {final_host!r} is not authorized for "
                f"{artifact.artifact_id}"
            )
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError(
            f"artifact {artifact.artifact_id} exceeds max_bytes={max_bytes}"
        )
    return payload


def _materialize_artifact(
    artifact: SourceArtifact,
    *,
    root: Path,
    source_id: str,
    case_id: str,
    allowed_hosts: set[str],
    fetcher: ArtifactFetcher,
    timeout_seconds: float,
    max_bytes: int,
) -> MaterializedArtifact:
    source_url = str(artifact.url)
    _require_https(source_url, artifact_id=artifact.artifact_id, context="artifact URL")
    source_host = _host(source_url)
    if _is_reference_only(artifact):
        if source_host not in allowed_hosts | _EXTERNAL_MEDIA_HOSTS:
            raise ValueError(
                f"reference host {source_host!r} is not authorized for {artifact.artifact_id}"
            )
        return MaterializedArtifact(
            artifact_id=artifact.artifact_id,
            source_url=str(artifact.url),
            media_type=artifact.media_type,
            reference_only=True,
        )
    if source_host not in allowed_hosts:
        raise ValueError(
            f"artifact host {source_host!r} is not authorized for {artifact.artifact_id}"
        )

    payload = fetcher(artifact, allowed_hosts, timeout_seconds, max_bytes)
    digest = hashlib.sha256(payload).hexdigest()
    relative_path = (
        Path(_safe_component(source_id))
        / _safe_component(case_id)
        / f"{_safe_component(artifact.artifact_id)}{_suffix_for(artifact)}"
    )
    destination = root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return MaterializedArtifact(
        artifact_id=artifact.artifact_id,
        source_url=str(artifact.url),
        local_path=relative_path.as_posix(),
        media_type=artifact.media_type,
        sha256=digest,
        byte_count=len(payload),
    )


def materialize_public_investigation_dataset(
    dataset: PublicInvestigationDataset,
    registry: PublicSourceRegistry,
    *,
    public_root: Path,
    verifier_root: Path | None = None,
    fetcher: ArtifactFetcher = fetch_artifact_bytes,
    timeout_seconds: float = 30.0,
    max_bytes: int = 256 * 1024 * 1024,
) -> DatasetMaterializationResult:
    sources = validate_dataset_registry(dataset, registry)
    public_root.mkdir(parents=True, exist_ok=True)
    if verifier_root is not None:
        verifier_root.mkdir(parents=True, exist_ok=True)

    materialized_cases: list[MaterializedCase] = []
    public_downloaded = 0
    verifier_downloaded = 0
    reference_only = 0

    for case in dataset.cases:
        source = sources[case.source_id]
        allowed = _allowed_hosts(source)
        public_items: list[MaterializedArtifact] = []
        verifier_items: list[MaterializedArtifact] = []

        for artifact in case.public_evidence:
            item = _materialize_artifact(
                artifact,
                root=public_root,
                source_id=case.source_id,
                case_id=case.case_id,
                allowed_hosts=allowed,
                fetcher=fetcher,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
            )
            public_items.append(item)
            if item.reference_only:
                reference_only += 1
            else:
                public_downloaded += 1

        if verifier_root is not None:
            for artifact in case.verifier_references:
                item = _materialize_artifact(
                    artifact,
                    root=verifier_root,
                    source_id=case.source_id,
                    case_id=case.case_id,
                    allowed_hosts=allowed,
                    fetcher=fetcher,
                    timeout_seconds=timeout_seconds,
                    max_bytes=max_bytes,
                )
                verifier_items.append(item)
                if item.reference_only:
                    reference_only += 1
                else:
                    verifier_downloaded += 1

        materialized_cases.append(
            MaterializedCase(
                case_id=case.case_id,
                source_id=case.source_id,
                public_artifacts=public_items,
                verifier_artifacts=verifier_items,
            )
        )

    result = DatasetMaterializationResult(
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        source_registry_id=dataset.source_registry_id,
        cases=materialized_cases,
        public_artifacts_downloaded=public_downloaded,
        verifier_artifacts_downloaded=verifier_downloaded,
        reference_only_artifacts=reference_only,
    )
    public_inventory = {
        "dataset_id": result.dataset_id,
        "dataset_version": result.dataset_version,
        "source_registry_id": result.source_registry_id,
        "cases": [
            {
                "case_id": case.case_id,
                "source_id": case.source_id,
                "public_artifacts": [
                    item.model_dump(mode="json") for item in case.public_artifacts
                ],
            }
            for case in result.cases
        ],
        "public_artifacts_downloaded": result.public_artifacts_downloaded,
        "reference_only_artifacts": result.reference_only_artifacts,
    }
    inventory = public_root / "materialization.json"
    inventory.write_text(
        json.dumps(public_inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if verifier_root is not None:
        verifier_inventory = verifier_root / "materialization.json"
        verifier_inventory.write_text(
            json.dumps(
                {
                    "dataset_id": result.dataset_id,
                    "dataset_version": result.dataset_version,
                    "source_registry_id": result.source_registry_id,
                    "cases": [
                        {
                            "case_id": case.case_id,
                            "source_id": case.source_id,
                            "verifier_artifacts": [
                                item.model_dump(mode="json")
                                for item in case.verifier_artifacts
                            ],
                        }
                        for case in result.cases
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return result
