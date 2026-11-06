"""Acquisition, preparation, and evidence-fusion primitives for investigation datasets."""

from .catalog import catalog_digest, find_source, load_catalog
from .corpus import (
    CorpusCaseSpec,
    CorpusEvidenceRelease,
    FusionCorpusIndex,
    corpus_digest,
    load_fusion_corpus,
    validate_fusion_corpus_sources,
)
from .fusion import (
    DerivationKind,
    EpistemicRole,
    EvidenceFragment,
    EvidenceModality,
    EvidenceRelation,
    FusionError,
    FusionManifest,
    FusionReport,
    FusionResult,
    fuse_manifest,
    manifest_digest,
    validate_fusion_sources,
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
    "CorpusCaseSpec",
    "CorpusEvidenceRelease",
    "DerivationKind",
    "EpistemicRole",
    "EvidenceFragment",
    "EvidenceModality",
    "EvidenceRelation",
    "FusionCorpusIndex",
    "FusionError",
    "FusionManifest",
    "FusionReport",
    "FusionResult",
    "InvestigationEpisodeBundle",
    "PrivateInvestigationOracle",
    "PublicInvestigationEpisode",
    "SourceCatalog",
    "SourceSpec",
    "catalog_digest",
    "corpus_digest",
    "find_source",
    "fuse_manifest",
    "load_catalog",
    "load_fusion_corpus",
    "manifest_digest",
    "validate_fusion_corpus_sources",
    "validate_fusion_sources",
    "write_episode_bundle",
]
