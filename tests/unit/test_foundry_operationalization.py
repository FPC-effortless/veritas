from __future__ import annotations

import json
from pathlib import Path

import pytest

from investigation_world.foundry import (
    CalibrationBinding,
    CalibrationDataset,
    CalibrationIngestionPlan,
    CalibrationParameter,
    CalibrationStatistic,
    DependencyFitRule,
    DistributionFitRule,
    DistributionSplit,
    ExpertTrajectory,
    ExternalInvestigationBuildPlan,
    ExternalInvestigationWorldSpec,
    PreferenceTrainerAdapter,
    SFTTrainerAdapter,
    TrainerKind,
    TrainingRecipe,
    TrainingRunManifest,
    VOPSDTrainerAdapter,
    compile_training_bundle,
    external_investigation_capability_contract,
    fit_calibration_plan,
    generate_counterfactual_trajectory,
    generate_demonstration_set,
    generate_verified_trajectory,
    load_external_investigation_distribution,
    make_preference_pair,
    materialize_external_investigation_build_plan,
    resolve_external_world_spec,
    write_external_investigation_distribution,
)
from investigation_world.world.generator import WorldGenerationConfig


def _small_world_spec(
    split: DistributionSplit,
    *,
    seed: int,
    tasks: int = 6,
) -> ExternalInvestigationWorldSpec:
    return ExternalInvestigationWorldSpec(
        split=split,
        world_seed=seed,
        evidence_seed=seed + 1000,
        task_seed=seed + 2000,
        task_count=tasks,
        config=WorldGenerationConfig(
            num_people=24,
            num_organizations=12,
            num_addresses=12,
            relationship_density=0.10,
            alias_rate=0.35,
            rename_rate=0.20,
            ownership_chain_depth=3,
        ),
    )


def _single_train_distribution(tasks: int = 12):
    plan = ExternalInvestigationBuildPlan(
        worlds=[_small_world_spec(DistributionSplit.TRAIN, seed=701, tasks=tasks)]
    )
    return materialize_external_investigation_build_plan(plan)


def _expert_episode_and_trajectory():
    distribution = _single_train_distribution(tasks=18)
    for episode in distribution.episodes:
        if not episode.oracle.answerable:
            continue
        trajectory = generate_verified_trajectory(
            episode,
            expert_threshold=0.70,
        )
        if isinstance(trajectory, ExpertTrajectory):
            return episode, trajectory
    raise AssertionError("small distribution produced no expert-qualified trajectory")


def test_calibration_ingestion_profiles_and_fits_csv(tmp_path: Path) -> None:
    dataset = tmp_path / "operations.csv"
    dataset.write_text(
        "employees,revenue,segment\n"
        "10,100,a\n"
        "20,200,a\n"
        "30,300,b\n",
        encoding="utf-8",
    )
    plan = CalibrationIngestionPlan(
        calibration_id="ops-v1",
        domain="enterprise_operations",
        datasets=[
            CalibrationDataset(
                source_id="ops",
                path=dataset,
                name="operations fixture",
            )
        ],
        distribution_rules=[
            DistributionFitRule(
                target_id="mean-employees",
                source_id="ops",
                object_type="organization",
                attribute="employees",
                statistic=CalibrationStatistic.MEAN,
                column="employees",
            ),
            DistributionFitRule(
                target_id="segments",
                source_id="ops",
                object_type="organization",
                attribute="segment",
                statistic=CalibrationStatistic.CATEGORY_DISTRIBUTION,
                column="segment",
            ),
        ],
        dependency_rules=[
            DependencyFitRule(
                target_id="headcount-revenue",
                source_id="ops",
                cause="headcount",
                effect="revenue",
                cause_column="employees",
                effect_column="revenue",
            )
        ],
    )

    result = fit_calibration_plan(plan)

    assert result.profiles["ops"].row_count == 3
    assert len(result.profiles["ops"].file_sha256) == 64
    targets = {target.target_id: target for target in result.spec.distribution_targets}
    assert targets["mean-employees"].expected_value == pytest.approx(20.0)
    assert targets["segments"].expected_value["a"] == pytest.approx(2 / 3)
    assert result.spec.dependency_targets[0].strength == pytest.approx(1.0)
    assert result.spec.sources[0].provenance["row_count"] == 3


