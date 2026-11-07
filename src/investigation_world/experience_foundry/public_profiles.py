"""Closed public synthetic TRAIN profiles, not an arbitrary episode admission hook.

ponytail: two single-formula profiles only; new grammars need native support and
equivalent regeneration/replay/projection tests before extending this allowlist.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from investigation_world.foundry.models import (
    CapabilityContract,
    MutationKind,
    RolloutTrace,
    TraceEvent,
)
from investigation_world.foundry.mutations import apply_mutation
from investigation_world.operational.artifacts import attach_native_artifact_descriptor
from investigation_world.operational.distribution import OperationalDistributionCase
from investigation_world.operational.models import (
    ActionEvent,
    OperationalRecord,
    capability_binding_from_contract,
)
from investigation_world.trajectory import canonical_hash

V1_RECORDER = "veritas.public-financial-training-recorder.v1"
V2_RECORDER = "veritas.public-financial-training-recorder.v2"
PROFILE_IDS = ("financial-ordered-v2", "financial-ordered-context-v2")


def _check_profile(profile_id: str) -> None:
    if type(profile_id) is not str or profile_id not in PROFILE_IDS:
        raise ValueError("PUBLIC_PROFILE_UNSUPPORTED")


def structural_training_fixture(
    profile_id: str,
) -> tuple[OperationalDistributionCase, CapabilityContract]:
    """Regenerate one of two public derivatives; never enumerate another split."""
    _check_profile(profile_id)
    from .admission import public_training_fixture

    case, capability = public_training_fixture()
    episode = case.episode
    suffix = "-" + profile_id
    episode.episode_id += suffix
    episode.world_id += suffix
    episode.task.task_id += suffix
    episode.task.world_id = episode.world_id
    episode.oracle.task_id = episode.task.task_id
    episode.metadata["distribution_version"] = "veritas.public-financial-structural.v2"
    episode.task.objective = (
        "Public synthetic task: " + episode.task.objective
        + " Recalculation requires a prior successful formula repair."
    )
    episode.task.constraints.append("Repair the formula successfully before recalculation.")
    # A genuine executable edge: the unchanged runtime blocks premature recalculation.
    for effect in episode.oracle.action_effects:
        if effect.action_name == "recalculate_model":
            effect.required_prior_actions = ["repair_formula"]
    episode.oracle.required_action_order = ["repair_formula", "recalculate_model"]
    if profile_id == "financial-ordered-context-v2":
        mutated, _ = apply_mutation(
            episode.public_payload(),
            task_id=episode.task.task_id,
            kind=MutationKind.INJECT_DISTRACTOR,
            seed=73,
            parameters={"system": "WORKBOOK", "note": "Context note, not formula evidence."},
        )
        # Foundry's generic record has two CompanyWorld-only fields. Explicitly map
        # its public fields instead of accepting arbitrary records or hidden keys.
        row = mutated["records"][-1]
        audit = next(r for r in episode.records if r.record_type == "formula_audit")
        episode.records.append(
            OperationalRecord(
                record_id=row["record_id"],
                system=row["system"],
                record_type=row["record_type"],
                object_id=row["object_id"],
                fields=dict(row["fields"]),
                related_object_ids=[audit.object_id],
            )
        )
    episode.capability = capability_binding_from_contract(capability, episode)
    attach_native_artifact_descriptor(episode)
    return case, capability


def profile_fixture(
    profile_id: str | None,
) -> tuple[OperationalDistributionCase, CapabilityContract]:
    if profile_id is not None:
        return structural_training_fixture(profile_id)
    from .admission import public_training_fixture

    return public_training_fixture()


def recorder_version(profile_id: str | None) -> str:
    if profile_id is None:
        return V1_RECORDER
    _check_profile(profile_id)
    return V2_RECORDER


def profile_provenance(profile_id: str) -> dict:
    """Evaluator-side provenance of the exact installed producer and finite recipe."""
    case, _ = structural_training_fixture(profile_id)
    parent, _ = profile_fixture(None)
    parent_digest = canonical_hash(parent.episode.model_dump(mode="json"))
    episode = case.episode
    root = Path(__file__).resolve().parents[1]
    modules = (
        "experience_foundry/public_profiles.py",
        "experience_foundry/admission.py",
        "foundry/mutations.py",
        "operational/catalog.py",
        "operational/distribution.py",
        "operational/models.py",
    )
    generator = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in modules}
    structure = {
        "actions": [a.name for a in episode.task.available_actions],
        "dependencies": [
            (effect.action_name, effect.required_prior_actions)
            for effect in episode.oracle.action_effects
        ],
        "required_order": episode.oracle.required_action_order,
        "records": [
            (r.record_type, r.object_id, r.related_object_ids) for r in episode.records
        ],
    }
    return {
        "schema_version": "veritas.public-training-profile.v2",
        "profile_id": profile_id,
        "generator_digest": canonical_hash(generator),
        "configuration_digest": canonical_hash(
            {"profile_id": profile_id, "base_seed": 73, "base_fixture_digest": parent_digest}
        ),
        "parent_source_digest": parent_digest,
        "structure_digest": canonical_hash(structure),
        "source_kind": "CONSTRUCTED_PUBLIC_SYNTHETIC",
    }


def profile_id_from_trace(trace: RolloutTrace) -> str | None:
    if trace.harness_version == V1_RECORDER:
        return None
    if trace.harness_version != V2_RECORDER:
        raise ValueError("RECORDER_VERSION_UNSUPPORTED")
    profile = trace.metadata.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("PUBLIC_PROFILE_PROVENANCE_REQUIRED")
    identity = profile.get("profile_id")
    if not isinstance(identity, str):
        raise ValueError("PUBLIC_PROFILE_UNSUPPORTED")
    _check_profile(identity)
    if profile != profile_provenance(identity):
        raise ValueError("PUBLIC_PROFILE_PROVENANCE_MISMATCH")
    return identity


def recorder_metadata(profile_id: str | None, source_digest: str) -> dict:
    metadata: dict[str, Any] = {
        "recorder": recorder_version(profile_id), "source_digest": source_digest
    }
    if profile_id is not None:
        metadata["profile"] = profile_provenance(profile_id)
    return metadata


def validate_profile_action_events(
    profile_id: str | None, trace: RolloutTrace, action_events: tuple[ActionEvent, ...]
) -> None:
    """V2 act companions must be the exact native ActionEvent projection.

    Fresh native reverification separately validates these retained ActionEvents;
    hashes between companion and trajectory alone cannot establish this mapping.
    """
    if profile_id is None:
        return  # Preserve the original v1 acceptance profile.
    _check_profile(profile_id)
    expected = [
        TraceEvent(
            step=event.sequence - 1,
            event_type="act",
            cost=float(event.cost),
            payload={
                "method": "act",
                "action_name": event.action_name,
                "args": [event.action_name],
                "kwargs": event.parameters,
                "success": bool(event.effect_applied and not event.blocked),
            },
        ).model_dump(mode="json")
        for event in action_events
    ]
    actual = [event.model_dump(mode="json") for event in trace.events if event.event_type == "act"]
    # Canonical JSON distinguishes true/false from integer aliases as well.
    if canonical_hash(actual) != canonical_hash(expected):
        raise ValueError("PROFILE_ACTION_EVIDENCE_MISMATCH")
