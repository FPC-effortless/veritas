from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum
from random import Random

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.core.models import CanonicalWorld, Predicate, TruthStatus


class TaskFamily(StrEnum):
    ENTITY_RESOLUTION = "entity_resolution"
    OWNERSHIP = "ownership_reconstruction"
    TEMPORAL = "temporal_reconstruction"
    PROVENANCE = "provenance"
    CONFLICT = "conflict_resolution"
    DUE_DILIGENCE = "due_diligence"


class RelationshipTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_id: str
    predicate: Predicate
    object_id: str
    valid_at: date | None = None

    def key(self) -> tuple[str, str, str]:
        return (self.subject_id, self.predicate.value, self.object_id)


class IdentityTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left_ref: str
    right_ref: str
    same_entity: bool


class TaskSpec(BaseModel):
    """Agent-visible task definition. It intentionally contains no verifier truth."""

    model_config = ConfigDict(extra="forbid")
    task_id: str
    world_id: str
    family: TaskFamily
    objective: str
    target_refs: list[str] = Field(default_factory=list)
    query_date: date | None = None
    constraints: dict[str, object] = Field(default_factory=dict)
    difficulty: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class TaskOracle(BaseModel):
    """Privileged verifier-only task state. Never return this through agent-facing APIs."""

    model_config = ConfigDict(extra="forbid")
    task_id: str
    answerable: bool = True
    answerability_reason: str = ""
    target_entity_ids: list[str] = Field(default_factory=list)
    relationship_truth: list[RelationshipTarget] = Field(default_factory=list)
    identity_truth: list[IdentityTarget] = Field(default_factory=list)
    provenance_document_ids: list[str] = Field(default_factory=list)
    provenance_root_count: int | None = None


class TaskInstance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    public: TaskSpec
    oracle: TaskOracle


def _config_dates(world: CanonicalWorld) -> tuple[date, date]:
    raw = world.metadata.get("config", {})
    start = raw.get("timeline_start")
    end = raw.get("timeline_end")
    if isinstance(start, str):
        start = date.fromisoformat(start)
    if isinstance(end, str):
        end = date.fromisoformat(end)
    if not isinstance(start, date):
        start = min((r.valid_from for r in world.relationships), default=date(2018, 1, 1))
    if not isinstance(end, date):
        end = max((e.timestamp for e in world.events), default=date(2026, 1, 1)) + timedelta(days=1)
    return start, end


def _random_date(world: CanonicalWorld, rng: Random) -> date:
    start, end = _config_dates(world)
    span = max(1, (end - start).days)
    return start + timedelta(days=rng.randrange(span))


def _roots(world: CanonicalWorld, document_ids: list[str]) -> set[str]:
    parents = {
        key: set(value)
        for key, value in (world.metadata.get("provenance_parents", {}) or {}).items()
    }

    def ancestors(document_id: str) -> set[str]:
        output: set[str] = set()
        stack = list(parents.get(document_id, ()))
        while stack:
            current = stack.pop()
            if current in output:
                continue
            output.add(current)
            stack.extend(parents.get(current, ()))
        return output

    roots: set[str] = set()
    for document_id in document_ids:
        lineage = ancestors(document_id) | {document_id}
        roots.update(item for item in lineage if not parents.get(item))
    return roots


def _relationship_answerable(world: CanonicalWorld, targets: list[RelationshipTarget]) -> bool:
    if not targets:
        return False
    claims_by_key = {}
    for claim in world.claims:
        if claim.object_id is None:
            continue
        claims_by_key.setdefault((claim.subject_id, claim.predicate.value, claim.object_id), []).append(claim)
    for target in targets:
        supporting = claims_by_key.get(target.key(), [])
        if not any(claim.truth_status in {TruthStatus.TRUE, TruthStatus.PARTIALLY_TRUE} for claim in supporting):
            return False
    return True


def _entity_ref(world: CanonicalWorld, entity_id: str, when: date | None = None) -> str:
    return world.entity_display_name(entity_id, when)


