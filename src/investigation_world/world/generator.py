from __future__ import annotations

from datetime import date, timedelta
from random import Random

from pydantic import BaseModel

from investigation_world.core.models import (
    Address,
    CanonicalWorld,
    Event,
    NamePeriod,
    Organization,
    Person,
    Predicate,
    Relationship,
)


class WorldGenerationConfig(BaseModel):
    num_people: int = 100
    num_organizations: int = 50
    num_addresses: int = 50
    timeline_start: date = date(2018, 1, 1)
    timeline_end: date = date(2026, 1, 1)
    relationship_density: float = 0.12
    alias_rate: float = 0.35
    rename_rate: float = 0.2
    ownership_chain_depth: int = 3


class WorldFactory:
    @staticmethod
    def generate(seed: int, config: WorldGenerationConfig | None = None) -> CanonicalWorld:
        config = config or WorldGenerationConfig()
        rng = Random(seed)
        world = CanonicalWorld(world_id=f"WORLD-{seed:06d}", seed=seed)

        def typed(prefix: str, number: int) -> str:
            return f"{prefix}-{number:06d}"

        for index in range(1, config.num_addresses + 1):
            address_id = typed("ADDR", index)
            world.addresses[address_id] = Address(
                canonical_id=address_id,
                synthetic_line=f"{100 + index} Meridian Loop",
                city=f"New {('Aster', 'Briar', 'Cedar')[index % 3]}",
                region=f"R-{index % 9:02d}",
                postal_code=f"SYN-{index:04d}",
            )

        first_names = ["Avery", "Daniel", "Mira", "Jonah", "Leila", "Chuka", "Nadia", "Rowan", "Sana", "Theo"]
        last_names = ["Okafor", "Ibarra", "Voss", "Marlowe", "Chen", "Bennett", "Kline", "Sato"]
        for index in range(1, config.num_people + 1):
            person_id = typed("PER", index)
            name = f"{first_names[index % len(first_names)]} {last_names[index % len(last_names)]}"
            aliases = [name.replace(" ", " C. ", 1)] if rng.random() < config.alias_rate else []
            world.people[person_id] = Person(
                canonical_id=person_id,
                canonical_name=name,
                aliases=aliases,
                birth_year=1965 + rng.randrange(35),
                historical_addresses=[typed("ADDR", 1 + (index % config.num_addresses))],
            )

        company_prefixes = ("Meridian", "Northstar", "Cobalt", "Juniper", "Palisade", "Lattice")
        company_suffixes = ("Industrial Systems", "Strategic Holdings", "Civic Works", "Analytics Group")
        for index in range(1, config.num_organizations + 1):
            organization_id = typed("ORG", index)
            name = f"{company_prefixes[index % 6]} {company_suffixes[index % 4]} Ltd"
            incorporation = config.timeline_start + timedelta(days=rng.randrange(900))
            world.organizations[organization_id] = Organization(
                canonical_id=organization_id,
                legal_name=name,
                aliases=[name[:-4]] if rng.random() < config.rename_rate else [],
                registration_number=f"SYN-REG-{index:05d}",
                incorporation_date=incorporation,
                historical_addresses=[typed("ADDR", 1 + (index % config.num_addresses))],
                name_history=[NamePeriod(name=name, valid_from=incorporation)],
            )

        event_number = 1
        relationship_number = 1

        def emit(event_type: str, timestamp: date, payload: dict) -> str:
            nonlocal event_number
            event_id = typed("EVENT", event_number)
            world.events.append(
                Event(event_id=event_id, event_type=event_type, timestamp=timestamp, payload=payload)
            )
            event_number += 1
            return event_id

        def add_relationship(
            subject_id: str,
            predicate: Predicate,
            object_id: str,
            valid_from: date,
            *,
            created_by_event_id: str | None = None,
            attributes: dict | None = None,
        ) -> Relationship:
            nonlocal relationship_number
            relationship = Relationship(
                relationship_id=typed("REL", relationship_number),
                subject_id=subject_id,
                predicate=predicate,
                object_id=object_id,
                valid_from=valid_from,
                created_by_event_id=created_by_event_id,
                attributes=attributes or {},
            )
            relationship_number += 1
            world.relationships.append(relationship)
            return relationship

        def close_relationship(relationship: Relationship, timestamp: date, event_id: str) -> None:
            if relationship.valid_to is None or relationship.valid_to >= timestamp:
                relationship.valid_to = timestamp - timedelta(days=1)
                relationship.ended_by_event_id = event_id

        # Initial residence state is represented as temporal relationships, not only metadata.
        for index in range(1, config.num_people + 1):
            person_id = typed("PER", index)
            address_id = typed("ADDR", 1 + (index % config.num_addresses))
            event_id = emit(
                "ResidenceEstablished",
                config.timeline_start,
                {"person_id": person_id, "address_id": address_id},
            )
            add_relationship(
                person_id,
                Predicate.RESIDES_AT,
                address_id,
                config.timeline_start,
                created_by_event_id=event_id,
            )

        for index in range(1, config.num_organizations + 1):
            organization_id = typed("ORG", index)
            address_id = typed("ADDR", 1 + (index % config.num_addresses))
            registration_event = emit(
                "OrganizationRegistered",
                world.organizations[organization_id].incorporation_date,
                {"organization_id": organization_id, "address_id": address_id},
            )
            add_relationship(
                organization_id,
                Predicate.REGISTERED_AT,
                address_id,
                world.organizations[organization_id].incorporation_date,
                created_by_event_id=registration_event,
            )

            person_id = typed("PER", 1 + (index * 7 % config.num_people))
            director_date = config.timeline_start + timedelta(days=(index * 37) % 1200)
            director_event = emit(
                "DirectorAppointed",
                director_date,
                {"person_id": person_id, "organization_id": organization_id},
            )
            add_relationship(
                person_id,
                Predicate.DIRECTOR_OF,
                organization_id,
                director_date,
                created_by_event_id=director_event,
            )

            owner_id = typed("PER", 1 + (index % config.num_people))
            owner_event = emit(
                "OwnershipEstablished",
                config.timeline_start + timedelta(days=80 + index),
                {"person_id": owner_id, "organization_id": organization_id, "percentage": 25.0},
            )
            add_relationship(
                owner_id,
                Predicate.OWNS,
                organization_id,
                config.timeline_start + timedelta(days=80 + index),
                created_by_event_id=owner_event,
                attributes={"percentage": 25.0, "ownership_class": "direct"},
            )

            if index > 1:
                parent_id = typed("ORG", max(1, index // 2))
                parent_event = emit(
                    "CorporateOwnershipEstablished",
                    config.timeline_start + timedelta(days=100 + index),
                    {"owner_id": parent_id, "organization_id": organization_id, "percentage": 75.0},
                )
                add_relationship(
                    parent_id,
                    Predicate.OWNS,
                    organization_id,
                    config.timeline_start + timedelta(days=100 + index),
                    created_by_event_id=parent_event,
                    attributes={"percentage": 75.0, "ownership_class": "corporate"},
                )

        for index in range(1, config.num_people + 1):
            if index % 3 == 0:
                person_id = typed("PER", index)
                organization_id = typed("ORG", 1 + (index % config.num_organizations))
                employment_date = config.timeline_start + timedelta(days=200 + index)
                event_id = emit(
                    "EmploymentStarted",
                    employment_date,
                    {"person_id": person_id, "organization_id": organization_id},
                )
                add_relationship(
                    person_id,
                    Predicate.EMPLOYED_BY,
                    organization_id,
                    employment_date,
                    created_by_event_id=event_id,
                )

        # Dense but deterministic affiliations exercise graph traversal without changing ownership truth.
        for organization_index in range(1, config.num_organizations + 1):
            organization_id = typed("ORG", organization_index)
            for hop in range(1, 5):
                person_index = ((organization_index + hop * 7 - 1) % config.num_people) + 1
                person_id = typed("PER", person_index)
                affiliation_date = config.timeline_start + timedelta(days=300 + hop * 17 + organization_index)
                event_id = emit(
                    "AffiliationObserved",
                    affiliation_date,
                    {"person_id": person_id, "organization_id": organization_id},
                )
                add_relationship(
                    person_id,
                    Predicate.AFFILIATED_WITH,
                    organization_id,
                    affiliation_date,
                    created_by_event_id=event_id,
                )

        # Renames update the canonical temporal name state.
        for index in range(1, min(10, config.num_organizations) + 1):
            organization_id = typed("ORG", index)
            organization = world.organizations[organization_id]
            rename_date = config.timeline_start + timedelta(days=500 + index * 23)
            old_name = organization.legal_name
            new_name = f"Legacy {old_name}"
            event_id = emit(
                "OrganizationRenamed",
                rename_date,
                {"organization_id": organization_id, "old_name": old_name, "new_name": new_name},
            )
            if organization.name_history:
                organization.name_history[-1].valid_to = rename_date - timedelta(days=1)
            organization.name_history.append(NamePeriod(name=new_name, valid_from=rename_date))
            organization.aliases = sorted(set([*organization.aliases, old_name]))
            organization.legal_name = new_name
            organization.metadata.setdefault("rename_event_ids", []).append(event_id)

        # Address changes close the previous residence relationship and open a successor.
        for index in range(1, config.num_people + 1):
            if index % 4 == 0:
                person_id = typed("PER", index)
                address_id = typed("ADDR", 1 + (index * 3 % config.num_addresses))
                change_date = config.timeline_start + timedelta(days=700 + index * 11)
                event_id = emit(
                    "AddressChanged",
                    change_date,
                    {"person_id": person_id, "address_id": address_id},
                )
                for relationship in world.relationships:
                    if (
                        relationship.subject_id == person_id
                        and relationship.predicate == Predicate.RESIDES_AT
                        and relationship.valid_to is None
                    ):
                        close_relationship(relationship, change_date, event_id)
                add_relationship(
                    person_id,
                    Predicate.RESIDES_AT,
                    address_id,
                    change_date,
                    created_by_event_id=event_id,
                )
                world.people[person_id].historical_addresses.append(address_id)

        # Ownership transfers now mutate the ownership graph rather than merely appending events.
        for organization_index in range(1, config.num_organizations + 1):
            organization_id = typed("ORG", organization_index)
            for phase in range(2):
                transfer_date = config.timeline_start + timedelta(days=1200 + phase * 600 + organization_index * 5)
                active_direct = [
                    relationship
                    for relationship in world.relationships_at(transfer_date)
                    if relationship.object_id == organization_id
                    and relationship.predicate == Predicate.OWNS
                    and relationship.subject_id in world.people
                    and relationship.attributes.get("ownership_class") == "direct"
                ]
                if not active_direct:
                    continue
                previous = active_direct[-1]
                next_owner_id = typed(
                    "PER",
                    1 + ((organization_index + phase + 11) % config.num_people),
                )
                event_id = emit(
                    "OwnershipTransferred",
                    transfer_date,
                    {
                        "organization_id": organization_id,
                        "from_person_id": previous.subject_id,
                        "to_person_id": next_owner_id,
                        "percentage": previous.attributes.get("percentage", 25.0),
                    },
                )
                close_relationship(previous, transfer_date, event_id)
                add_relationship(
                    next_owner_id,
                    Predicate.OWNS,
                    organization_id,
                    transfer_date,
                    created_by_event_id=event_id,
                    attributes={"percentage": 25.0, "ownership_class": "direct"},
                )

        # Dissolutions happen late enough that transfer history exists, then close active operational edges.
        for index in range(1, config.num_organizations + 1):
            if index % 2 == 0:
                organization_id = typed("ORG", index)
                dissolution_date = config.timeline_start + timedelta(days=2400 + index * 5)
                if dissolution_date >= config.timeline_end:
                    dissolution_date = config.timeline_end - timedelta(days=1)
                event_id = emit(
                    "OrganizationDissolved",
                    dissolution_date,
                    {"organization_id": organization_id},
                )
                organization = world.organizations[organization_id]
                organization.dissolution_date = dissolution_date
                organization.status = "dissolved"
                for relationship in world.relationships:
                    if (
                        relationship.valid_to is None
                        and relationship.predicate != Predicate.REGISTERED_AT
                        and (relationship.subject_id == organization_id or relationship.object_id == organization_id)
                        and relationship.valid_from < dissolution_date
                    ):
                        close_relationship(relationship, dissolution_date, event_id)

        world.metadata = {
            "generator_version": "0.4.0",
            "config": config.model_dump(mode="json"),
            "temporal_semantics": "event_sourced_relationship_intervals",
        }
        world.validate()
        return world


def validate_world(world: CanonicalWorld) -> list[str]:
    try:
        world.validate()
        return []
    except (AssertionError, ValueError) as error:
        return [str(error) or "world validation failed"]
