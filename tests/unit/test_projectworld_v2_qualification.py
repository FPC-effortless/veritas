from investigation_world.projectworld.v2_models import ProjectType
from investigation_world.qualification.models import PolicyClass, QualificationThresholds
from investigation_world.qualification.projectworld import (
    build_projectworld_v2_qualification_candidate,
    execute_projectworld_v2_policy_suite,
)
from investigation_world.qualification.protocol import qualify_candidate


def test_projectworld_v2_candidate_spans_structural_archetypes_and_private_panel():
    candidate, specs = build_projectworld_v2_qualification_candidate(seeds_per_type=6)

    types = {item.metadata["project_type"] for item in candidate.scenarios}
    assert types == {item.value for item in ProjectType}
    assert len(specs) == len(candidate.scenarios) == 30
    assert any(item.split.value == "private_test" for item in candidate.scenarios)


def test_projectworld_v2_policy_suite_runs_same_private_panel_for_all_policies():
    candidate, specs = build_projectworld_v2_qualification_candidate(seeds_per_type=6)
    evaluations = execute_projectworld_v2_policy_suite(candidate, specs, random_seed=11)

    panels = [
        {item.scenario_id for item in evaluation.outcomes}
        for evaluation in evaluations
    ]
    assert len(evaluations) == len(PolicyClass)
    assert all(panel == panels[0] for panel in panels)
    oracle = next(item for item in evaluations if item.policy_class == PolicyClass.ORACLE)
    random = next(item for item in evaluations if item.policy_class == PolicyClass.RANDOM)
    exploit = next(item for item in evaluations if item.policy_class == PolicyClass.EXPLOIT)
    assert oracle.mean_reward > random.mean_reward
    assert oracle.mean_reward > exploit.mean_reward


def test_projectworld_v2_qualification_exposes_policy_discrimination_gates():
    candidate, specs = build_projectworld_v2_qualification_candidate(seeds_per_type=6)
    evaluations = execute_projectworld_v2_policy_suite(candidate, specs, random_seed=13)
    # Small unit fixture relaxes only source/test-count thresholds; discrimination and exploit gates
    # remain live and are visible in the generic report.
    thresholds = QualificationThresholds(
        minimum_source_groups=30,
        minimum_train_source_groups=15,
        minimum_dev_source_groups=5,
        minimum_private_test_source_groups=5,
        minimum_private_test_scenarios=5,
        maximum_random_reward=0.50,
        maximum_exploit_reward=0.50,
    )
    report = qualify_candidate(candidate, evaluations, thresholds=thresholds)

    gate_names = {item.name for item in report.gates}
    assert {"feasibility", "policy_ordering", "random_ceiling", "exploit_resistance"} <= gate_names
    assert report.policy_means[PolicyClass.ORACLE] > report.policy_means[PolicyClass.RANDOM]
