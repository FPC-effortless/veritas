"""Acquisition, preparation, and evidence-fusion primitives for investigation datasets."""

from .catalog import catalog_digest, find_source, load_catalog
from .fusion import (
    DerivationKind,
    EpistemicRole,
    EvidenceFragment,
    EvidenceModality,
    EvidenceRelation,
    FusionManifest,
    FusionReport,
    FusionResult,
    fuse_manifest,
    manifest_digest,
)
from .models import (
    InvestigationEpisodeBundle,
    PrivateInvestigationOracle,
    PublicInvestigationEpisode,
    SourceCatalog,
    SourceSpec,
)
from .serialization import write_episode_bundle

__all__ = [
    "DerivationKind",
    "EpistemicRole",
    "EvidenceFragment",
    "EvidenceModality",
    "EvidenceRelation",
    "FusionManifest",
    "FusionReport",
    "FusionResult",
    "InvestigationEpisodeBundle",
    "PrivateInvestigationOracle",
    "PublicInvestigationEpisode",
    "SourceCatalog",
    "SourceSpec",
    "catalog_digest",
    "find_source",
    "fuse_manifest",
    "load_catalog",
    "manifest_digest",
    "write_episode_bundle",
]
