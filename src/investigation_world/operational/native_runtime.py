from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from investigation_world.operational.artifacts import (
    NativeArtifactVerification,
    NativeArtifactWorkspace,
    attach_native_artifact_descriptor,
)
from investigation_world.operational.models import EpisodeSubmission, StateAssertion, VerificationBreakdown
from investigation_world.operational.runtime import OperationalRuntime
from investigation_world.operational.substrate import PersistentOperationalSubstrate


class NativeOperationalRuntime(OperationalRuntime):
    """OperationalRuntime with a lazily materialized native domain artifact.

    Public actions and the seven verification dimensions are unchanged. Successful
    transitions are mirrored into XLSX, SQLite, declarative Kubernetes, rendered
    evidence-corpus, or GeoJSON artifacts. Native verifier checks are injected as
    additional state assertions before the ordinary Veritas verifier runs.
    """

    def __init__(
        self,
        episode,
        *,
        artifact_root: str | Path | None = None,
        substrate: PersistentOperationalSubstrate | None = None,
    ):
        attach_native_artifact_descriptor(episode)
        super().__init__(episode, substrate=substrate)
        if artifact_root is None:
            artifact_root = tempfile.mkdtemp(prefix="veritas-native-")
        self.artifact_workspace = NativeArtifactWorkspace(episode, artifact_root)
        self.last_artifact_verification: NativeArtifactVerification | None = None

    def artifact_descriptor(self) -> dict[str, Any]:
        return self.artifact_workspace.descriptor.model_dump(mode="json")

    def materialize_artifact(self) -> Path:
        return self.artifact_workspace.materialize()

    def artifact_verification(self) -> NativeArtifactVerification:
        if self.last_artifact_verification is not None:
            return self.last_artifact_verification
        return self.artifact_workspace.verify()

    def act(self, action_name: str, **parameters: Any) -> dict[str, Any]:
        result = super().act(action_name, **parameters)
        event = self.events[-1]
        if event.effect_applied and not event.blocked:
            self.artifact_workspace.apply_action(action_name, parameters)
        return result

    def submit(self, submission: EpisodeSubmission) -> VerificationBreakdown:
        self._ensure_open()
        artifact_result = self.artifact_workspace.verify()
        self.last_artifact_verification = artifact_result

        existing = {assertion.key() for assertion in self.episode.oracle.target_state}
        for check, passed in sorted(artifact_result.checks.items()):
            key = f"native_artifact.{check}"
            self.state[key] = bool(passed)
            if key not in existing:
                self.episode.oracle.target_state.append(
                    StateAssertion(
                        object_id="native_artifact",
                        field_name=check,
                        expected_value=True,
                    )
                )

        result = super().submit(submission)
        failed = sorted(check for check, passed in artifact_result.checks.items() if not passed)
        result.process_violations.extend(f"native_artifact:{check}" for check in failed)
        return result
