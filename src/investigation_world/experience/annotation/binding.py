from __future__ import annotations

from investigation_world.portable_contract import PortableOperationalContract
from investigation_world.trajectory import TrajectoryV2

from .compiler import SemanticAnnotationError, apply_semantic_annotations
from .compiler import compile_semantic_annotations as _compile_semantic_annotations
from .models import SemanticAnnotationBundle


def compile_semantic_annotations(
    trajectory: TrajectoryV2,
    contract: PortableOperationalContract,
) -> SemanticAnnotationBundle:
    """Compile semantics only when the trace binds the exact full contract.

    TRACE-002 derives evaluator-private process, transition, invariant, budget, and
    verifier semantics. A public contract identity proves only public task/runtime
    semantics and therefore cannot authorize those private derivations.
    """

    reference = trajectory.world.portable_operational_contract
    if reference is None or reference.digest is None:
        raise SemanticAnnotationError(
            "semantic annotation requires trajectory binding to the exact full "
            "portable contract identity"
        )

    public_only_binding = (
        reference.digest == contract.public.public_id
        and reference.digest != contract.contract_id
    )
    if public_only_binding:
        raise SemanticAnnotationError(
            "public-only portable-contract binding cannot authorize evaluator-private "
            "semantic derivation"
        )

    if reference.digest != contract.contract_id:
        raise SemanticAnnotationError(
            "trajectory portable-contract digest does not match supplied full contract"
        )

    return _compile_semantic_annotations(trajectory, contract)


__all__ = [
    "SemanticAnnotationError",
    "apply_semantic_annotations",
    "compile_semantic_annotations",
]