def generate_task_bundle(world: CanonicalWorld, count: int = 24, seed: int = 0) -> list[TaskInstance]:
    """Generate concrete task instances plus private verifier oracles."""
    if not world.people or not world.organizations:
        raise ValueError("task generation requires a populated canonical world")

    rng = Random(seed)
    families = list(TaskFamily)
    organizations = sorted(world.organizations)
    people = sorted(world.people)
    documents = sorted(world.documents, key=lambda document: document.document_id)
    output: list[TaskInstance] = []

    for index in range(count):
        family = families[(index + seed) % len(families)]
        task_id = f"TASK-{index + 1:06d}"
        query_date = _random_date(world, rng)
        target_refs: list[str] = []
        target_entity_ids: list[str] = []
        relationship_truth: list[RelationshipTarget] = []
        identity_truth: list[IdentityTarget] = []
        provenance_document_ids: list[str] = []
        provenance_root_count: int | None = None
        answerable = True
        answerability_reason = "sufficient projected evidence exists"

        if family == TaskFamily.ENTITY_RESOLUTION:
            left_id = people[rng.randrange(len(people))]
            left_person = world.people[left_id]
            if rng.random() < 0.65:
                right_id = left_id
                left_ref = left_person.canonical_name
                right_ref = left_person.aliases[0] if left_person.aliases else left_person.canonical_name
                same_entity = True
            else:
                right_id = people[(people.index(left_id) + 1 + rng.randrange(len(people) - 1)) % len(people)]
                left_ref = left_person.canonical_name
                right_ref = world.people[right_id].canonical_name
                same_entity = False
            target_refs = [left_ref, right_ref]
            target_entity_ids = sorted({left_id, right_id})
            identity_truth = [
                IdentityTarget(left_ref=left_ref, right_ref=right_ref, same_entity=same_entity)
            ]
            answerable = len(world.resolve_entity_ref(left_ref)) == 1 and len(world.resolve_entity_ref(right_ref)) == 1
            if not answerable:
                answerability_reason = "surface labels are ambiguous in the projected evidence world"
            objective = f"Determine whether the records '{left_ref}' and '{right_ref}' refer to the same entity."

        elif family == TaskFamily.OWNERSHIP:
            organization_id = organizations[rng.randrange(len(organizations))]
            target_refs = [_entity_ref(world, organization_id, query_date)]
            target_entity_ids = [organization_id]
            truth = [
                relationship
                for relationship in world.relationships_at(query_date)
                if relationship.object_id == organization_id and relationship.predicate == Predicate.OWNS
            ]
            relationship_truth = [
                RelationshipTarget(
                    subject_id=relationship.subject_id,
                    predicate=relationship.predicate,
                    object_id=relationship.object_id,
                    valid_at=query_date,
                )
                for relationship in truth
            ]
            answerable = _relationship_answerable(world, relationship_truth)
            if not answerable:
                answerability_reason = "projected evidence does not support every required ownership edge"
            objective = (
                f"Reconstruct the ownership of {target_refs[0]} as of {query_date.isoformat()}. "
                "Return only relationships supported by evidence and state unresolved gaps."
            )

        elif family == TaskFamily.TEMPORAL:
            organization_id = organizations[rng.randrange(len(organizations))]
            target_refs = [_entity_ref(world, organization_id, query_date)]
            target_entity_ids = [organization_id]
            truth = [
                relationship
                for relationship in world.entity_state_at(organization_id, query_date)
                if relationship.predicate
                in {Predicate.OWNS, Predicate.DIRECTOR_OF, Predicate.EMPLOYED_BY, Predicate.REGISTERED_AT}
            ]
            relationship_truth = [
                RelationshipTarget(
                    subject_id=relationship.subject_id,
                    predicate=relationship.predicate,
                    object_id=relationship.object_id,
                    valid_at=query_date,
                )
                for relationship in truth
            ]
            answerable = _relationship_answerable(world, relationship_truth)
            if not answerable:
                answerability_reason = "historical state is only partially represented in public evidence"
            objective = (
                f"Reconstruct the relevant state of {target_refs[0]} on {query_date.isoformat()}, "
                "distinguishing historical from current facts."
            )

        elif family == TaskFamily.PROVENANCE:
            candidates = [document for document in documents if document.cites_document_ids]
            if candidates:
                chosen = candidates[rng.randrange(len(candidates))]
                provenance_document_ids = [chosen.document_id, *chosen.cites_document_ids]
                provenance_root_count = len(_roots(world, provenance_document_ids))
                target_refs = provenance_document_ids
                objective = (
                    "Determine how many independent root sources underlie the supplied documents "
                    f"{', '.join(provenance_document_ids)}."
                )
            else:
                answerable = False
                answerability_reason = "no citation-linked documents were projected"
                objective = "Determine whether the supplied reports derive from independent sources."

        elif family == TaskFamily.CONFLICT:
            grouped: dict[tuple[str, str, str], list] = {}
            for claim in world.claims:
                if claim.object_id is not None:
                    grouped.setdefault(
                        (claim.subject_id, claim.predicate.value, claim.object_id), []
                    ).append(claim)
            conflict_keys = [
                key
                for key, claims in grouped.items()
                if any(claim.truth_status == TruthStatus.TRUE for claim in claims)
                and any(claim.truth_status in {TruthStatus.FALSE, TruthStatus.OUTDATED} for claim in claims)
            ]
            if conflict_keys:
                subject_id, predicate, object_id = conflict_keys[rng.randrange(len(conflict_keys))]
                target_entity_ids = [subject_id, object_id]
                target_refs = [
                    _entity_ref(world, subject_id, query_date),
                    _entity_ref(world, object_id, query_date),
                ]
                relationship_truth = [
                    RelationshipTarget(
                        subject_id=subject_id,
                        predicate=Predicate(predicate),
                        object_id=object_id,
                        valid_at=query_date,
                    )
                ]
                objective = (
                    f"Adjudicate conflicting records concerning {target_refs[0]} and {target_refs[1]}; "
                    "identify the best-supported relationship and explain uncertainty."
                )
            else:
                answerable = False
                answerability_reason = "no suitable cross-source conflict was projected"
                objective = "Adjudicate the conflicting synthetic corporate records."

        else:  # due diligence
            organization_id = organizations[rng.randrange(len(organizations))]
            target_refs = [_entity_ref(world, organization_id, query_date)]
            target_entity_ids = [organization_id]
            truth = [
                relationship
                for relationship in world.entity_state_at(organization_id, query_date)
                if relationship.predicate
                in {
                    Predicate.OWNS,
                    Predicate.DIRECTOR_OF,
                    Predicate.EMPLOYED_BY,
                    Predicate.REGISTERED_AT,
                    Predicate.AFFILIATED_WITH,
                }
            ]
            relationship_truth = [
                RelationshipTarget(
                    subject_id=relationship.subject_id,
                    predicate=relationship.predicate,
                    object_id=relationship.object_id,
                    valid_at=query_date,
                )
                for relationship in truth[:12]
            ]
            answerable = _relationship_answerable(world, relationship_truth)
            if not answerable:
                answerability_reason = "compound due-diligence target has unresolved evidence gaps"
            objective = (
                f"Perform evidence-grounded due diligence on {target_refs[0]} as of {query_date.isoformat()}, "
                "covering ownership, leadership, affiliations, and registered location."
            )

        public = TaskSpec(
            task_id=task_id,
            world_id=world.world_id,
            family=family,
            objective=objective,
            target_refs=target_refs,
            query_date=query_date if family not in {TaskFamily.ENTITY_RESOLUTION, TaskFamily.PROVENANCE} else None,
            constraints={"must_cite_evidence": True, "canonical_ids_are_not_available": True},
            difficulty={
                "candidate_entities": float(2 + rng.randrange(10)),
                "required_graph_hops": float(1 + rng.randrange(4)),
                "temporal_depth": float(1 + rng.randrange(8)),
                "noise_ratio": round(rng.random(), 3),
                "budget_tightness": round(rng.random(), 3),
            },
            metadata={"generator_seed": seed, "generator_version": "0.4.0"},
        )
        oracle = TaskOracle(
            task_id=task_id,
            answerable=answerable,
            answerability_reason=answerability_reason,
            target_entity_ids=target_entity_ids,
            relationship_truth=relationship_truth,
            identity_truth=identity_truth,
            provenance_document_ids=provenance_document_ids,
            provenance_root_count=provenance_root_count,
        )
        output.append(TaskInstance(public=public, oracle=oracle))

    return output


def generate_tasks(world: CanonicalWorld, count: int = 24, seed: int = 0) -> list[TaskSpec]:
    return [instance.public for instance in generate_task_bundle(world, count=count, seed=seed)]


def split_manifest(tasks: list[TaskSpec]) -> dict[str, list[str]]:
    task_ids = [task.task_id for task in tasks]
    train_end = max(1, int(len(task_ids) * 0.6))
    public_end = max(train_end, int(len(task_ids) * 0.8))
    return {
        "train": task_ids[:train_end],
        "public_eval": task_ids[train_end:public_end],
        "private_eval": task_ids[public_end:],
    }
