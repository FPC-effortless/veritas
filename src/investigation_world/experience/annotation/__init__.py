"""Deterministic semantic annotations over canonical MachineExperience trajectories."""

from .compiler import (
    SemanticAnnotationError,
    apply_semantic_annotations,
    compile_semantic_annotations,
)
from .models import (
    SEMANTIC_ANNOTATION_SCHEMA,
    AuthorityAnnotation,
    BudgetImpactAnnotation,
    EvidenceFlowAnnotation,
    InvariantEffectAnnotation,
    InvocationAnnotation,
    ProcessRequirementAnnotation,
    ResourceChargeAnnotation,
    SemanticAnnotationBundle,
    SemanticDerivationStatus,
    SemanticEventAnnotation,
    SemanticInvocationKind,
    StateTransitionAnnotation,
    VerifierRelevanceAnnotation,
)

__all__ = [
    "SEMANTIC_ANNOTATION_SCHEMA",
    "AuthorityAnnotation",
    "BudgetImpactAnnotation",
    "EvidenceFlowAnnotation",
    "InvariantEffectAnnotation",
    "InvocationAnnotation",
    "ProcessRequirementAnnotation",
    "ResourceChargeAnnotation",
    "SemanticAnnotationBundle",
    "SemanticAnnotationError",
    "SemanticDerivationStatus",
    "SemanticEventAnnotation",
    "SemanticInvocationKind",
    "StateTransitionAnnotation",
    "VerifierRelevanceAnnotation",
    "apply_semantic_annotations",
    "compile_semantic_annotations",
]
