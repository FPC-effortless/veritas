import json

from investigation_world.foundry.models import DistributionSplit
from investigation_world.projectworld import (
    ProjectDistributionConfig,
    compile_project_distribution,
    private_project_distribution_payload,
    project_distribution_manifest,
    public_project_distribution_payload,
    validate_project_distribution,
)


def _small_config() -> ProjectDistributionConfig:
    return ProjectDistributionConfig(
        seed=2718,
        train=4,
        iid_test=3,
        ood=4,
        adversarial=3,
    )


def test_default_distribution_has_896_long_horizon_projects():
    assert ProjectDistributionConfig().total_cases == 896


def test_project_distribution_counts_and_split_separation():
    config = _small_config()
    cases = compile_project_distribution(config)
    validation = validate_project_distribution(cases, config=config)
    assert validation["valid"] is True
    assert validation["errors"] == []
    assert len(cases) == config.total_cases
    assert validation["split_counts"] == {
        "train": 4,
        "iid_test": 3,
        "ood": 4,
        "adversarial": 3,
    }
    assert len({case.scenario.spec.world_id for case in cases}) == len(cases)
    assert len({case.scenario.spec.project_id for case in cases}) == len(cases)


def test_distribution_is_deterministic():
    config = _small_config()
    first = compile_project_distribution(config)
    second = compile_project_distribution(config)
    first_manifest = project_distribution_manifest(first, config=config)
    second_manifest = project_distribution_manifest(second, config=config)
    assert first_manifest.public_hash == second_manifest.public_hash
    assert first_manifest.private_hash == second_manifest.private_hash
    assert [case.scenario.spec.world_id for case in first] == [
        case.scenario.spec.world_id for case in second
    ]


def test_public_payload_hides_private_oracle_and_split_metadata():
    config = _small_config()
    cases = compile_project_distribution(config)
    public = public_project_distribution_payload(cases, config=config)
    private = private_project_distribution_payload(cases, config=config)
    public_text = json.dumps(public, sort_keys=True)
    assert public["manifest"]["seed"] is None
    assert public["manifest"]["private_hash"] is None
    assert '"oracle"' not in public_text
    assert '"split"' not in public_text
    assert '"scenario_family"' not in public_text
    assert '"surface_profile"' not in public_text
    assert '"private_ground_truth"' not in public_text
    assert private["manifest"]["seed"] == config.seed
    assert private["manifest"]["private_hash"]
    assert all("split" in case for case in private["cases"])
    assert all("oracle" in case["scenario"] for case in private["cases"])


def test_ood_contains_held_out_construction_archetypes():
    config = _small_config()
    cases = compile_project_distribution(config)
    train_types = {
        case.scenario.spec.metadata["project_type"]
        for case in cases
        if case.split == DistributionSplit.TRAIN
    }
    ood_types = {
        case.scenario.spec.metadata["project_type"]
        for case in cases
        if case.split == DistributionSplit.OOD
    }
    assert ood_types - train_types
    assert {"hospital", "laboratory", "data_center", "education"}.intersection(ood_types)


def test_generator_changes_scale_cost_schedule_and_site_conditions():
    config = _small_config()
    cases = compile_project_distribution(config)
    specs = [case.scenario.spec for case in cases]
    assert len({spec.metadata["storeys"] for spec in specs}) > 1
    assert len({spec.metadata["gross_floor_area_m2"] for spec in specs}) > 1
    assert len({spec.metadata["site_profile"] for spec in specs}) > 1
    assert len({spec.budget for spec in specs}) > 1
    assert len({spec.deadline_days for spec in specs}) > 1
    superstructure_costs = {
        next(
            work.direct_cost
            for work in spec.work_packages
            if work.work_package_id == "superstructure"
        )
        for spec in specs
    }
    assert len(superstructure_costs) > 1


def test_adversarial_projects_have_compound_hidden_disruptions_and_pressure():
    config = _small_config()
    cases = compile_project_distribution(config)
    adversarial = [case for case in cases if case.split == DistributionSplit.ADVERSARIAL]
    assert adversarial
    for case in adversarial:
        oracle = case.scenario.oracle
        hidden_disruptions = (
            len(oracle.work_package_delay_days)
            + len(oracle.resource_delay_days)
            + len(oracle.latent_defects)
        )
        assert hidden_disruptions >= 6
        assert len(oracle.latent_defects) >= 3
        assert case.difficulty.adversarial_pressure >= 0.9


def test_every_generated_scenario_revalidates_project_graph():
    config = _small_config()
    cases = compile_project_distribution(config)
    for case in cases:
        scenario = case.scenario
        assert scenario.spec.domain.value == "construction"
        assert scenario.spec.budget > 0
        assert scenario.spec.deadline_days > 0
        assert len(scenario.spec.work_packages) == 12
        assert len(scenario.spec.roles) >= 8
        assert scenario.public_payload()["seed"] is None
