from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from investigation_world.portability.models import (
    PortableEnvironmentManifest,
    PortableSplit,
    PortableVisibility,
)


@dataclass(frozen=True)
class PortabilityValidationIssue:
    code: str
    detail: str


def validate_portable_manifest(manifest: PortableEnvironmentManifest) -> list[PortabilityValidationIssue]:
    issues: list[PortabilityValidationIssue] = []

    if not manifest.reset.deterministic:
        issues.append(
            PortabilityValidationIssue(
                code="reset_not_deterministic",
                detail="portable environments must declare deterministic reset semantics",
            )
        )
    if not manifest.verifier.deterministic:
        issues.append(
            PortabilityValidationIssue(
                code="verifier_not_deterministic",
                detail="portable commercial verifiers must be deterministic",
            )
        )

    if manifest.visibility != PortableVisibility.PRIVATE_OPERATOR:
        if manifest.taskset.private_task_ids_included:
            issues.append(
                PortabilityValidationIssue(
                    code="private_task_ids_exposed",
                    detail="buyer-safe/public manifests must not include private task identities",
                )
            )
        if manifest.taskset.private_ground_truth_included:
            issues.append(
                PortabilityValidationIssue(
                    code="private_ground_truth_exposed",
                    detail="buyer-safe/public manifests must not include private ground truth",
                )
            )
        if any(task.split == PortableSplit.PRIVATE_TEST for task in manifest.taskset.visible_tasks):
            issues.append(
                PortabilityValidationIssue(
                    code="private_tasks_visible",
                    detail="buyer-safe/public manifests must not contain private-test task rows",
                )
            )
        private_artifacts = [
            artifact.artifact_id
            for artifact in manifest.artifacts
            if artifact.visibility == PortableVisibility.PRIVATE_OPERATOR
        ]
        if private_artifacts:
            issues.append(
                PortabilityValidationIssue(
                    code="private_artifacts_exposed",
                    detail=f"buyer-safe/public manifest references private artifacts: {private_artifacts}",
                )
            )

    for dependency in manifest.dependencies:
        lowered = dependency.casefold()
        if "file://" in lowered or lowered.startswith(("/", "~", "../", "./")):
            issues.append(
                PortabilityValidationIssue(
                    code="local_dependency",
                    detail=f"portable dependency is local-path bound: {dependency}",
                )
            )

    for artifact in manifest.artifacts:
        if artifact.path_hint:
            path = PurePosixPath(artifact.path_hint)
            if path.is_absolute() or ".." in path.parts:
                issues.append(
                    PortabilityValidationIssue(
                        code="unsafe_artifact_path",
                        detail=f"artifact path must remain package-relative: {artifact.path_hint}",
                    )
                )

    return issues


def require_portable_manifest(manifest: PortableEnvironmentManifest) -> PortableEnvironmentManifest:
    issues = validate_portable_manifest(manifest)
    if issues:
        rendered = "; ".join(f"{issue.code}: {issue.detail}" for issue in issues)
        raise ValueError(f"portable manifest failed validation: {rendered}")
    return manifest


def require_no_forbidden_tokens(texts: Iterable[str], forbidden_tokens: Iterable[str]) -> None:
    material = "\n".join(texts)
    leaked = sorted(token for token in forbidden_tokens if token and token in material)
    if leaked:
        raise ValueError(f"portable buyer-safe export contains forbidden tokens: {leaked}")
