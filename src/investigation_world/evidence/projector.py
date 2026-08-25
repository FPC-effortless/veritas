from __future__ import annotations

from datetime import timedelta
from random import Random

from investigation_world.core.models import (
    CanonicalWorld,
    Claim,
    Document,
    Predicate,
    Source,
    SourceType,
    TruthStatus,
)
from investigation_world.core.provenance import ProvenanceDAG


def _surface_label(
    world: CanonicalWorld,
    entity_id: str,
    source_type: SourceType,
    rng: Random,
    published_at,
):
    if entity_id in world.people:
        person = world.people[entity_id]
        labels = [person.canonical_name, *person.aliases]
        if source_type in {SourceType.NEWS, SourceType.DIRECTORY} and len(labels) > 1:
            return labels[rng.randrange(len(labels))]
        return person.canonical_name
    if entity_id in world.organizations:
        organization = world.organizations[entity_id]
        historical_name = world.entity_display_name(entity_id, published_at)
        # Authoritative sources use the name valid when the record was published. Noisy sources may
        # use an alias, but must not import a future legal name into an earlier document.
        if source_type in {SourceType.REGISTRY, SourceType.FILING, SourceType.ARCHIVE}:
            return historical_name
        labels = [historical_name, *organization.aliases]
        labels = list(dict.fromkeys(labels))
        if source_type in {SourceType.NEWS, SourceType.DIRECTORY, SourceType.COMPANY_SITE} and len(labels) > 1:
            return labels[rng.randrange(len(labels))]
        return historical_name
    return world.entity_display_name(entity_id, published_at)


def _replacement_object(world: CanonicalWorld, object_id: str, rng: Random) -> str:
    if object_id in world.people:
        pool = sorted(world.people)
    elif object_id in world.organizations:
        pool = sorted(world.organizations)
    elif object_id in world.addresses:
        pool = sorted(world.addresses)
    elif object_id in world.domains:
        pool = sorted(world.domains)
    else:
        return object_id
    if len(pool) < 2:
        return object_id
    candidate = object_id
    while candidate == object_id:
        candidate = pool[rng.randrange(len(pool))]
    return candidate


def _render_statement(
    source_type: SourceType,
    subject: str,
    predicate: Predicate,
    object_: str,
    truth_status: TruthStatus,
) -> str:
    qualifier = {
        TruthStatus.TRUE: "",
        TruthStatus.OUTDATED: "Historical records indicate that ",
        TruthStatus.FALSE: "A record asserts that ",
        TruthStatus.PARTIALLY_TRUE: "Available records partially indicate that ",
        TruthStatus.UNKNOWN: "An unverified record suggests that ",
    }[truth_status]
    phrasing = {
        SourceType.REGISTRY: f"{subject} — {predicate.value.replace('_', ' ').lower()} — {object_}.",
        SourceType.FILING: f"The filing records {subject} as {predicate.value.replace('_', ' ').lower()} {object_}.",
        SourceType.COMPANY_SITE: f"{subject} is described as {predicate.value.replace('_', ' ').lower()} {object_}.",
        SourceType.NEWS: f"Reporting links {subject} to {object_} through {predicate.value.replace('_', ' ').lower()}.",
        SourceType.ARCHIVE: f"Archived material records {subject} as {predicate.value.replace('_', ' ').lower()} {object_}.",
        SourceType.DIRECTORY: f"Directory entry: {subject}; {predicate.value.replace('_', ' ').lower()}; {object_}.",
    }[source_type]
    return qualifier + phrasing


def project(
    world: CanonicalWorld,
    seed: int = 0,
    omission_probability: float = 0.08,
    stale_probability: float = 0.12,
):
    """Project hidden canonical truth into noisy, leakage-safe public evidence."""
    rng = Random(seed)
    specs = [
        ("Synthetic Registry", SourceType.REGISTRY, 0.95),
        ("Aster Ledger", SourceType.NEWS, 0.65),
        ("Corporate Website", SourceType.COMPANY_SITE, 0.55),
        ("Synthetic Archive", SourceType.ARCHIVE, 0.80),
        ("Filing Office", SourceType.FILING, 0.90),
        ("Business Directory", SourceType.DIRECTORY, 0.35),
    ]
    world.sources = [
        Source(
            source_id=f"SOURCE-{index:06d}",
            name=name,
            source_type=source_type,
            reliability_baseline=reliability,
        )
        for index, (name, source_type, reliability) in enumerate(specs, 1)
    ]
    world.claims = []
    world.documents = []
    dag = ProvenanceDAG()
    claim_number = 1
    document_number = 1

    for relationship in world.relationships:
        prior_document: str | None = None
        for source in world.sources:
            source_omission = min(
                0.85,
                omission_probability + (1.0 - source.reliability_baseline) * 0.12,
            )
            if rng.random() < source_omission:
                continue

            publication_lag = rng.randrange(0, 180)
            published_at = relationship.valid_from + timedelta(days=publication_lag)
            is_temporally_stale = (
                relationship.valid_to is not None and published_at > relationship.valid_to
            )
            random_stale = rng.random() < stale_probability * (1.15 - source.reliability_baseline)
            false_probability = max(0.01, (1.0 - source.reliability_baseline) * 0.20)
            partial_probability = max(0.01, (1.0 - source.reliability_baseline) * 0.10)

            object_id = relationship.object_id
            roll = rng.random()
            if roll < false_probability:
                truth_status = TruthStatus.FALSE
                object_id = _replacement_object(world, relationship.object_id, rng)
            elif roll < false_probability + partial_probability:
                truth_status = TruthStatus.PARTIALLY_TRUE
            elif is_temporally_stale or random_stale:
                truth_status = TruthStatus.OUTDATED
            else:
                truth_status = TruthStatus.TRUE

            claim_id = f"CLAIM-{claim_number:06d}"
            claim = Claim(
                claim_id=claim_id,
                subject_id=relationship.subject_id,
                predicate=relationship.predicate,
                object_id=object_id,
                valid_from=relationship.valid_from,
                valid_to=relationship.valid_to,
                truth_status=truth_status,
                origin_source_id=source.source_id,
                metadata={"relationship_id": relationship.relationship_id},
            )
            world.claims.append(claim)
            claim_number += 1

            subject_label = _surface_label(
                world,
                relationship.subject_id,
                source.source_type,
                rng,
                published_at,
            )
            object_label = _surface_label(
                world,
                object_id,
                source.source_type,
                rng,
                published_at,
            )
            body = _render_statement(
                source.source_type,
                subject_label,
                relationship.predicate,
                object_label,
                truth_status,
            )
            document_id = f"DOC-{document_number:06d}"
            cites = []
            if prior_document and rng.random() < 0.30:
                cites = [prior_document]
            title_subject = subject_label[:80]
            document = Document(
                document_id=document_id,
                source_id=source.source_id,
                title=f"{source.name}: {title_subject}",
                body=body,
                published_at=published_at,
                entity_ids=[relationship.subject_id, object_id],
                claim_ids=[claim_id],
                cites_document_ids=cites,
                url=f"https://synthetic.invalid/{source.source_type.value}/{document_id.lower()}",
                is_stale=truth_status == TruthStatus.OUTDATED,
            )
            world.documents.append(document)
            if cites:
                dag.add_citation(document_id, cites[0])
            prior_document = document_id
            document_number += 1

    world.metadata["provenance_parents"] = {
        key: sorted(value) for key, value in dag.parents.items()
    }
    world.metadata["evidence_projection_version"] = "0.4.0"
    world.metadata["evidence_seed"] = seed
    world.validate()
    return world, dag
