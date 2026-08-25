from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Predicate(StrEnum):
    OWNS = "OWNS"
    CONTROLS = "CONTROLS"
    DIRECTOR_OF = "DIRECTOR_OF"
    EMPLOYED_BY = "EMPLOYED_BY"
    REGISTERED_AT = "REGISTERED_AT"
    RESIDES_AT = "RESIDES_AT"
    SUBSIDIARY_OF = "SUBSIDIARY_OF"
    FORMERLY_NAMED = "FORMERLY_NAMED"
    AFFILIATED_WITH = "AFFILIATED_WITH"


class TruthStatus(StrEnum):
    TRUE = "true"
    FALSE = "false"
    PARTIALLY_TRUE = "partially_true"
    OUTDATED = "outdated"
    UNKNOWN = "unknown"


class SourceType(StrEnum):
    REGISTRY = "registry"
    COMPANY_SITE = "company_site"
    NEWS = "news"
    FILING = "filing"
    ARCHIVE = "archive"
    DIRECTORY = "directory"


class NamePeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    valid_from: date
    valid_to: date | None = None


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Person(Entity):
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    birth_year: int | None = None
    historical_addresses: list[str] = Field(default_factory=list)
    identifiers: dict[str, str] = Field(default_factory=dict)
    affiliations: list[str] = Field(default_factory=list)


class Organization(Entity):
    legal_name: str
    aliases: list[str] = Field(default_factory=list)
    registration_number: str
    incorporation_date: date
    dissolution_date: date | None = None
    organization_type: str = "company"
    historical_addresses: list[str] = Field(default_factory=list)
    status: str = "active"
    name_history: list[NamePeriod] = Field(default_factory=list)


class Address(Entity):
    synthetic_line: str
    city: str
    region: str
    postal_code: str


class Domain(Entity):
    hostname: str
    organization_id: str


class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relationship_id: str
    subject_id: str
    predicate: Predicate
    object_id: str
    valid_from: date
    valid_to: date | None = None
    created_by_event_id: str | None = None
    ended_by_event_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    event_type: str
    timestamp: date
    payload: dict[str, Any]


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    subject_id: str
    predicate: Predicate
    object_id: str | None = None
    value: Any = None
    valid_from: date | None = None
    valid_to: date | None = None
    truth_status: TruthStatus = TruthStatus.UNKNOWN
    origin_source_id: str
    parent_claim_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    name: str
    source_type: SourceType
    reliability_baseline: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str
    source_id: str
    title: str
    body: str
    published_at: date
    entity_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    cites_document_ids: list[str] = Field(default_factory=list)
    url: str | None = None
    is_stale: bool = False


class PublicDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str
    title: str
    body: str
    published_at: date
    source_type: SourceType
    url: str | None = None
    cites_document_ids: list[str] = Field(default_factory=list)


