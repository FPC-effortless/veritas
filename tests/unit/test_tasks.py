from investigation_world.evidence.projector import project
from investigation_world.tasks.spec import TaskFamily, generate_task_bundle, split_manifest
from investigation_world.world.generator import WorldFactory, WorldGenerationConfig


def _world():
    world = WorldFactory.generate(
        7,
        WorldGenerationConfig(num_people=30, num_organizations=15, num_addresses=15),
    )
    return project(world, seed=7)[0]


def test_task_families_are_concrete_and_oracles_are_private():
    world = _world()
    bundle = generate_task_bundle(world, count=48, seed=7)
    tasks = [instance.public for instance in bundle]
    assert {task.family for task in tasks} == set(TaskFamily)
    assert all(task.objective for task in tasks)
    assert all(not hasattr(task, "answerable") for task in tasks)
    assert all(not hasattr(task, "relationship_truth") for task in tasks)
    assert any(instance.oracle.relationship_truth for instance in bundle)
    assert all(instance.public.task_id == instance.oracle.task_id for instance in bundle)


def test_task_splits_do_not_overlap():
    tasks = [instance.public for instance in generate_task_bundle(_world(), count=30, seed=2)]
    manifest = split_manifest(tasks)
    assert not (set(manifest["train"]) & set(manifest["public_eval"]))
    assert not (set(manifest["train"]) & set(manifest["private_eval"]))
    assert not (set(manifest["public_eval"]) & set(manifest["private_eval"]))
    assert set().union(*map(set, manifest.values())) == {task.task_id for task in tasks}
