from investigation_world.training_value import (
    build_diagnostic_examples,
    build_heldout_diagnostic_episodes,
)


def test_training_and_heldout_worlds_are_disjoint():
    train = build_diagnostic_examples(count=4)
    heldout = build_heldout_diagnostic_episodes(count=4)
    assert {item["episode"].world_id for item in train} == {"CW-TRAINING"}
    assert {item.world_id for item in heldout} == {"CW-HELDOUT"}
    assert {item["episode"].episode_id for item in train}.isdisjoint(
        {item.episode_id for item in heldout}
    )


def test_training_examples_include_reference_json_targets():
    examples = build_diagnostic_examples(count=2)
    assert all('"claims"' in item["target"] for item in examples)
    assert all('"evidence_record_ids"' in item["target"] for item in examples)
