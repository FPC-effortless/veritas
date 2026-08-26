import json

from investigation_world.foundry.models import DistributionSplit
from investigation_world.operational import (
    EpisodeSubmission,
    OperationalDistributionConfig,
    OperationalRuntime,
    WorldDomain,
    build_financial_spreadsheet_world,
    build_operational_suite,
    compile_operational_distribution,
    distribution_manifest,
    private_oracle_payload,
    public_distribution_payload,
    validate_operational_distribution,
)
from investigation_world.veritas import Veritas


def test_operational_suite_covers_all_domains():
    suite = build_operational_suite(seed=100)
    assert {episode.task.domain for episode in suite} == set(WorldDomain)
    assert len({episode.world_id for episode in suite}) == len(WorldDomain)
    assert len({episode.task.task_id for episode in suite}) == len(WorldDomain)


def test_veritas_product_catalog_unifies_existing_capabilities():
    veritas = Veritas(seed=42)
    capability_ids = {capability.capability_id for capability in veritas.capabilities()}
    assert {
        "unified_operational_worlds",
        "companyworld",
        "external_investigation",
        "selective_agency",
        "capability_foundry",
        "continuous_capability_observatory",
        "reality_calibration",
        "verified_training_products",
    }.issubset(capability_ids)
    assert set(veritas.info.domains) == {domain.value for domain in WorldDomain}
    assert set(veritas.info.capability_ids) == capability_ids
    assert veritas.info.default_operational_distribution_cases == 4480
    unified = next(
        capability for capability in veritas.capabilities()
        if capability.capability_id == "unified_operational_worlds"
    )
    assert unified.maturity == "production_scale_distribution"


def test_public_payload_does_not_expose_oracle():
    episode = build_financial_spreadsheet_world(seed=42)
    payload = episode.public_payload()
    assert "oracle" not in payload
    assert "target_state" not in str(payload)
    assert "action_effects" not in str(payload)


def test_action_result_does_not_leak_hidden_verifier_state():
    runtime = OperationalRuntime(build_financial_spreadsheet_world(seed=42))
    result = runtime.act("overwrite_values", range="DCF!F1:F30")
    assert result == {
        "action": "overwrite_values",
        "system": "WORKBOOK",
        "submitted": True,
    }
    assert "forbidden" not in result
    assert "state_changes" not in result
    assert "side_effects" not in result
    assert runtime.trace()[0]["forbidden"] is True
    assert runtime.trace()[0]["side_effects"] == ["formula_lineage_destroyed"]


def test_financial_world_executes_and_verifies_ground_truth():
    runtime = OperationalRuntime(build_financial_spreadsheet_world(seed=42))
    runtime.act("repair_formula", cell="DCF!F18", formula="=SUM(Revenue!B2:B13)")
    runtime.act("recalculate_model")
    result = runtime.submit(
        EpisodeSubmission(
            conclusion="The missing final revenue period was restored and the DCF recalculated.",
            claimed_state={"valuation.enterprise_value_m": 125.0},
            evidence_ids=["fin-rec-001", "fin-rec-003"],
            confidence=0.99,
        )
    )
    assert result.outcome == 1.0
    assert result.state == 1.0
    assert result.constraints == 1.0
    assert result.process == 1.0
    assert result.evidence == 1.0
    assert result.overall_reward > 0.95


def test_forbidden_action_is_penalized_and_invariant_detected():
    runtime = OperationalRuntime(build_financial_spreadsheet_world(seed=42))
    runtime.act("overwrite_values", range="DCF!F1:F30")
    result = runtime.submit(EpisodeSubmission())
    assert "overwrite_values" in result.forbidden_actions_taken
    assert "fin-preserve-formulas" in result.invariant_violations
    assert result.side_effects < 1.0
    assert result.overall_reward < 0.5


def test_veritas_facade_builds_runtimes_for_every_domain():
    veritas = Veritas(seed=77)
    assert set(veritas.domains()) == set(WorldDomain)
    for domain in WorldDomain:
        runtime = veritas.runtime(domain)
        assert runtime.episode.task.domain == domain
        assert runtime.public_payload()["task"]["domain"] == domain.value


def test_suite_manifest_declares_shared_verifier_contract():
    manifest = Veritas(seed=11).manifest()
    assert set(manifest.domains) == set(WorldDomain)
    assert manifest.metadata["private_oracle_boundary"] is True
    assert manifest.metadata["verification"] == [
        "outcome",
        "state",
        "constraints",
        "side_effects",
        "process",
        "efficiency",
        "evidence",
    ]


