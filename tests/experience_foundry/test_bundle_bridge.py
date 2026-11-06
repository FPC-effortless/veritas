import pytest
from test_admission import recorded

from investigation_world.experience_foundry.admission import authorized_registry
from investigation_world.experience_foundry.bundle_bridge import compile_verified_bundle
from investigation_world.foundry.training_product import TrainerKind, TrainingRecipe


def recipe(source):
    return TrainingRecipe(
        recipe_id="public-sft",
        trainer=TrainerKind.SFT,
        capability_contract_id=source.capability.capability_id,
    )


def test_existing_bundle_and_allowlisted_bytes(tmp_path):
    source = recorded(tmp_path)
    result = compile_verified_bundle([source], recipe(source), registry=authorized_registry())
    assert len(result.bundle.train_examples) == 1
    assert b"task_seed" not in result.trainer_bytes
    assert b"private_metadata" not in result.trainer_bytes
    assert b"prompt" in result.trainer_bytes
    assert (
        result.trainer_bytes
        == compile_verified_bundle(
            [source], recipe(source), registry=authorized_registry()
        ).trainer_bytes
    )


def test_duplicate_source_rejects(tmp_path):
    source = recorded(tmp_path)
    with pytest.raises(ValueError, match="DUPLICATE"):
        compile_verified_bundle([source, source], recipe(source), registry=authorized_registry())


@pytest.mark.parametrize(
    "change",
    [
        {"require_invariant_pass": False},
        {"require_verified_terminal_success": False},
        {"minimum_verifier_score": 0.1},
        {"train_splits": ["train", "iid_test"]},
        {"trainer": "rl"},
        {"parameters": {"private": "CANARY"}},
    ],
)
def test_recipe_cannot_relax_admission(tmp_path, change):
    source = recorded(tmp_path)
    with pytest.raises(ValueError, match="RECIPE"):
        compile_verified_bundle(
            [source], recipe(source).model_copy(update=change), registry=authorized_registry()
        )


def test_frozen_panel_overlap_rejects(tmp_path):
    source = recorded(tmp_path)
    with pytest.raises(ValueError, match="OVERLAP"):
        compile_verified_bundle(
            [source],
            recipe(source),
            registry=authorized_registry(),
            frozen_panel_task_ids=(source.companion.task_id,),
        )


def test_private_canaries_never_reach_actual_trainer_bytes(tmp_path):
    from dataclasses import replace

    from investigation_world.experience import machine_experience_from_trajectory

    source = recorded(tmp_path)
    trajectory = source.experience.trajectory.model_copy(deep=True)
    trajectory.private_metadata["private-seed-note"] = "PRIVATE-SEED-CANARY"
    trajectory.provenance[0].private_metadata["hidden"] = "HIDDEN-ORACLE-CANARY"
    source = replace(source, experience=machine_experience_from_trajectory(trajectory))
    output = compile_verified_bundle([source], recipe(source), registry=authorized_registry())
    for secret in (
        b"PRIVATE-SEED-CANARY",
        b"HIDDEN-ORACLE-CANARY",
        str(source.companion.task_seed).encode(),
        source.experience.trajectory.trajectory_id.encode(),
        source.experience.experience_id.encode(),
        b"native_submission",
        b"oracle",
    ):
        assert secret not in output.trainer_bytes


def test_compilation_does_not_mutate_inputs(tmp_path):
    source = recorded(tmp_path)
    policy = recipe(source)
    before = source.experience.model_dump(), source.companion.model_dump(), policy.model_dump()
    compile_verified_bundle([source], policy, registry=authorized_registry())
    assert before == (
        source.experience.model_dump(),
        source.companion.model_dump(),
        policy.model_dump(),
    )


def test_frozen_panel_content_overlap_rejects(tmp_path):
    source = recorded(tmp_path)
    source_digest = source.experience.trajectory.provenance[0].source_digest
    with pytest.raises(ValueError, match="SOURCE_OVERLAP"):
        compile_verified_bundle(
            [source],
            recipe(source),
            registry=authorized_registry(),
            frozen_panel_source_digests=(source_digest,),
        )


def test_private_action_event_cannot_be_widened_even_with_rebound_evidence(tmp_path):
    from dataclasses import replace

    from investigation_world.experience import machine_experience_from_trajectory
    from investigation_world.trajectory import TrajectoryV2, VisibilityClass, canonical_hash
    from investigation_world.trajectory.reverify import (
        OperationalReplayEvidence,
        attach_operational_replay_evidence,
    )

    source = recorded(tmp_path)
    original = source.experience.trajectory
    events = (
        original.events[0].model_copy(update={"visibility": VisibilityClass.EVALUATOR_PRIVATE}),
        *original.events[1:],
    )
    payload = original.private_metadata["operational_reverification_evidence"].copy()
    payload.update(
        trajectory_events_digest=canonical_hash(events),
        evidence_id="",
        evidence_digest="",
        input_trajectory_id=None,
    )
    evidence = OperationalReplayEvidence.model_validate(payload)
    payload = original.model_dump(mode="python")
    payload.update(
        events=events,
        trajectory_id="",
        evidence_references=(evidence.reference(),),
        private_metadata={},
    )
    trajectory = TrajectoryV2.model_validate(payload)
    trajectory = attach_operational_replay_evidence(trajectory, evidence)
    source = replace(source, experience=machine_experience_from_trajectory(trajectory))
    with pytest.raises(ValueError, match="VISIBILITY"):
        compile_verified_bundle([source], recipe(source), registry=authorized_registry())
