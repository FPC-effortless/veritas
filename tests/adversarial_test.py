from datetime import timedelta

from investigation_world.core.models import InvestigationResult
from investigation_world.evidence.projector import project
from investigation_world.tasks.spec import TaskFamily, generate_task_bundle
from investigation_world.verifier.aggregate import verify
from investigation_world.world.generator import WorldFactory, WorldGenerationConfig


def _benchmark_world(seed=3):
    world = WorldFactory.generate(
        seed,
        WorldGenerationConfig(num_people=30, num_organizations=15, num_addresses=15),
    )
    return project(world, seed=seed)[0]


def _relationship_instance(world):
    for instance in generate_task_bundle(world, count=60, seed=9):
        if (
            instance.public.family in {TaskFamily.OWNERSHIP, TaskFamily.TEMPORAL, TaskFamily.DUE_DILIGENCE}
            and instance.oracle.answerable
            and instance.oracle.relationship_truth
        ):
            return instance
    raise AssertionError("expected an answerable relationship task")


def _perfect_relationships(world, instance):
    return [
        {
            "subject": world.entity_display_name(target.subject_id, instance.public.query_date),
            "predicate": target.predicate.value,
            "object": world.entity_display_name(target.object_id, instance.public.query_date),
            "valid_at": instance.public.query_date.isoformat() if instance.public.query_date else None,
        }
        for target in instance.oracle.relationship_truth
    ]


def test_empty_answer_gets_zero_reward_on_answerable_task():
    world = _benchmark_world()
    instance = _relationship_instance(world)
    empty = InvestigationResult(overall_confidence=0.0)
    score = verify(empty, world, task=instance.public, oracle=instance.oracle)
    assert score["overall_reward"] == 0.0


def test_answer_stuffing_reduces_reward():
    world = _benchmark_world(5)
    instance = _relationship_instance(world)
    relationships = _perfect_relationships(world, instance)
    good = InvestigationResult(relationships=relationships, overall_confidence=1.0)

    wrong_subject = next(
        person_id
        for person_id in world.people
        if all(person_id != target.subject_id for target in instance.oracle.relationship_truth)
    )
    bad_relationships = [
        *relationships,
        {
            "subject": world.entity_display_name(wrong_subject),
            "predicate": "OWNS",
            "object": world.entity_display_name(instance.oracle.target_entity_ids[0]),
            "valid_at": instance.public.query_date.isoformat() if instance.public.query_date else None,
        },
    ]
    stuffed = InvestigationResult(relationships=bad_relationships, overall_confidence=1.0)
    good_score = verify(good, world, task=instance.public, oracle=instance.oracle)
    stuffed_score = verify(stuffed, world, task=instance.public, oracle=instance.oracle)
    assert good_score["relationship_precision"] >= stuffed_score["relationship_precision"]
    assert good_score["overall_reward"] > stuffed_score["overall_reward"]
    assert stuffed_score["unsupported_claim_count"] >= 1


def test_false_entity_merge_is_penalized_against_hidden_identity():
    world = _benchmark_world(8)
    identity_instances = [
        instance
        for instance in generate_task_bundle(world, count=80, seed=4)
        if instance.public.family == TaskFamily.ENTITY_RESOLUTION and instance.oracle.answerable
    ]
    assert identity_instances
    instance = identity_instances[0]
    target = instance.oracle.identity_truth[0]
    correct = InvestigationResult(
        identity_assertions=[
            {"left": target.left_ref, "right": target.right_ref, "same_entity": target.same_entity}
        ],
        overall_confidence=1.0,
    )
    wrong = InvestigationResult(
        identity_assertions=[
            {"left": target.left_ref, "right": target.right_ref, "same_entity": not target.same_entity}
        ],
        overall_confidence=1.0,
    )
    correct_score = verify(correct, world, task=instance.public, oracle=instance.oracle)
    wrong_score = verify(wrong, world, task=instance.public, oracle=instance.oracle)
    assert correct_score["overall_reward"] > wrong_score["overall_reward"]
    if not target.same_entity:
        assert wrong_score["false_merge_count"] == 1


def test_ownership_transfer_changes_temporal_truth():
    world = WorldFactory.generate(
        11,
        WorldGenerationConfig(num_people=30, num_organizations=15, num_addresses=15),
    )
    event = next(event for event in world.events if event.event_type == "OwnershipTransferred")
    organization_id = event.payload["organization_id"]
    previous_owner = event.payload["from_person_id"]
    next_owner = event.payload["to_person_id"]
    before = {
        (relationship.subject_id, relationship.object_id)
        for relationship in world.relationships_at(event.timestamp - timedelta(days=1))
        if relationship.predicate.value == "OWNS" and relationship.object_id == organization_id
    }
    after = {
        (relationship.subject_id, relationship.object_id)
        for relationship in world.relationships_at(event.timestamp)
        if relationship.predicate.value == "OWNS" and relationship.object_id == organization_id
    }
    assert (previous_owner, organization_id) in before
    assert (previous_owner, organization_id) not in after
    assert (next_owner, organization_id) in after
