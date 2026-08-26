from __future__ import annotations

from collections import defaultdict

from investigation_world.foundry.models import stable_hash
from investigation_world.qualification.models import (
    PolicyClass,
    PolicyEvaluation,
    PrivateReleaseManifest,
    QualificationCandidate,
    QualificationGate,
    QualificationReport,
    QualificationSplit,
    QualificationThresholds,
)
from investigation_world.qualification.source_disjoint import (
    cross_split_near_duplicates,
    source_group_overlap,
)


def _gate(name: str, passed: bool, observed, required, detail: str = "") -> QualificationGate:
    return QualificationGate(
        name=name,
        passed=passed,
        observed=observed,
        required=required,
        detail=detail,
    )


def _source_groups(candidate: QualificationCandidate) -> dict[QualificationSplit, set[str]]:
    result: dict[QualificationSplit, set[str]] = defaultdict(set)
    for scenario in candidate.scenarios:
        result[scenario.split].add(scenario.source_group_id)
    return result


def _policy_map(evaluations: list[PolicyEvaluation]) -> dict[PolicyClass, PolicyEvaluation]:
    mapping: dict[PolicyClass, PolicyEvaluation] = {}
    for evaluation in evaluations:
        if evaluation.policy_class in mapping:
            raise ValueError(f"duplicate policy class: {evaluation.policy_class.value}")
        mapping[evaluation.policy_class] = evaluation
    required = set(PolicyClass)
    missing = required - set(mapping)
    if missing:
        raise ValueError("missing qualification policy classes: " + ", ".join(sorted(x.value for x in missing)))
    return mapping


