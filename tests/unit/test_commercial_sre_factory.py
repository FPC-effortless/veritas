from collections import Counter

from investigation_world.qualification import (
    PolicyClass,
    QualificationSplit,
    QualificationThresholds,
    build_commercial_sre_candidate,
    cross_split_near_duplicates,
    execute_commercial_sre_policy_suite,
    qualify_candidate,
)


def _thresholds() -> QualificationThresholds:
    return QualificationThresholds(
        minimum_private_test_scenarios=30,
        random_chance_reward=0.25,
        maximum_random_excess_over_chance=0.10,
        private_stratum_metadata_key="causal_class",
        minimum_private_strata=4,
        minimum_private_scenarios_per_stratum=5,
        maximum_private_stratum_fraction=0.35,
    )


def test_commercial_sre_factory_is_balanced_source_clean_and_qualifiable() -> None:
    candidate, cases = build_commercial_sre_candidate(seed=20260826, per_class=40)
    private = [case for case in cases if case.scenario.split == QualificationSplit.PRIVATE_TEST]
    counts = Counter(case.causal_class.value for case in private)

    assert len(candidate.scenarios) == 160
    assert len(private) == 32
    assert counts == {
        "regression": 8,
        "infrastructure": 8,
        "capacity": 8,
        "transient": 8,
    }
    assert candidate.metadata["synthetic"] is True
    assert candidate.metadata["source_text_copied"] is False
    assert {item["license"] for item in candidate.metadata["source_references"]} == {"MIT", "Apache-2.0"}
    assert cross_split_near_duplicates(candidate.scenarios) == []

    report = qualify_candidate(
        candidate,
        execute_commercial_sre_policy_suite(cases, random_seed=7),
        thresholds=_thresholds(),
    )
    assert report.releaseable is True
    assert all(gate.passed for gate in report.gates)
    assert report.policy_means[PolicyClass.ORACLE] == 1.0
    assert (
        report.policy_means[PolicyClass.ORACLE]
        > report.policy_means[PolicyClass.COMPETENT_HEURISTIC]
        > report.policy_means[PolicyClass.MYOPIC]
        > report.policy_means[PolicyClass.RANDOM]
    )


def test_commercial_sre_private_identity_changes_with_release_seed() -> None:
    first, first_cases = build_commercial_sre_candidate(seed=11, per_class=40)
    second, second_cases = build_commercial_sre_candidate(seed=29, per_class=40)

    first_private = {
        case.scenario.scenario_id
        for case in first_cases
        if case.scenario.split == QualificationSplit.PRIVATE_TEST
    }
    second_private = {
        case.scenario.scenario_id
        for case in second_cases
        if case.scenario.split == QualificationSplit.PRIVATE_TEST
    }
    assert first.candidate_id != second.candidate_id
    assert first.evidence_manifest.manifest_id != second.evidence_manifest.manifest_id
    assert first_private != second_private
