from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from investigation_world.core.models import InvestigationResult
from investigation_world.foundry.expert_trajectories import VerifiedTrajectory
from investigation_world.foundry.models import RolloutTrace, stable_hash
from investigation_world.foundry.training_product import (
    TrainerAdapter,
    TrainerKind,
    TrainingBundle,
    TrainingRunManifest,
    TrainingRunResult,
)


def _trace_payload(trajectory: VerifiedTrajectory) -> dict[str, Any]:
    return trajectory.trace.model_dump(mode="json")


def _submitted_result(trace: RolloutTrace) -> dict[str, Any] | None:
    for event in reversed(trace.events):
        if event.event_type != "submit":
            continue
        args = event.payload.get("args", [])
        if isinstance(args, list) and args:
            return InvestigationResult.model_validate(args[0]).model_dump(mode="json")
    return None


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


class ArtifactTrainerAdapter(TrainerAdapter):
    """Materialize deterministic trainer inputs without coupling Veritas to a framework."""

    trainer_kind: TrainerKind

    def __init__(
        self,
        output_dir: str | Path,
        trajectories: list[VerifiedTrajectory],
    ):
        self.output_dir = Path(output_dir)
        self.trajectories = {
            trajectory.trajectory_id: trajectory for trajectory in trajectories
        }

    def _trajectory(self, trajectory_id: str) -> VerifiedTrajectory:
        try:
            return self.trajectories[trajectory_id]
        except KeyError as error:
            raise ValueError(
                f"training bundle references unavailable trajectory {trajectory_id}"
            ) from error

    def _training_rows(self, bundle: TrainingBundle) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for example in bundle.train_examples:
            trajectory = self._trajectory(example.trajectory_id)
            rows.append(self._row(bundle, trajectory, example.model_dump(mode="json")))
        return rows

    def _row(
        self,
        bundle: TrainingBundle,
        trajectory: VerifiedTrajectory,
        example: dict[str, Any],
    ) -> dict[str, Any]:
        public_task = trajectory.annotations.get("public_task")
        trace = _trace_payload(trajectory)
        base = {
            "example_id": example["example_id"],
            "trajectory_id": trajectory.trajectory_id,
            "task_id": trajectory.task_id,
            "capability_tags": trajectory.capability_tags,
            "public_task": public_task,
            "verifier_score": trajectory.assessment.verifier_score,
        }
        if self.trainer_kind == TrainerKind.SFT:
            return {
                **base,
                "trajectory": trace,
                "target_result": _submitted_result(trajectory.trace),
            }
        if self.trainer_kind == TrainerKind.RL:
            return {
                **base,
                "rollout": trace,
                "reward": trajectory.trace.total_reward,
                "verifier_components": trajectory.trace.verifier_components,
            }
        if self.trainer_kind == TrainerKind.VOPSD:
            structural_steps = []
            for event in trajectory.trace.events:
                if event.event_type == "submit":
                    continue
                structural_steps.append(
                    {
                        "step": event.step,
                        "operation": event.event_type,
                        "action": {
                            "args": event.payload.get("args", []),
                            "kwargs": event.payload.get("kwargs", {}),
                        },
                        "observation": event.payload.get("result"),
                        "state_hash_before": event.state_hash_before,
                        "state_hash_after": event.state_hash_after,
                        "cost": event.cost,
                    }
                )
            return {
                **base,
                "on_policy_trace": trace,
                "structural_steps": structural_steps,
                "teacher_structural_guidance": trajectory.annotations.get(
                    "teacher_structural_guidance",
                    [],
                ),
                "independent_verification": {
                    "components": trajectory.trace.verifier_components,
                    "reward": trajectory.trace.total_reward,
                    "invariant_pass": trajectory.assessment.invariant_pass,
                    "terminal_success": trajectory.assessment.terminal_success,
                },
                "training_rule": (
                    "teacher structural guidance is advisory; independently verified "
                    "outcomes and invariants are authoritative"
                ),
            }
        raise ValueError(
            f"{self.trainer_kind.value} requires trainer-specific row generation"
        )

    def _preference_rows(self, bundle: TrainingBundle) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for example in bundle.preference_examples:
            chosen = self._trajectory(example.chosen_trajectory_id)
            rejected = self._trajectory(example.rejected_trajectory_id)
            rows.append(
                {
                    "example_id": example.example_id,
                    "pair_id": example.pair_id,
                    "task_id": example.task_id,
                    "capability_tags": example.capability_tags,
                    "public_task": chosen.annotations.get("public_task"),
                    "chosen": _trace_payload(chosen),
                    "rejected": _trace_payload(rejected),
                    "chosen_verifier_score": chosen.assessment.verifier_score,
                    "rejected_verifier_score": rejected.assessment.verifier_score,
                    "score_margin": example.score_margin,
                }
            )
        return rows

    def run(
        self,
        bundle: TrainingBundle,
        manifest: TrainingRunManifest,
    ) -> TrainingRunResult:
        if bundle.recipe.trainer != self.trainer_kind:
            raise ValueError(
                f"adapter {self.trainer_kind.value} cannot run {bundle.recipe.trainer.value} bundle"
            )
        if manifest.trainer != self.trainer_kind:
            raise ValueError("training run manifest trainer does not match adapter")
        if manifest.bundle_id != bundle.bundle_id:
            raise ValueError("training run manifest bundle_id does not match bundle")

        run_dir = self.output_dir / manifest.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        rows = (
            self._preference_rows(bundle)
            if self.trainer_kind == TrainerKind.PREFERENCE
            else self._training_rows(bundle)
        )
        training_path = run_dir / "training.jsonl"
        heldout_path = run_dir / "heldout.json"
        bundle_path = run_dir / "bundle.json"
        manifest_path = run_dir / "run_manifest.json"
        artifact_manifest_path = run_dir / "artifact_manifest.json"

        _write_jsonl(training_path, rows)
        _write_json(heldout_path, bundle.heldout_trajectory_ids)
        _write_json(bundle_path, bundle.model_dump(mode="json"))
        _write_json(manifest_path, manifest.model_dump(mode="json"))

        content = {
            "format": "veritas-training-artifact-v1",
            "trainer": self.trainer_kind.value,
            "run_id": manifest.run_id,
            "bundle_id": bundle.bundle_id,
            "training_data": str(training_path),
            "heldout": str(heldout_path),
            "bundle": str(bundle_path),
            "run_manifest": str(manifest_path),
            "training_examples": len(rows),
            "heldout_trajectories": len(bundle.heldout_trajectory_ids),
            "rejected_trajectories": len(bundle.rejected_trajectory_ids),
        }
        content["content_hash"] = stable_hash(content)
        _write_json(artifact_manifest_path, content)

        return TrainingRunResult(
            manifest=manifest,
            artifact_ref=str(artifact_manifest_path),
            metrics={
                "training_examples": float(len(rows)),
                "heldout_trajectories": float(len(bundle.heldout_trajectory_ids)),
                "rejected_trajectories": float(len(bundle.rejected_trajectory_ids)),
            },
            metadata={
                "training_data": str(training_path),
                "heldout": str(heldout_path),
                "bundle": str(bundle_path),
                "artifact_content_hash": content["content_hash"],
                "framework_execution": False,
            },
        )


