"""Existing TrainingBundle compilation with a deliberately separate safe byte projection."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from investigation_world.experience_foundry.admission import (
    RecordedExperience,
    admit_experience,
)
from investigation_world.experience_foundry.public_profiles import (
    profile_fixture,
    profile_id_from_trace,
)
from investigation_world.foundry.models import DistributionSplit
from investigation_world.foundry.training_product import (
    TrainerKind,
    TrainingBundle,
    TrainingRecipe,
    compile_training_bundle,
)
from investigation_world.trajectory import canonical_hash
from investigation_world.trajectory.reverify import AuthorizedVerifierRegistry


@dataclass(frozen=True)
class VerifiedLearningBundle:
    bundle: TrainingBundle
    trainer_bytes: bytes
    provenance: tuple[dict[str, str], ...]


def _trainer_row(source: RecordedExperience) -> dict:
    # The exact source fixture was independently matched at admission. Arbitrary metadata,
    # private traces, digests, seed, episode IDs and evaluator annotations never enter here.
    profile_id = profile_id_from_trace(source.companion)
    case, _ = profile_fixture(profile_id)
    task = case.episode.task
    actions = {action.name: action for action in task.available_actions}
    calls = []
    for event in source.companion.events:
        if event.event_type != "act":
            continue
        name = event.payload["args"][0]
        if name not in actions:
            raise ValueError("UNSUPPORTED_PUBLIC_ACTION")
        parameters = event.payload["kwargs"]
        if set(parameters) - set(actions[name].parameter_names):
            raise ValueError("NONPUBLIC_ACTION_PARAMETER")
        calls.append({"action": name, "parameters": parameters})
    row: dict[str, Any] = {
        "prompt": {
            "objective": task.objective,
            "records": [
                {
                    "record_id": record.record_id,
                    "system": record.system,
                    "record_type": record.record_type,
                    "object_id": record.object_id,
                    "fields": record.fields,
                }
                for record in case.episode.records
            ],
            "available_actions": [
                {"name": action.name, "parameters": action.parameter_names}
                for action in task.available_actions
            ],
        },
        # SFT action-only sequence, not fabricated observations or a new result schema.
        "target": calls,
    }
    if profile_id is not None:
        row["prompt"]["constraints"] = list(task.constraints)
        for public, record in zip(row["prompt"]["records"], case.episode.records, strict=True):
            public["related_object_ids"] = list(record.related_object_ids)
    return row


def compile_verified_bundle(
    sources: list[RecordedExperience],
    recipe: TrainingRecipe,
    *,
    registry: AuthorizedVerifierRegistry,
    frozen_panel_task_ids: tuple[str, ...] = (),
    frozen_panel_source_digests: tuple[str, ...] = (),
) -> VerifiedLearningBundle:
    recipe = TrainingRecipe.model_validate(recipe.model_dump(mode="python"))
    if (
        recipe.trainer is not TrainerKind.SFT
        or recipe.train_splits != [DistributionSplit.TRAIN]
        or set(recipe.heldout_splits)
        != {DistributionSplit.IID_TEST, DistributionSplit.OOD, DistributionSplit.ADVERSARIAL}
        or len(recipe.heldout_splits) != 3
        or not recipe.require_invariant_pass
        or not recipe.require_verified_terminal_success
        or not math.isfinite(recipe.minimum_verifier_score)
        or not 0.8 <= recipe.minimum_verifier_score <= 1.0
        or recipe.parameters
    ):
        raise ValueError("RECIPE_WIDENS_OR_UNSUPPORTED_ADMISSION")
    if not sources:
        raise ValueError("EMPTY_TRAINING_INPUT")
    identities: set[str] = set()
    tasks: set[str] = set()
    admitted = []
    for source in sources:
        trajectory = source.experience.trajectory
        for identity in (
            source.experience.experience_id,
            trajectory.trajectory_id,
            source.companion.trace_id,
        ):
            if identity in identities:
                raise ValueError("DUPLICATE_TRAINING_IDENTITY")
            identities.add(identity)
        if trajectory.task.task_id in tasks:
            raise ValueError("DUPLICATE_TRAINING_TASK")
        tasks.add(trajectory.task.task_id)
        if trajectory.task.task_id in frozen_panel_task_ids:
            raise ValueError("FROZEN_PANEL_OVERLAP")
        checked = admit_experience(source, registry=registry)
        if checked.lineage["source_digest"] in frozen_panel_source_digests:
            raise ValueError("FROZEN_PANEL_SOURCE_OVERLAP")
        admitted.append(checked)
    capability = admitted[0].source.capability
    if any(item.source.capability != capability for item in admitted):
        raise ValueError("MIXED_CAPABILITY_CONTRACTS")
    bundle = compile_training_bundle(capability, recipe, [item.verified for item in admitted])
    if (
        len(bundle.train_examples) != len(sources)
        or bundle.preference_examples
        or bundle.heldout_trajectory_ids
        or bundle.rejected_trajectory_ids
    ):
        raise ValueError("EXISTING_COMPILER_REJECTED_ADMITTED_INPUT")
    # Evaluator-only lineage is bound by the receipt's full bundle digest.
    bundle.metadata["verified_learning_lineage"] = [dict(item.lineage) for item in admitted]
    rows = [_trainer_row(item.source) for item in admitted]
    trainer_bytes = (
        "".join(
            json.dumps(
                row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            )
            + "\n"
            for row in rows
        )
    ).encode("utf-8")
    provenance = tuple(
        {**item.lineage, "bundle_id": bundle.bundle_id, "trainer_row_digest": canonical_hash(row)}
        for item, row in zip(admitted, rows, strict=True)
    )
    return VerifiedLearningBundle(bundle, trainer_bytes, provenance)