class CanonicalWorld(BaseModel):
    world_id: str
    seed: int
    people: dict[str, Person] = Field(default_factory=dict)
    organizations: dict[str, Organization] = Field(default_factory=dict)
    addresses: dict[str, Address] = Field(default_factory=dict)
    domains: dict[str, Domain] = Field(default_factory=dict)
    relationships: list[Relationship] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def relationships_at(self, timestamp: date) -> list[Relationship]:
        return [
            relationship
            for relationship in self.relationships
            if relationship.valid_from <= timestamp
            and (relationship.valid_to is None or timestamp <= relationship.valid_to)
        ]

    def entity_state_at(self, entity_id: str, timestamp: date) -> list[Relationship]:
        return [
            relationship
            for relationship in self.relationships_at(timestamp)
            if relationship.subject_id == entity_id or relationship.object_id == entity_id
        ]

    def entity_display_name(self, entity_id: str, timestamp: date | None = None) -> str:
        if entity_id in self.people:
            return self.people[entity_id].canonical_name
        if entity_id in self.organizations:
            organization = self.organizations[entity_id]
            if timestamp and organization.name_history:
                for period in organization.name_history:
                    if period.valid_from <= timestamp and (
                        period.valid_to is None or timestamp <= period.valid_to
                    ):
                        return period.name
            return organization.legal_name
        if entity_id in self.addresses:
            address = self.addresses[entity_id]
            return f"{address.synthetic_line}, {address.city}"
        if entity_id in self.domains:
            return self.domains[entity_id].hostname
        return entity_id

    def resolve_entity_ref(
        self,
        reference: str,
        *,
        allow_canonical_ids: bool = False,
    ) -> set[str]:
        """Resolve an observable label without accepting hidden IDs unless explicitly privileged."""
        needle = reference.strip().casefold()
        if not needle:
            return set()
        resolved: set[str] = set()
        if allow_canonical_ids:
            all_ids = set(self.people) | set(self.organizations) | set(self.addresses) | set(self.domains)
            if reference in all_ids:
                resolved.add(reference)
        for entity_id, person in self.people.items():
            labels = [person.canonical_name, *person.aliases, *person.identifiers.values()]
            if any(label.casefold() == needle for label in labels):
                resolved.add(entity_id)
        for entity_id, organization in self.organizations.items():
            labels = [
                organization.legal_name,
                organization.registration_number,
                *organization.aliases,
                *(period.name for period in organization.name_history),
            ]
            if any(label.casefold() == needle for label in labels):
                resolved.add(entity_id)
        for entity_id, address in self.addresses.items():
            labels = [
                address.synthetic_line,
                f"{address.synthetic_line}, {address.city}",
                address.postal_code,
            ]
            if any(label.casefold() == needle for label in labels):
                resolved.add(entity_id)
        for entity_id, domain in self.domains.items():
            if domain.hostname.casefold() == needle:
                resolved.add(entity_id)
        return resolved

    def public_documents(self) -> list[PublicDocument]:
        source_types = {source.source_id: source.source_type for source in self.sources}
        return [
            PublicDocument(
                document_id=document.document_id,
                title=document.title,
                body=document.body,
                published_at=document.published_at,
                source_type=source_types.get(document.source_id, SourceType.DIRECTORY),
                url=document.url,
                cites_document_ids=document.cites_document_ids,
            )
            for document in self.documents
        ]

    def validate(self) -> bool:
        ids = set(self.people) | set(self.organizations) | set(self.addresses) | set(self.domains)
        assert len(ids) == len(self.people) + len(self.organizations) + len(self.addresses) + len(self.domains)
        assert len({person.canonical_name for person in self.people.values()}) == len(self.people)
        assert len({organization.legal_name for organization in self.organizations.values()}) == len(
            self.organizations
        )
        for organization in self.organizations.values():
            assert organization.dissolution_date is None or organization.incorporation_date <= organization.dissolution_date
            for period in organization.name_history:
                assert period.valid_to is None or period.valid_from <= period.valid_to
        for relationship in self.relationships:
            assert relationship.subject_id in ids
            assert relationship.object_id in ids
            assert relationship.valid_to is None or relationship.valid_from <= relationship.valid_to
        assert len({relationship.relationship_id for relationship in self.relationships}) == len(self.relationships)
        assert len({event.event_id for event in self.events}) == len(self.events)
        source_ids = {source.source_id for source in self.sources}
        claim_ids = {claim.claim_id for claim in self.claims}
        document_ids = {document.document_id for document in self.documents}
        for claim in self.claims:
            assert claim.subject_id in ids
            assert claim.object_id is None or claim.object_id in ids
            assert not source_ids or claim.origin_source_id in source_ids
            assert claim.valid_to is None or claim.valid_from is None or claim.valid_from <= claim.valid_to
        for document in self.documents:
            assert not source_ids or document.source_id in source_ids
            assert all(claim_id in claim_ids for claim_id in document.claim_ids)
            assert all(parent in document_ids for parent in document.cites_document_ids)
        return True


class InvestigationBudget(BaseModel):
    total_cost: int = Field(default=40, ge=1)
    max_tool_calls: int = Field(default=30, ge=1)
    spent: int = Field(default=0, ge=0)
    calls: int = Field(default=0, ge=0)

    def charge(self, cost: int) -> None:
        if cost < 0:
            raise ValueError("tool cost cannot be negative")
        if self.calls >= self.max_tool_calls or self.spent + cost > self.total_cost:
            raise ValueError("investigation budget exhausted")
        self.calls += 1
        self.spent += cost


class InvestigationResult(BaseModel):
    entities: list[dict[str, Any]] = Field(default_factory=list)
    identity_assertions: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    conclusion: str = ""
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class VerificationResult(BaseModel):
    identity: float = 0.0
    relationships: float = 0.0
    relationship_precision: float = 0.0
    relationship_recall: float = 0.0
    temporal: float = 0.0
    evidence_support: float = 0.0
    provenance: float = 0.0
    calibration: float = 0.0
    abstention: float = 0.0
    efficiency: float = 0.0
    false_merge_count: int = 0
    unsupported_claim_count: int = 0
    unresolved_reference_count: int = 0
    overall_reward: float = 0.0


def typed_id(prefix: str, number: int) -> str:
    return f"{prefix}-{number:06d}"
