from pathlib import Path

import pytest

from investigation_world.foundry import (
    CalibrationReport,
    CalibrationSource,
    CalibrationSourceKind,
    CompanyWorldBuildPlan,
    CompanyWorldBuildSpec,
    DistributionSplit,
    DistributionTarget,
    RolloutTrace,
    TrainerKind,
    TrainingRecipe,
    TrainingUse,
    WorldCalibrationSpec,
    calibration_fingerprint,
    compile_training_bundle,
    external_investigation_family,
    external_investigation_task_metadata,
    make_preference_pair,
    materialize_companyworld_build_plan,
    qualify_expert_trace,
    validate_calibration_report,
    world_manifest_id,
)
from investigation_world.tasks.spec import TaskFamily, TaskSpec


def _trace(trace_id: str, *, split: DistributionSplit, reward: float = 1.0) -> RolloutTrace:
    return RolloutTrace(
        trace_id=trace_id,
        environment_version="test",
        task_id="task-1",
        task_seed=1,
        split=split,
        capability_tags=["discover", "verify"],
        taskset_version="test",
        harness_version="test",
        runtime_version="test",
        initial_state_hash="start",
        verifier_components={"outcome": reward},
        total_reward=reward,
        final_state_hash="end",
        termination_reason="success",
    )


def _calibration_spec() -> WorldCalibrationSpec:
    return WorldCalibrationSpec(
        calibration_id="enterprise-reality-v1",
        domain="enterprise_operations",
        sources=[
            CalibrationSource(
                source_id="filings",
                kind=CalibrationSourceKind.REGULATORY_FILINGS,
                name="filing corpus",
                fields=["organization", "financials"],
            )
        ],
        distribution_targets=[
            DistributionTarget(
                target_id="entity-count",
                object_type="organization",
                attribute="count",
                statistic="median",
                expected_value=100,
                tolerance=0.1,
                source_ids=["filings"],
            )
        ],
    )


def test_expert_trajectories_compile_into_vopsd_bundle_without_heldout_leakage() -> None:
    family = external_investigation_family()
    train = qualify_expert_trace(_trace("train", split=DistributionSplit.TRAIN))
    heldout = qualify_expert_trace(_trace("heldout", split=DistributionSplit.OOD))
    recipe = TrainingRecipe(
        recipe_id="external-vopsd-v1",
        trainer=TrainerKind.VOPSD,
        capability_contract_id=family.capability_contract.capability_id,
    )

    bundle = compile_training_bundle(family.capability_contract, recipe, [train, heldout])

    assert [example.trajectory_id for example in bundle.train_examples] == [train.trajectory_id]
    assert bundle.heldout_trajectory_ids == [heldout.trajectory_id]
    assert bundle.metadata["heldout_is_never_emitted_as_training_data"] is True
    assert bundle.metadata["post_training_evaluation_required"] is True
    assert bundle.train_examples[0].trace_ref == "train"


def test_low_outcome_score_cannot_be_promoted_as_expert() -> None:
    with pytest.raises(ValueError, match="verifier score below expert threshold"):
        qualify_expert_trace(
            _trace("bad", split=DistributionSplit.TRAIN, reward=0.2),
            min_verifier_score=0.8,
        )


def test_preference_product_uses_verified_pair_provenance() -> None:
    family = external_investigation_family()
    chosen = qualify_expert_trace(
        _trace("chosen", split=DistributionSplit.TRAIN, reward=1.0),
        training_uses=[TrainingUse.PREFERENCE],
    )
    rejected = qualify_expert_trace(
        _trace("rejected", split=DistributionSplit.TRAIN, reward=0.85),
        training_uses=[TrainingUse.PREFERENCE],
    )
    pair = make_preference_pair(chosen, rejected, reason="higher verified outcome")
    recipe = TrainingRecipe(
        recipe_id="external-preference-v1",
        trainer=TrainerKind.PREFERENCE,
        capability_contract_id=family.capability_contract.capability_id,
    )

    bundle = compile_training_bundle(
        family.capability_contract,
        recipe,
        [chosen, rejected],
        preference_pairs=[pair],
    )

    assert bundle.train_examples == []
    assert len(bundle.preference_examples) == 1
    assert bundle.preference_examples[0].chosen_trace_ref == "chosen"
    assert bundle.preference_examples[0].rejected_trace_ref == "rejected"


def test_world_calibration_has_stable_provenance_fingerprint_and_quality_gate() -> None:
    spec = _calibration_spec()

    assert calibration_fingerprint(spec) == calibration_fingerprint(spec)
    manifest_id = world_manifest_id(spec, {"seed": 7})
    assert manifest_id.startswith("world-")

    report = validate_calibration_report(
        CalibrationReport(
            calibration_id=spec.calibration_id,
            world_manifest_id=manifest_id,
            target_scores={"entity-count": 0.7},
        ),
        minimum_score=0.8,
    )
    assert report.passed is False
    assert report.failed_targets == ["entity-count"]


def test_companyworld_build_manifest_is_bound_to_calibration(tmp_path: Path) -> None:
    generator = tmp_path / "generator.py"
    generator.write_text(
        "from pathlib import Path\nSEED = 0\nCOMPANY_ID = 'ORG'\nroot = Path('out')\n",
        encoding="utf-8",
    )
    spec = _calibration_spec()
    plan = CompanyWorldBuildPlan(
        generator_path=generator,
        calibration_spec=spec,
        builds=[
            CompanyWorldBuildSpec(
                split=DistributionSplit.TRAIN,
                seed=7,
                output_root=tmp_path / "world",
            )
        ],
    )

    manifest = materialize_companyworld_build_plan(plan)

    assert manifest["calibration"]["calibration_id"] == spec.calibration_id
    assert manifest["calibration"]["fingerprint"] == calibration_fingerprint(spec)
    assert manifest["builds"][0]["calibration_fingerprint"] == calibration_fingerprint(spec)


def test_external_investigation_is_not_alias_for_companyworld() -> None:
    family = external_investigation_family()

    assert family.family_id.value == "external_investigation"
    assert family.capability_contract.capability_id == "external-investigation"
    assert "entity_resolution" in family.task_families
    assert "web" in family.source_surfaces
    assert "customer-specific investigative domains" in family.capability_contract.transfer_targets


def test_external_investigation_tasks_have_foundry_metadata() -> None:
    task = TaskSpec(
        task_id="TASK-1",
        world_id="WORLD-1",
        family=TaskFamily.ENTITY_RESOLUTION,
        objective="Resolve whether two public records refer to the same entity.",
        target_refs=["A", "B"],
        constraints={"must_cite_evidence": True, "canonical_ids_are_not_available": True},
        difficulty={
            "candidate_entities": 8.0,
            "required_graph_hops": 2.0,
            "temporal_depth": 1.0,
            "noise_ratio": 0.5,
            "budget_tightness": 0.4,
        },
    )

    metadata = external_investigation_task_metadata(
        task,
        split=DistributionSplit.TRAIN,
        taskset_version="external-v1",
        harness_version="h1",
        runtime_version="r1",
        seed=11,
    )

    assert metadata.task_id == "WORLD-1::TASK-1"
    assert "entity_resolution" in metadata.capability_tags
    assert metadata.generator_parameters["capability_family"] == "external_investigation"
    assert metadata.difficulty.entities == 8
    assert metadata.difficulty.adversarial_pressure == 0.5