class SFTTrainerAdapter(ArtifactTrainerAdapter):
    trainer_kind = TrainerKind.SFT


class PreferenceTrainerAdapter(ArtifactTrainerAdapter):
    trainer_kind = TrainerKind.PREFERENCE


class RLTrainerAdapter(ArtifactTrainerAdapter):
    trainer_kind = TrainerKind.RL


class VOPSDTrainerAdapter(ArtifactTrainerAdapter):
    trainer_kind = TrainerKind.VOPSD


class ExternalCommandTrainerAdapter(TrainerAdapter):
    """Run an explicit external trainer against a deterministic Veritas artifact.

    The command is executed with ``shell=False`` and receives only artifact paths and
    run metadata through environment variables. Veritas never interpolates a shell string.
    """

    def __init__(
        self,
        artifact_adapter: ArtifactTrainerAdapter,
        command: list[str],
        *,
        cwd: str | Path | None = None,
        environment: dict[str, str] | None = None,
    ):
        if not command:
            raise ValueError("external trainer command cannot be empty")
        self.artifact_adapter = artifact_adapter
        self.command = list(command)
        self.cwd = Path(cwd) if cwd is not None else None
        self.environment = dict(environment or {})

    def run(
        self,
        bundle: TrainingBundle,
        manifest: TrainingRunManifest,
    ) -> TrainingRunResult:
        artifact = self.artifact_adapter.run(bundle, manifest)
        if artifact.artifact_ref is None:
            raise RuntimeError("artifact adapter did not produce an artifact manifest")
        artifact_manifest = Path(artifact.artifact_ref)
        training_data = str(artifact.metadata["training_data"])
        run_manifest = str(artifact_manifest.parent / "run_manifest.json")
        log_path = artifact_manifest.parent / "trainer.log"

        environment = {
            **os.environ,
            **self.environment,
            "VERITAS_TRAINING_ARTIFACT": str(artifact_manifest),
            "VERITAS_TRAINING_DATA": training_data,
            "VERITAS_RUN_MANIFEST": run_manifest,
            "VERITAS_TRAINER_KIND": manifest.trainer.value,
        }
        completed = subprocess.run(
            self.command,
            cwd=str(self.cwd) if self.cwd is not None else None,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        log_path.write_text(
            "STDOUT\n" + completed.stdout + "\nSTDERR\n" + completed.stderr,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"external trainer failed with exit code {completed.returncode}; log={log_path}"
            )
        return artifact.model_copy(
            update={
                "logs_ref": str(log_path),
                "metadata": {
                    **artifact.metadata,
                    "framework_execution": True,
                    "command": list(self.command),
                    "returncode": completed.returncode,
                },
            }
        )


def trainer_adapter_for(
    trainer: TrainerKind,
    output_dir: str | Path,
    trajectories: list[VerifiedTrajectory],
) -> ArtifactTrainerAdapter:
    adapters: dict[TrainerKind, type[ArtifactTrainerAdapter]] = {
        TrainerKind.SFT: SFTTrainerAdapter,
        TrainerKind.PREFERENCE: PreferenceTrainerAdapter,
        TrainerKind.RL: RLTrainerAdapter,
        TrainerKind.VOPSD: VOPSDTrainerAdapter,
    }
    return adapters[trainer](output_dir, trajectories)
