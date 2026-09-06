from investigation_world.benchmark.policies import PublicEvidenceReferencePolicy
from investigation_world.companyworld.verifier import verify_companyworld
from investigation_world.training_value import build_training_rows, build_transfer_suite


def test_transfer_suites_are_world_disjoint_and_reference_solvable():
    suites = build_transfer_suite(train_candidates=8, eval_per_split=3)
    world_ids = {
        split: {episode.world_id for episode in episodes}
        for split, episodes in suites.items()
    }
    assert world_ids["train_pool"] == {"CW-FOUNDRY-TRAIN"}
    assert world_ids["iid"] == {"CW-FOUNDRY-IID"}
    assert world_ids["ood"] == {"CW-FOUNDRY-OOD"}
    assert world_ids["adversarial"] == {"CW-FOUNDRY-ADVERSARIAL"}
    assert len({next(iter(ids)) for ids in world_ids.values()}) == 4

    policy = PublicEvidenceReferencePolicy()
    for split, episodes in suites.items():
        for episode in episodes:
            result = policy(episode.public_payload())
            assert verify_companyworld(result, episode).overall_reward == 1.0, split


def test_ood_and_adversarial_suites_are_causally_harder_than_iid():
    suites = build_transfer_suite(train_candidates=4, eval_per_split=4)
    iid_records = sum(len(episode.records) for episode in suites["iid"])
    ood_records = sum(len(episode.records) for episode in suites["ood"])
    adversarial_records = sum(len(episode.records) for episode in suites["adversarial"])
    assert ood_records > iid_records
    assert adversarial_records > ood_records
    assert all(episode.task.constraints["foundry_adversarial_pressure"] == 1.0 for episode in suites["adversarial"])


def test_training_rows_keep_oracle_private():
    suites = build_transfer_suite(train_candidates=4, eval_per_split=1)
    rows = build_training_rows(suites["train_pool"], target_count=6)
    assert len(rows) == 6
    for row in rows:
        prompt = str(row["prompt"])
        assert "supporting_record_ids" not in prompt
        assert "expected_value" not in prompt
        assert "oracle" not in prompt.casefold()
