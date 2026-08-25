from investigation_world.core.models import SourceType
from investigation_world.evidence.projector import project
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


def test_authoritative_documents_do_not_leak_future_renames():
    world = _projected_world()
    source_types = {source.source_id: source.source_type for source in world.sources}
    renamed = next(
        organization
        for organization in world.organizations.values()
        if len(organization.name_history) > 1
    )
    rename_date = renamed.name_history[-1].valid_from
    future_name = renamed.legal_name
    authoritative_before = [
        document
        for document in world.documents
        if renamed.canonical_id in document.entity_ids
        and document.published_at < rename_date
        and source_types[document.source_id] in {SourceType.REGISTRY, SourceType.FILING}
    ]
    assert authoritative_before
    for document in authoritative_before:
        assert future_name not in document.title
        assert future_name not in document.body


def test_deterministic_world_and_evidence_serialization():
    left = project(WorldFactory.generate(42), 42)[0].model_dump(mode="json")
    right = project(WorldFactory.generate(42), 42)[0].model_dump(mode="json")
    different = project(WorldFactory.generate(43), 43)[0].model_dump(mode="json")
    assert left == right
    assert left != different