def test_calibration_target_can_parameterize_world_generator(tmp_path: Path) -> None:
    dataset = tmp_path / "organizations.csv"
    dataset.write_text("employees\n10\n20\n30\n", encoding="utf-8")
    fitted = fit_calibration_plan(
        CalibrationIngestionPlan(
            calibration_id="org-scale-v1",
            domain="organizations",
            datasets=[
                CalibrationDataset(
                    source_id="organizations",
                    path=dataset,
                    name="organization scale",
                )
            ],
            distribution_rules=[
                DistributionFitRule(
                    target_id="mean-employees",
                    source_id="organizations",
                    object_type="organization",
                    attribute="employees",
                    statistic=CalibrationStatistic.MEAN,
                    column="employees",
                )
            ],
        )
    )
    base = _small_world_spec(DistributionSplit.TRAIN, seed=801)
    resolved = resolve_external_world_spec(
        base,
        calibration_spec=fitted.spec,
        bindings=[
            CalibrationBinding(
                target_id="mean-employees",
                parameter=CalibrationParameter.NUM_PEOPLE,
                minimum=5,
                maximum=100,
            )
        ],
    )

    assert resolved.config.num_people == 20


def test_external_distribution_has_disjoint_splits_and_private_boundary() -> None:
    plan = ExternalInvestigationBuildPlan(
        worlds=[
            _small_world_spec(DistributionSplit.TRAIN, seed=901, tasks=3),
            _small_world_spec(DistributionSplit.IID_TEST, seed=902, tasks=3),
            _small_world_spec(DistributionSplit.OOD, seed=903, tasks=3),
            _small_world_spec(DistributionSplit.ADVERSARIAL, seed=904, tasks=3),
        ]
    )
    distribution = materialize_external_investigation_build_plan(plan)

    assert {partition.split for partition in distribution.manifest.partitions} == set(
        DistributionSplit
    )
    task_ids = [
        task_id
        for partition in distribution.manifest.partitions
        for task_id in partition.task_ids
    ]
    seeds = [
        seed
        for partition in distribution.manifest.partitions
        for seed in partition.seeds
    ]
    assert len(task_ids) == len(set(task_ids))
    assert len(seeds) == len(set(seeds))
    public_text = json.dumps(distribution.public_payload(), default=str).casefold()
    assert '"oracle"' not in public_text
    assert "target_entity_ids" not in public_text
    assert '"people"' not in public_text


def test_private_external_distribution_round_trips(tmp_path: Path) -> None:
    distribution = _single_train_distribution(tasks=4)
    public_path = tmp_path / "public.json"
    private_path = tmp_path / "private.json"

    write_external_investigation_distribution(
        distribution,
        public_path,
        private_output=private_path,
    )
    loaded = load_external_investigation_distribution(private_path)

    assert loaded.manifest.manifest_id == distribution.manifest.manifest_id
    assert len(loaded.episodes) == len(distribution.episodes)
    assert json.loads(public_path.read_text())["episode_count"] == 4


def test_shared_runtime_exposes_only_public_state() -> None:
    distribution = _single_train_distribution(tasks=6)
    episode = distribution.episodes[0]
    runtime = episode.runtime()
    try:
        query = episode.task.target_refs[0] if episode.task.target_refs else "Meridian"
        runtime.document_search(query, limit=3)
        snapshot = runtime.state_snapshot()
        text = json.dumps(snapshot).casefold()
        assert runtime.budget_snapshot()["spent"] > 0
        assert "oracle" not in text
        assert "target_entity_ids" not in text
        assert '"world"' not in text
    finally:
        runtime.close()


def test_reference_policy_records_verified_public_tool_trajectory() -> None:
    _, trajectory = _expert_episode_and_trajectory()

    event_types = [event.event_type for event in trajectory.trace.events]
    assert "submit" in event_types
    assert any(event_type.endswith("search") for event_type in event_types)
    assert "open_document" in event_types
    assert trajectory.assessment.verifier_score >= 0.70
    assert trajectory.annotations["privileged_reference"] is True
    assert trajectory.annotations["teacher_structural_guidance"]


