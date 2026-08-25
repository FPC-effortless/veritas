from random import Random

from investigation_world.core.models import SourceType
from investigation_world.evidence.projector import _surface_label, project
from investigation_world.world.generator import WorldFactory, WorldGenerationConfig


def _projected_world():
    world = WorldFactory.generate(
        42,
        WorldGenerationConfig(num_people=24, num_organizations=12, num_addresses=12),
    )
    return project(world, 42)[0]


def test_public_documents_strip_private_fields():
    world = _projected_world()
    public = world.public_documents()
    assert public
    for document in public:
        assert not hasattr(document, "source_id")
        assert not hasattr(document, "claim_ids")
        assert not hasattr(document, "is_stale")
        payload = document.model_dump()
        assert "truth_status" not in payload
        assert "canonical_id" not in payload


def test_public_document_text_never_contains_canonical_entity_ids():
    world = _projected_world()
    canonical_ids = [
        *world.people.keys(),
        *world.organizations.keys(),
        *world.addresses.keys(),
        *world.domains.keys(),
    ]
    for document in world.public_documents():
        public_text = "\n".join(
            [document.title, document.body, document.url or "", *document.cites_document_ids]
        )
        assert not any(canonical_id in public_text for canonical_id in canonical_ids)


def test_guessed_canonical_ids_do_not_resolve_through_agent_reference_path():
    world = _projected_world()
    person_id = next(iter(world.people))
    organization_id = next(iter(world.organizations))
    assert world.resolve_entity_ref(person_id) == set()
    assert world.resolve_entity_ref(organization_id) == set()
    assert world.resolve_entity_ref(person_id, allow_canonical_ids=True) == {person_id}
    assert world.resolve_entity_ref(organization_id, allow_canonical_ids=True) == {organization_id}


def test_authoritative_labels_are_publication_time_consistent_across_renames():
    world = _projected_world()
    renamed = next(
        organization
        for organization in world.organizations.values()
        if len(organization.name_history) > 1
    )
    entity_id = renamed.canonical_id
    old_period = renamed.name_history[0]
    new_period = renamed.name_history[-1]
    assert old_period.valid_to is not None
    assert old_period.name != new_period.name

    before = _surface_label(world, entity_id, SourceType.REGISTRY, Random(0), old_period.valid_to)
    after = _surface_label(world, entity_id, SourceType.REGISTRY, Random(0), new_period.valid_from)
    filing_before = _surface_label(world, entity_id, SourceType.FILING, Random(0), old_period.valid_to)

    assert before == old_period.name
    assert filing_before == old_period.name
    assert after == new_period.name


def test_deterministic_world_and_evidence_serialization():
    left = project(WorldFactory.generate(42), 42)[0].model_dump(mode="json")
    right = project(WorldFactory.generate(42), 42)[0].model_dump(mode="json")
    different = project(WorldFactory.generate(43), 43)[0].model_dump(mode="json")
    assert left == right
    assert left != different
