from investigation_world.training_value import (
    build_diagnostic_examples,
    build_heldout_diagnostic_episodes,
    score_diagnostic_generator,
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


def test_training_targets_are_verifier_valid_reference_answers():
    examples = build_diagnostic_examples(count=4)
    by_prompt = {str(item["prompt"]): str(item["target"]) for item in examples}

    report = score_diagnostic_generator(
        lambda prompt: by_prompt[prompt],
        [item["episode"] for item in examples],
    )

    assert report["parse_failures"] == 0
    assert report["mean"] == 1.0
    assert report["min"] == 1.0
