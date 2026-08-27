from investigation_world.qualification.models import (
    EvidenceItem,
    EvidenceManifest,
    PolicyClass,
    PolicyEvaluation,
    PolicyOutcome,
    QualificationCandidate,
    QualificationScenario,
    QualificationSplit,
    QualificationThresholds,
)
from investigation_world.qualification.protocol import private_release_manifest, qualify_candidate


def _candidate(*, contaminate: bool = False, private_strata: list[str] | None = None) -> QualificationCandidate:
    scenarios = []
    splits = [
        *([QualificationSplit.TRAIN] * 6),
        *([QualificationSplit.DEV] * 2),
        *([QualificationSplit.PRIVATE_TEST] * 4),
    ]
    strata = private_strata or ["a", "b", "c", "d"]
    for index, split in enumerate(splits):
        text = f"unique operational scenario {index} service evidence token-{index}"
        if contaminate and index == 8:
            text = "unique operational scenario 0 service evidence token-0"
        metadata = {}
        if split == QualificationSplit.PRIVATE_TEST:
            metadata["class"] = strata[index - 8]
        scenarios.append(
            QualificationScenario(
                scenario_id=f"S-{index}",
                source_group_id=f"SRC-{index}",
                split=split,
                normalized_text=text,
                public_digest=f"PUB-{index}",
                private_digest=f"PRIV-{index}",
                metadata=metadata,
            )
        )
    manifest = EvidenceManifest(
        items=[
            EvidenceItem(
                evidence_id=f"E-{index}",
                source_group_id=f"SRC-{index}",
                source_uri=f"https://example.invalid/{index}",
                content_sha256=(f"{index:064d}"[-64:]),
            )
            for index in range(12)
        ]
    )
    return QualificationCandidate(
        candidate_id="CAND-1",
        domain="test",
        version="v1",
        scenarios=scenarios,
        evidence_manifest=manifest,
    )


def _evaluations() -> list[PolicyEvaluation]:
    private = ["S-8", "S-9", "S-10", "S-11"]
    values = {
        PolicyClass.ORACLE: [1.0, 1.0, 1.0, 1.0],
        PolicyClass.COMPETENT_HEURISTIC: [1.0, 1.0, 0.5, 0.5],
        PolicyClass.MYOPIC: [1.0, 0.5, 0.5, 0.0],
        PolicyClass.RANDOM: [0.0, 0.0, 0.0, 0.0],
        PolicyClass.EXPLOIT: [0.0, 0.0, 0.0, 0.0],
    }
    return [
        PolicyEvaluation(
            policy_class=kind,
            policy_name=kind.value,
            outcomes=[
                PolicyOutcome(scenario_id=scenario_id, reward=reward, passed=reward >= 0.95)
                for scenario_id, reward in zip(private, rewards, strict=True)
            ],
        )
        for kind, rewards in values.items()
    ]


def _thresholds() -> QualificationThresholds:
    return QualificationThresholds(
        minimum_private_test_scenarios=4,
        maximum_random_reward=0.20,
        maximum_exploit_reward=0.20,
    )


def test_qualification_passes_only_when_all_release_gates_hold():
    candidate = _candidate()
    report = qualify_candidate(candidate, _evaluations(), thresholds=_thresholds())

    assert report.releaseable is True
    assert all(gate.passed for gate in report.gates)
    assert report.policy_means[PolicyClass.ORACLE] == 1.0
    assert report.policy_means[PolicyClass.COMPETENT_HEURISTIC] == 0.75

    release = private_release_manifest(candidate, report)
    assert release.private_test_scenario_ids == ["S-10", "S-11", "S-8", "S-9"]
    assert release.evidence_manifest_id == candidate.evidence_manifest.manifest_id
    assert release.manifest_id.startswith("PRIVREL-")


def test_cross_split_near_duplicate_blocks_release():
    report = qualify_candidate(_candidate(contaminate=True), _evaluations(), thresholds=_thresholds())

    assert report.releaseable is False
    contamination = next(gate for gate in report.gates if gate.name == "cross_split_contamination")
    assert contamination.passed is False
    assert report.cross_split_near_duplicate_pairs


def test_policy_panel_must_match_private_test_exactly():
    evaluations = _evaluations()
    bad = evaluations[0].model_copy(update={"outcomes": evaluations[0].outcomes[:-1]})
    evaluations[0] = bad

    import pytest

    with pytest.raises(ValueError, match="exact private-test scenario panel"):
        qualify_candidate(_candidate(), evaluations, thresholds=_thresholds())


def test_private_stratum_gate_rejects_majority_class_panel():
    thresholds = _thresholds().model_copy(
        update={
            "private_stratum_metadata_key": "class",
            "minimum_private_strata": 4,
            "minimum_private_scenarios_per_stratum": 1,
            "maximum_private_stratum_fraction": 0.50,
        }
    )
    report = qualify_candidate(
        _candidate(private_strata=["transient", "transient", "transient", "capacity"]),
        _evaluations(),
        thresholds=thresholds,
    )
    gate = next(gate for gate in report.gates if gate.name == "private_stratum_coverage")
    assert gate.passed is False
    assert gate.observed["counts"] == {"capacity": 1, "transient": 3}
    assert report.releaseable is False


def test_private_stratum_gate_accepts_balanced_support():
    thresholds = _thresholds().model_copy(
        update={
            "private_stratum_metadata_key": "class",
            "minimum_private_strata": 4,
            "minimum_private_scenarios_per_stratum": 1,
            "maximum_private_stratum_fraction": 0.50,
        }
    )
    report = qualify_candidate(_candidate(), _evaluations(), thresholds=thresholds)
    gate = next(gate for gate in report.gates if gate.name == "private_stratum_coverage")
    assert gate.passed is True
    assert report.releaseable is True
