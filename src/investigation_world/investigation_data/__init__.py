"""Acquisition, preparation, and evidence-fusion primitives for investigation datasets."""

from .catalog import catalog_digest, find_source, load_catalog
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
    DocumentPageExposure,
    DocumentPreparationPlan,
    DocumentPreparationResult,
    DocumentSliceSpec,
    InvestigationEpisodeBundle,
    PageRange,
    PreparedDocumentSlice,
    PrivateInvestigationOracle,
    PublicInvestigationEpisode,
    SourceCatalog,
    SourceSpec,
)
from .preparation import prepare_document_artifact
from .serialization import write_episode_bundle

__all__ = [
    "DerivationKind",
    "DocumentPageExposure",
    "DocumentPreparationPlan",
    "DocumentPreparationResult",
    "DocumentSliceSpec",
    "EpistemicRole",
    "EvidenceFragment",
    "EvidenceModality",
    "EvidenceRelation",
    "FusionError",
    "FusionManifest",
    "FusionReport",
    "FusionResult",
    "InvestigationEpisodeBundle",
    "PageRange",
    "PreparedDocumentSlice",
    "PrivateInvestigationOracle",
    "PublicInvestigationEpisode",
    "SourceCatalog",
    "SourceSpec",
    "catalog_digest",
    "find_source",
    "fuse_manifest",
    "load_catalog",
    "manifest_digest",
    "prepare_document_artifact",
    "validate_fusion_sources",
    "write_episode_bundle",
]
