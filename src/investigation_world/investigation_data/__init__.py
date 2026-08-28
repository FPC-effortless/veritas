"""Acquisition and normalization primitives for high-stakes investigation datasets."""

from .catalog import catalog_digest, find_source, load_catalog
from .models import (
    InvestigationEpisodeBundle,
    PrivateInvestigationOracle,
    PublicInvestigationEpisode,
    SourceCatalog,
    SourceSpec,
)
from .serialization import write_episode_bundle

__all__ = [
    "InvestigationEpisodeBundle",
    "PrivateInvestigationOracle",
    "PublicInvestigationEpisode",
    "SourceCatalog",
    "SourceSpec",
    "catalog_digest",
    "find_source",
    "load_catalog",
    "write_episode_bundle",
]
