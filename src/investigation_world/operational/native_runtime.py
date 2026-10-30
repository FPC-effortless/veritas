from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from investigation_world.operational.artifacts import (
    NativeArtifactVerification,
    attach_native_artifact_descriptor,
)
from investigation_world.operational.models import (
    EpisodeSubmission,
    StateAssertion,
    VerificationBreakdown,
)
from investigation_world.operational.native_submission import (
    NATIVE_ARTIFACT_SOURCES,
    NativeSubmissionReceipt,
    canonical_native_json,
    native_source_identities,
)
from investigation_world.operational.parameterized_artifacts import (
    ParameterizedNativeArtifactWorkspace,
)
from investigation_world.operational.runtime import OperationalRuntime
from investigation_world.operational.substrate import PersistentOperationalSubstrate


class NativeOperationalRuntime(OperationalRuntime):
    """OperationalRuntime with a lazily materialized native domain artifact.

    Public actions and the seven verification dimensions are unchanged. Successful
    transitions are mirrored into XLSX, SQLite, declarative Kubernetes, rendered
    evidence-corpus, or GeoJSON artifacts. Native verifier checks are injected as
    additional state assertions before the ordinary Veritas verifier runs.

    The workspace derives artifact state from each episode's actual target/oracle
    values, so procedurally parameterized cases remain executable rather than
    falling back to constants from the reference examples.
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
        self.artifact_workspace = ParameterizedNativeArtifactWorkspace(episode, artifact_root)
        self.last_artifact_verification: NativeArtifactVerification | None = None
        self.last_native_submission: NativeSubmissionReceipt | None = None
        self._native_initial_state_json = canonical_native_json(self.state_snapshot())

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
        if native_source_identities() != NATIVE_ARTIFACT_SOURCES:
            raise ValueError("native verifier source identity mismatch")
        episode_json = canonical_native_json(self.episode.model_dump(mode="json"))
        pre_state_json = canonical_native_json(self.state_snapshot())
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

        if self.substrate is not None:
            self.substrate.apply_changes(
                world_id=self.episode.world_id,
                domain=self.episode.task.domain,
                actor="verifier",
                action_name="verify_native_artifact",
                changes={
                    f"native_artifact.{check}": bool(passed)
                    for check, passed in sorted(artifact_result.checks.items())
                },
            )

        result = super().submit(submission)
        failed = sorted(check for check, passed in artifact_result.checks.items() if not passed)
        result.process_violations.extend(f"native_artifact:{check}" for check in failed)
        self.last_native_submission = NativeSubmissionReceipt(
            artifact_path=str(self.artifact_workspace.path.resolve()),
            episode_json=episode_json,
            initial_state_json=self._native_initial_state_json,
            pre_state_json=pre_state_json,
            final_state_json=canonical_native_json(self.state_snapshot()),
            action_events_json=canonical_native_json(self.trace()),
            submission_json=canonical_native_json(submission.model_dump(mode="json")),
            verification_json=canonical_native_json(artifact_result.model_dump(mode="json")),
            descriptor_json=canonical_native_json(self.artifact_descriptor()),
            tool_calls=self.budget.calls,
            cost_spent=self.budget.spent,
        )
        return result
