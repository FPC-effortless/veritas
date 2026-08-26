from investigation_world.projectworld.construction import build_construction_project_world
from investigation_world.projectworld.models import (
    HiddenDefect,
    OperationalProjectWorldSpec,
    ProcurementOrder,
    ProjectAction,
    ProjectActionKind,
    ProjectDecisionOption,
    ProjectDecisionSpec,
    ProjectDomain,
    ProjectIssue,
    ProjectJournalEvent,
    ProjectObservation,
    ProjectOracle,
    ProjectPhase,
    ProjectRequirement,
    ProjectResourceSpec,
    ProjectRoleSpec,
    ProjectScenario,
    ProjectTransition,
    ProjectVerificationReport,
    ProjectWorkPackageSpec,
    ProjectWorldState,
    ResourceKind,
    WorkPackageStatus,
)
from investigation_world.projectworld.runtime import OperationalProjectWorld, ProjectActionError
from investigation_world.projectworld.verifier import verify_project_world


def build_project_world(
    domain: ProjectDomain | str = ProjectDomain.CONSTRUCTION,
    *,
    seed: int = 42,
) -> ProjectScenario:
    resolved = ProjectDomain(domain)
    if resolved == ProjectDomain.CONSTRUCTION:
        return build_construction_project_world(seed=seed)
    raise NotImplementedError(f"project domain not implemented yet: {resolved.value}")


__all__ = [
    "HiddenDefect",
    "OperationalProjectWorld",
    "OperationalProjectWorldSpec",
    "ProcurementOrder",
    "ProjectAction",
    "ProjectActionError",
    "ProjectActionKind",
    "ProjectDecisionOption",
    "ProjectDecisionSpec",
    "ProjectDomain",
    "ProjectIssue",
    "ProjectJournalEvent",
    "ProjectObservation",
    "ProjectOracle",
    "ProjectPhase",
    "ProjectRequirement",
    "ProjectResourceSpec",
    "ProjectRoleSpec",
    "ProjectScenario",
    "ProjectTransition",
    "ProjectVerificationReport",
    "ProjectWorkPackageSpec",
    "ProjectWorldState",
    "ResourceKind",
    "WorkPackageStatus",
    "build_construction_project_world",
    "build_project_world",
    "verify_project_world",
]
