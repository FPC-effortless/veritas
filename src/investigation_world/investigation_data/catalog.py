from __future__ import annotations

import hashlib
from importlib.resources import files
from pathlib import Path

from .models import SourceCatalog, SourceSpec


def default_catalog_path() -> Path:
    resource = files(__package__).joinpath("source_catalog.json")
    return Path(str(resource))


def load_catalog(path: Path | None = None) -> SourceCatalog:
    catalog_path = path or default_catalog_path()
    return SourceCatalog.model_validate_json(catalog_path.read_text(encoding="utf-8"))


def catalog_digest(path: Path | None = None) -> str:
    catalog_path = path or default_catalog_path()
    return hashlib.sha256(catalog_path.read_bytes()).hexdigest()


def find_source(catalog: SourceCatalog, source_id: str) -> SourceSpec:
    for source in catalog.sources:
        if source.source_id == source_id:
            return source
    raise KeyError(f"unknown source_id: {source_id}")
