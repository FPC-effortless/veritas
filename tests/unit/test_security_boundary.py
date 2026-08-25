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


def test_deterministic_world_and_evidence_serialization():
    left = project(WorldFactory.generate(42), 42)[0].model_dump(mode="json")
    right = project(WorldFactory.generate(42), 42)[0].model_dump(mode="json")
    different = project(WorldFactory.generate(43), 43)[0].model_dump(mode="json")
    assert left == right
    assert left != different
