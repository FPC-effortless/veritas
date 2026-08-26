from investigation_world.foundry import (
    CalibrationReport,
    CalibrationSource,
    CalibrationSourceKind,
    DistributionSplit,
    DistributionTarget,
    RolloutTrace,
    TrainerKind,
    TrainingRecipe,
    WorldCalibrationSpec,
    calibration_fingerprint,
    compile_training_bundle,
    external_investigation_family,
    qualify_expert_trace,
    validate_calibration_report,
    world_manifest_id,
)


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
    assert bundle.train_examples[0].trace_ref == "train"


def test_world_calibration_has_stable_provenance_fingerprint_and_quality_gate() -> None:
    spec = WorldCalibrationSpec(
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


def test_external_investigation_is_not_alias_for_companyworld() -> None:
    family = external_investigation_family()

    assert family.family_id.value == "external_investigation"
    assert family.capability_contract.capability_id == "external-investigation"
    assert "entity_resolution" in family.task_families
    assert "web" in family.source_surfaces
    assert "customer-specific investigative domains" in family.capability_contract.transfer_targets
