from investigation_world.evidence.projector import project
from investigation_world.tools.server import (
    EpisodeCreateRequest,
    create_episode,
    delete_episode,
    get_budget,
    registry_search,
    web_search,
)
from investigation_world.world.generator import WorldFactory, WorldGenerationConfig


def _world():
    world = WorldFactory.generate(
        17,
        WorldGenerationConfig(num_people=24, num_organizations=12, num_addresses=12),
    )
    return project(world, seed=17)[0]


def test_episode_budgets_are_isolated():
    world = _world()
    first = create_episode(EpisodeCreateRequest(world=world, task_seed=1))["episode_id"]
    second = create_episode(EpisodeCreateRequest(world=world, task_seed=2))["episode_id"]
    try:
        web_search(first, "Aster", limit=5)
        assert get_budget(first)["spent"] == 1
        assert get_budget(first)["calls"] == 1
        assert get_budget(second)["spent"] == 0
        assert get_budget(second)["calls"] == 0
    finally:
        delete_episode(first)
        delete_episode(second)


def test_registry_and_web_tools_have_distinct_source_surfaces():
    world = _world()
    episode_id = create_episode(EpisodeCreateRequest(world=world, task_seed=3))["episode_id"]
    try:
        registry = registry_search(episode_id, "Synthetic", limit=20)
        web = web_search(episode_id, "Aster", limit=20)
        assert registry
        assert all(item["source_type"] == "registry" for item in registry)
        assert all(
            item["source_type"] in {"news", "company_site", "directory"}
            for item in web
        )
    finally:
        delete_episode(episode_id)
