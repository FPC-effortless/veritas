from datetime import date

import pytest

from investigation_world.core.provenance import ProvenanceDAG
from investigation_world.world.generator import WorldFactory, WorldGenerationConfig, validate_world


def test_seed_reproducibility():
    config = WorldGenerationConfig(num_people=20, num_organizations=10, num_addresses=10)
    assert WorldFactory.generate(42, config).model_dump() == WorldFactory.generate(42, config).model_dump()
    assert WorldFactory.generate(42, config).model_dump() != WorldFactory.generate(43, config).model_dump()


def test_scale_and_temporal_query():
    world = WorldFactory.generate(
        7,
        WorldGenerationConfig(num_people=100, num_organizations=50, num_addresses=50),
    )
    assert len(world.people) == 100
    assert len(world.organizations) == 50
    assert len(world.relationships) >= 300
    assert len(world.events) >= 200
    assert world.relationships_at(date(2020, 1, 1))
    assert not validate_world(world)


def test_canonical_surface_names_are_unique_at_reference_scale():
    world = WorldFactory.generate(19)
    person_names = [person.canonical_name for person in world.people.values()]
    organization_names = [organization.legal_name for organization in world.organizations.values()]
    assert len(person_names) == len(set(person_names))
    assert len(organization_names) == len(set(organization_names))


def test_organizational_relationships_never_predate_incorporation():
    world = WorldFactory.generate(23)
    for relationship in world.relationships:
        for entity_id in (relationship.subject_id, relationship.object_id):
            organization = world.organizations.get(entity_id)
            if organization is not None:
                assert relationship.valid_from >= organization.incorporation_date


def test_provenance_laundering():
    provenance = ProvenanceDAG()
    provenance.add_citation("B", "A")
    provenance.add_citation("C", "B")
    provenance.add_citation("D", "C")
    assert provenance.independent_source_count(["B", "C", "D"]) == 1
    with pytest.raises(ValueError):
        provenance.add_citation("A", "D")