def qualify_candidate(
    candidate: QualificationCandidate,
    evaluations: list[PolicyEvaluation],
    *,
    thresholds: QualificationThresholds | None = None,
) -> QualificationReport:
    cfg = thresholds or QualificationThresholds()
    policies = _policy_map(evaluations)
    private_ids = sorted(
        scenario.scenario_id
        for scenario in candidate.scenarios
        if scenario.split == QualificationSplit.PRIVATE_TEST
    )
    if not private_ids:
        raise ValueError("qualification requires a private-test panel")
    private_set = set(private_ids)
    for policy_class, evaluation in policies.items():
        observed = [item.scenario_id for item in evaluation.outcomes]
        if len(observed) != len(set(observed)):
            raise ValueError(f"duplicate outcomes in {policy_class.value} policy evaluation")
        if set(observed) != private_set:
            raise ValueError(
                f"{policy_class.value} policy must run on the exact private-test scenario panel"
            )

    source_groups = _source_groups(candidate)
    all_groups = set().union(*source_groups.values()) if source_groups else set()
    overlap = source_group_overlap(candidate.scenarios)
    duplicates = cross_split_near_duplicates(candidate.scenarios)
    policy_means = {kind: policies[kind].mean_reward for kind in PolicyClass}
    policy_replay = min(policies[kind].replay_rate for kind in PolicyClass)
    replay_rate = min(candidate.replay_rate, policy_replay)

    oracle = policy_means[PolicyClass.ORACLE]
    competent = policy_means[PolicyClass.COMPETENT_HEURISTIC]
    myopic = policy_means[PolicyClass.MYOPIC]
    random = policy_means[PolicyClass.RANDOM]
    exploit = policy_means[PolicyClass.EXPLOIT]
    ordered = oracle > competent > myopic > random

    if cfg.random_chance_reward is None:
        random_limit = cfg.maximum_random_reward
        random_required = random_limit
        random_detail = "absolute random-policy ceiling"
    else:
        random_limit = min(1.0, cfg.random_chance_reward + cfg.maximum_random_excess_over_chance)
        random_required = {
            "chance_reward": cfg.random_chance_reward,
            "maximum_excess_over_chance": cfg.maximum_random_excess_over_chance,
            "maximum_random_reward": random_limit,
        }
        random_detail = "domain chance baseline plus allowed finite-panel tolerance"

    gates = [
        _gate("source_groups", len(all_groups) >= cfg.minimum_source_groups, len(all_groups), cfg.minimum_source_groups),
        _gate(
            "train_source_groups",
            len(source_groups[QualificationSplit.TRAIN]) >= cfg.minimum_train_source_groups,
            len(source_groups[QualificationSplit.TRAIN]),
            cfg.minimum_train_source_groups,
        ),
        _gate(
            "dev_source_groups",
            len(source_groups[QualificationSplit.DEV]) >= cfg.minimum_dev_source_groups,
            len(source_groups[QualificationSplit.DEV]),
            cfg.minimum_dev_source_groups,
        ),
        _gate(
            "private_test_source_groups",
            len(source_groups[QualificationSplit.PRIVATE_TEST]) >= cfg.minimum_private_test_source_groups,
            len(source_groups[QualificationSplit.PRIVATE_TEST]),
            cfg.minimum_private_test_source_groups,
        ),
        _gate(
            "private_test_scenarios",
            len(private_ids) >= cfg.minimum_private_test_scenarios,
            len(private_ids),
            cfg.minimum_private_test_scenarios,
        ),
        _gate("source_disjoint", not overlap, overlap, {}),
        _gate(
            "cross_split_contamination",
            len(duplicates) <= cfg.maximum_cross_split_near_duplicates,
            len(duplicates),
            cfg.maximum_cross_split_near_duplicates,
        ),
        _gate(
            "private_leakage",
            candidate.private_leakage_count <= cfg.maximum_private_leakage_count,
            candidate.private_leakage_count,
            cfg.maximum_private_leakage_count,
        ),
        _gate(
            "provenance",
            candidate.provenance_rate >= cfg.minimum_provenance_rate,
            candidate.provenance_rate,
            cfg.minimum_provenance_rate,
        ),
        _gate(
            "deterministic_replay",
            replay_rate >= cfg.minimum_replay_rate,
            replay_rate,
            cfg.minimum_replay_rate,
        ),
        _gate(
            "programmatic_criteria",
            candidate.programmatic_rate >= cfg.minimum_programmatic_rate,
            candidate.programmatic_rate,
            cfg.minimum_programmatic_rate,
        ),
        _gate(
            "feasibility",
            candidate.broken_rate <= cfg.maximum_broken_rate and oracle >= cfg.minimum_oracle_reward,
            {"broken_rate": candidate.broken_rate, "oracle_reward": oracle},
            {"broken_rate_max": cfg.maximum_broken_rate, "oracle_reward_min": cfg.minimum_oracle_reward},
        ),
        _gate(
            "policy_ordering",
            ordered,
            {"oracle": oracle, "competent": competent, "myopic": myopic, "random": random},
            "oracle > competent_heuristic > myopic > random",
        ),
        _gate(
            "competent_ceiling",
            competent <= cfg.maximum_competent_reward,
            competent,
            cfg.maximum_competent_reward,
        ),
        _gate(
            "oracle_competent_gap",
            oracle - competent >= cfg.minimum_oracle_competent_gap,
            oracle - competent,
            cfg.minimum_oracle_competent_gap,
        ),
        _gate("random_ceiling", random <= random_limit, random, random_required, random_detail),
        _gate("exploit_resistance", exploit <= cfg.maximum_exploit_reward, exploit, cfg.maximum_exploit_reward),
    ]
    panel_payload = [
        [scenario.scenario_id, scenario.source_group_id, scenario.public_digest]
        for scenario in sorted(
            (item for item in candidate.scenarios if item.split == QualificationSplit.PRIVATE_TEST),
            key=lambda item: item.scenario_id,
        )
    ]
    panel_id = f"QPANEL-{stable_hash(panel_payload)[:24].upper()}"
    report_payload = [
        candidate.candidate_id,
        candidate.version,
        candidate.evidence_manifest.manifest_id,
        panel_id,
        [gate.model_dump(mode="json") for gate in gates],
        {kind.value: value for kind, value in policy_means.items()},
    ]
    report_id = f"QREPORT-{stable_hash(report_payload)[:24].upper()}"
    return QualificationReport(
        report_id=report_id,
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.version,
        evidence_manifest_id=candidate.evidence_manifest.manifest_id,
        panel_id=panel_id,
        gates=gates,
        policy_means=policy_means,
        source_overlap=overlap,
        cross_split_near_duplicate_pairs=duplicates,
        releaseable=all(gate.passed for gate in gates),
    )


def private_release_manifest(
    candidate: QualificationCandidate,
    report: QualificationReport,
) -> PrivateReleaseManifest:
    if report.candidate_id != candidate.candidate_id or report.candidate_version != candidate.version:
        raise ValueError("qualification report does not belong to candidate")
    if report.evidence_manifest_id != candidate.evidence_manifest.manifest_id:
        raise ValueError("qualification report evidence manifest mismatch")
    if not report.releaseable:
        raise ValueError("candidate cannot receive a private release manifest before qualification")

    by_split = {
        split: sorted(item.scenario_id for item in candidate.scenarios if item.split == split)
        for split in QualificationSplit
    }
    return PrivateReleaseManifest(
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.version,
        qualification_report_id=report.report_id,
        evidence_manifest_id=report.evidence_manifest_id,
        panel_id=report.panel_id,
        train_scenario_ids=by_split[QualificationSplit.TRAIN],
        dev_scenario_ids=by_split[QualificationSplit.DEV],
        private_test_scenario_ids=by_split[QualificationSplit.PRIVATE_TEST],
    )