def test_counterfactual_produces_lower_scoring_preference_candidate() -> None:
    episode, chosen = _expert_episode_and_trajectory()
    rejected = generate_counterfactual_trajectory(episode, chosen)

    assert chosen.assessment.verifier_score > rejected.assessment.verifier_score
    pair = make_preference_pair(
        chosen,
        rejected,
        reason="higher independently verified outcome",
    )
    assert pair.score_margin > 0
    assert rejected.annotations["parent_trajectory_id"] == chosen.trajectory_id


def test_training_adapters_emit_sft_preference_and_vopsd_artifacts(
    tmp_path: Path,
) -> None:
    episode, chosen = _expert_episode_and_trajectory()
    rejected = generate_counterfactual_trajectory(episode, chosen)
    pair = make_preference_pair(
        chosen,
        rejected,
        reason="higher independently verified outcome",
    )
    trajectories = [chosen, rejected]
    contract = external_investigation_capability_contract()

    sft_recipe = TrainingRecipe(
        recipe_id="sft-v1",
        trainer=TrainerKind.SFT,
        capability_contract_id=contract.capability_id,
        minimum_verifier_score=0.70,
    )
    sft_bundle = compile_training_bundle(contract, sft_recipe, trajectories)
    sft_manifest = TrainingRunManifest(
        run_id="sft-run",
        bundle_id=sft_bundle.bundle_id,
        trainer=TrainerKind.SFT,
        base_model="fixture-model",
    )
    sft_result = SFTTrainerAdapter(tmp_path, trajectories).run(
        sft_bundle,
        sft_manifest,
    )
    sft_rows = [
        json.loads(line)
        for line in Path(sft_result.metadata["training_data"]).read_text().splitlines()
    ]
    assert sft_rows and sft_rows[0]["target_result"] is not None

    preference_recipe = TrainingRecipe(
        recipe_id="preference-v1",
        trainer=TrainerKind.PREFERENCE,
        capability_contract_id=contract.capability_id,
        minimum_verifier_score=0.70,
    )
    preference_bundle = compile_training_bundle(
        contract,
        preference_recipe,
        trajectories,
        preference_pairs=[pair],
    )
    preference_manifest = TrainingRunManifest(
        run_id="preference-run",
        bundle_id=preference_bundle.bundle_id,
        trainer=TrainerKind.PREFERENCE,
        base_model="fixture-model",
    )
    preference_result = PreferenceTrainerAdapter(tmp_path, trajectories).run(
        preference_bundle,
        preference_manifest,
    )
    preference_rows = [
        json.loads(line)
        for line in Path(preference_result.metadata["training_data"])
        .read_text()
        .splitlines()
    ]
    assert preference_rows[0]["score_margin"] > 0

    vopsd_recipe = TrainingRecipe(
        recipe_id="vopsd-v1",
        trainer=TrainerKind.VOPSD,
        capability_contract_id=contract.capability_id,
        minimum_verifier_score=0.70,
    )
    vopsd_bundle = compile_training_bundle(contract, vopsd_recipe, trajectories)
    vopsd_manifest = TrainingRunManifest(
        run_id="vopsd-run",
        bundle_id=vopsd_bundle.bundle_id,
        trainer=TrainerKind.VOPSD,
        base_model="fixture-model",
    )
    vopsd_result = VOPSDTrainerAdapter(tmp_path, trajectories).run(
        vopsd_bundle,
        vopsd_manifest,
    )
    vopsd_rows = [
        json.loads(line)
        for line in Path(vopsd_result.metadata["training_data"]).read_text().splitlines()
    ]
    assert vopsd_rows[0]["structural_steps"]
    assert vopsd_rows[0]["teacher_structural_guidance"]
    assert vopsd_rows[0]["independent_verification"]["reward"] >= 0.70
    assert "authoritative" in vopsd_rows[0]["training_rule"]


def test_demonstration_set_marks_privileged_policy_as_non_evaluation() -> None:
    distribution = _single_train_distribution(tasks=8)
    contract = external_investigation_capability_contract()
    demonstrations = generate_demonstration_set(
        distribution.episodes,
        capability_contract_id=contract.capability_id,
        expert_threshold=0.70,
        maximum_episodes=8,
    )

    assert demonstrations.trajectories
    assert demonstrations.metadata["privileged_generation"] is True
    assert demonstrations.metadata["evaluation_use_of_oracle_policy_forbidden"] is True
