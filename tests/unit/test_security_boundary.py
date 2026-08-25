from investigation_world.world.generator import WorldFactory
from investigation_world.evidence.projector import project

def test_public_documents_strip_canonical_metadata():
    world, _ = project(WorldFactory.generate(42), 42)
    public = world.public_documents()
    assert public
    for document in public:
        assert not hasattr(document, 'source_id')
        assert not hasattr(document, 'claim_ids')
        assert not hasattr(document, 'is_stale')

def test_deterministic_world_serialization():
    assert WorldFactory.generate(42).model_dump(mode='json') == WorldFactory.generate(42).model_dump(mode='json')
    assert WorldFactory.generate(42).model_dump(mode='json') != WorldFactory.generate(43).model_dump(mode='json')

def test_public_documents_are_not_truth_labeled():
    world, _ = project(WorldFactory.generate(42), 42)
    for document in world.public_documents():
        assert 'truth_status' not in document.model_dump()
        assert 'canonical_id' not in document.model_dump()