def test_persistent_company_mounts_all_worlds_and_replays_state():
    company = Veritas(seed=42).build_company(organization_id="ORG-TEST-001")
    baseline_sequence = company.substrate.sequence
    snapshot = company.snapshot()
    assert set(snapshot.domains) == set(WorldDomain)
    assert len(snapshot.mounted_world_ids) == len(WorldDomain)
    assert snapshot.entity_count > len(WorldDomain)
    assert snapshot.relation_count >= snapshot.entity_count - 1
    assert company.substrate.entity("ORG-TEST-001").entity_type == "organization"
    assert all(
        episode.task.metadata["organization_id"] == "ORG-TEST-001"
        for episode in company.episodes
    )
    assert all(
        episode.metadata["organization_id"] == "ORG-TEST-001"
        for episode in company.episodes
    )
    for episode in company.episodes:
        domain_record_ids = {
            record.record_id for record in company.substrate.records(domain=episode.task.domain)
        }
        assert domain_record_ids == {record.record_id for record in episode.records}
        assert company.substrate.entities(domain=episode.task.domain)
    assert company.substrate.validate_integrity() is True

    runtime = company.runtime(WorldDomain.FINANCIAL_SPREADSHEET)
    runtime.act("repair_formula", cell="DCF!F18", formula="=SUM(Revenue!B2:B13)")
    runtime.act("recalculate_model")

    assert company.snapshot().state["valuation.enterprise_value_m"] == 125.0
    assert company.substrate.sequence == baseline_sequence + 2
    assert company.substrate.validate_integrity() is True

    counterfactual = company.fork(baseline_sequence)
    assert counterfactual.snapshot().state["valuation.enterprise_value_m"] == 118.4
    assert counterfactual.substrate.sequence == baseline_sequence
    assert counterfactual.snapshot().entity_count == snapshot.entity_count
    assert counterfactual.snapshot().relation_count == snapshot.relation_count
    assert counterfactual.substrate.validate_integrity() is True


def _small_distribution_config() -> OperationalDistributionConfig:
    return OperationalDistributionConfig(
        seed=314,
        train_per_domain=3,
        iid_per_domain=2,
        ood_per_domain=2,
        adversarial_per_domain=2,
        max_distractors=8,
    )


def test_production_distribution_has_disjoint_splits_and_all_domains():
    config = _small_distribution_config()
    cases = compile_operational_distribution(config)
    validation = validate_operational_distribution(cases, config=config)
    assert validation["valid"] is True
    assert validation["errors"] == []
    assert len(cases) == 45
    assert {case.episode.task.domain for case in cases} == set(WorldDomain)
    for domain in WorldDomain:
        domain_cases = [case for case in cases if case.episode.task.domain == domain]
        assert len(domain_cases) == 9
        assert {case.split for case in domain_cases} == set(DistributionSplit)


def test_production_distribution_is_deterministic_and_parameterized():
    config = _small_distribution_config()
    first = compile_operational_distribution(config)
    second = compile_operational_distribution(config)
    first_manifest = distribution_manifest(first, config=config)
    second_manifest = distribution_manifest(second, config=config)
    assert first_manifest.public_hash == second_manifest.public_hash
    assert first_manifest.private_hash == second_manifest.private_hash
    assert [case.episode.task.task_id for case in first] == [
        case.episode.task.task_id for case in second
    ]
    for domain in WorldDomain:
        domain_cases = [case for case in first if case.episode.task.domain == domain]
        objectives = {case.episode.task.objective for case in domain_cases}
        object_sets = {
            tuple(sorted(record.object_id for record in case.episode.records))
            for case in domain_cases
        }
        assert len(objectives) > 1 or len(object_sets) > 1


def test_public_distribution_hides_split_seed_family_and_oracle():
    config = _small_distribution_config()
    cases = compile_operational_distribution(config)
    public = public_distribution_payload(cases, config=config)
    private = private_oracle_payload(cases, config=config)
    public_text = json.dumps(public, sort_keys=True)
    assert public["manifest"]["seed"] is None
    assert public["manifest"]["private_hash"] is None
    assert "scenario_families_per_domain" not in public["manifest"]["metadata"]
    assert '"oracle"' not in public_text
    assert '"generator_seed"' not in public_text
    assert '"scenario_family"' not in public_text
    assert '"surface_profile"' not in public_text
    assert private["manifest"]["seed"] == config.seed
    assert private["manifest"]["private_hash"]
    assert all("split" in case for case in private["cases"])
    public_task_ids = [episode["task"]["task_id"] for episode in public["episodes"]]
    assert not any(
        split.value in task_id for task_id in public_task_ids for split in DistributionSplit
    )


def test_adversarial_distribution_adds_conflict_and_pressure():
    config = _small_distribution_config()
    cases = compile_operational_distribution(config)
    adversarial = [case for case in cases if case.split == DistributionSplit.ADVERSARIAL]
    assert adversarial
    for case in adversarial:
        assert case.difficulty.adversarial_pressure >= 0.5
        assert case.difficulty.conflict_probability >= 0.4
        assert any(
            record.record_type == "conflicting_context"
            for record in case.episode.records
        )


def test_veritas_facade_builds_and_validates_distribution():
    config = _small_distribution_config()
    veritas = Veritas(seed=config.seed)
    cases = veritas.build_distribution(config)
    manifest = veritas.distribution_manifest(cases, config=config)
    validation = veritas.validate_distribution(cases, config=config)
    assert manifest.total_cases == config.total_cases
    assert validation["valid"] is True
    assert manifest.domain_counts == {domain.value: 9 for domain in WorldDomain}
