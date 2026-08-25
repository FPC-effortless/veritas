from __future__ import annotations

from datetime import date
from typing import Any

from investigation_world.core.models import (
    CanonicalWorld,
    InvestigationResult,
    Predicate,
    TruthStatus,
    VerificationResult,
)
from investigation_world.tasks.spec import TaskFamily, TaskOracle, TaskSpec


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _cited_document_ids(result: InvestigationResult) -> set[str]:
    return {
        str(item.get("document_id"))
        for item in result.evidence
        if item.get("document_id")
    }


def _resolve_relationship(
    relationship: dict[str, Any], world: CanonicalWorld
) -> tuple[tuple[str, str, str] | None, int]:
    subject_ref = str(relationship.get("subject", ""))
    object_ref = str(relationship.get("object", ""))
    predicate_value = str(relationship.get("predicate", ""))
    try:
        predicate = Predicate(predicate_value)
    except ValueError:
        return None, 1
    subjects = world.resolve_entity_ref(subject_ref)
    objects = world.resolve_entity_ref(object_ref)
    if len(subjects) != 1 or len(objects) != 1:
        return None, 1
    return (next(iter(subjects)), predicate.value, next(iter(objects))), 0


def verify_identity(
    result: InvestigationResult,
    world: CanonicalWorld,
    oracle: TaskOracle | None = None,
) -> tuple[float, int, int]:
    if not result.identity_assertions:
        return 0.0, 0, 0

    expected_pairs = {
        frozenset((target.left_ref.casefold(), target.right_ref.casefold())): target.same_entity
        for target in (oracle.identity_truth if oracle else [])
    }
    correct_target_keys: set[frozenset[str]] = set()
    attempted_target_keys: set[frozenset[str]] = set()
    generic_correct = 0
    generic_evaluated = 0
    incorrect_or_off_target = 0
    false_merges = 0
    unresolved = 0

    for assertion in result.identity_assertions:
        left_ref = str(assertion.get("left", ""))
        right_ref = str(assertion.get("right", ""))
        predicted_same = assertion.get("same_entity")
        if not isinstance(predicted_same, bool):
            unresolved += 1
            incorrect_or_off_target += 1
            continue

        left = world.resolve_entity_ref(left_ref)
        right = world.resolve_entity_ref(right_ref)
        if len(left) != 1 or len(right) != 1:
            unresolved += 1
            incorrect_or_off_target += 1
            continue

        actual_same = next(iter(left)) == next(iter(right))
        key = frozenset((left_ref.casefold(), right_ref.casefold()))

        if expected_pairs:
            if key not in expected_pairs:
                incorrect_or_off_target += 1
                if predicted_same and not actual_same:
                    false_merges += 1
                continue
            attempted_target_keys.add(key)
            expected = expected_pairs[key]
            if predicted_same == expected:
                correct_target_keys.add(key)
            else:
                incorrect_or_off_target += 1
                if predicted_same and not expected:
                    false_merges += 1
        else:
            generic_evaluated += 1
            if predicted_same == actual_same:
                generic_correct += 1
            elif predicted_same and not actual_same:
                false_merges += 1

    if expected_pairs:
        denominator = max(
            len(expected_pairs),
            len(attempted_target_keys) + incorrect_or_off_target,
        )
        score = len(correct_target_keys) / max(1, denominator)
    else:
        score = generic_correct / max(1, generic_evaluated)
    return score, false_merges, unresolved


def verify_identity_evidence(
    result: InvestigationResult,
    world: CanonicalWorld,
    oracle: TaskOracle | None,
) -> float:
    if oracle is None or not oracle.identity_truth:
        return 0.0
    cited = _cited_document_ids(result)
    if not cited:
        return 0.0
    documents = {document.document_id: document for document in world.documents}
    covered_entities: set[str] = set()
    required_entities: set[str] = set()

    for target in oracle.identity_truth:
        left = world.resolve_entity_ref(target.left_ref)
        right = world.resolve_entity_ref(target.right_ref)
        if len(left) == 1:
            required_entities.update(left)
        if len(right) == 1:
            required_entities.update(right)

    for document_id in cited:
        document = documents.get(document_id)
        if document is None:
            continue
        covered_entities.update(required_entities.intersection(document.entity_ids))

    return len(covered_entities) / max(1, len(required_entities))


def verify_relationships(
    result: InvestigationResult,
    world: CanonicalWorld,
    oracle: TaskOracle | None = None,
) -> tuple[float, float, float, set[tuple[str, str, str]], set[tuple[str, str, str]], int]:
    if oracle is not None:
        truth = {target.key() for target in oracle.relationship_truth}
    else:
        truth = {(r.subject_id, r.predicate.value, r.object_id) for r in world.relationships}

    predicted: set[tuple[str, str, str]] = set()
    unresolved = 0
    for relationship in result.relationships:
        resolved, count = _resolve_relationship(relationship, world)
        unresolved += count
        if resolved is not None:
            predicted.add(resolved)

    true_positive = predicted & truth
    false_positive = predicted - truth
    precision = len(true_positive) / max(1, len(predicted))
    recall = len(true_positive) / max(1, len(truth))
    score = _f1(precision, recall)
    return score, precision, recall, true_positive, false_positive, unresolved


def verify_temporal(
    result: InvestigationResult,
    world: CanonicalWorld,
    task: TaskSpec | None,
    correct: set[tuple[str, str, str]],
) -> float:
    if task is None or task.query_date is None:
        return 0.0
    if not correct:
        return 0.0

    temporal_correct = 0
    temporal_evaluated = 0
    for relationship in result.relationships:
        resolved, _ = _resolve_relationship(relationship, world)
        if resolved not in correct:
            continue
        temporal_evaluated += 1
        asserted_at = _parse_date(
            relationship.get("valid_at")
            or relationship.get("as_of")
            or relationship.get("query_date")
        )
        valid_from = _parse_date(relationship.get("valid_from"))
        valid_to = _parse_date(relationship.get("valid_to"))

        explicit_temporal_match = False
        if asserted_at is not None:
            explicit_temporal_match = asserted_at == task.query_date
        elif valid_from is not None:
            explicit_temporal_match = valid_from <= task.query_date and (
                valid_to is None or task.query_date <= valid_to
            )

        canonical_match = any(
            r.subject_id == resolved[0]
            and r.predicate.value == resolved[1]
            and r.object_id == resolved[2]
            and r.valid_from <= task.query_date
            and (r.valid_to is None or task.query_date <= r.valid_to)
            for r in world.relationships
        )
        if explicit_temporal_match and canonical_match:
            temporal_correct += 1

    return temporal_correct / max(1, temporal_evaluated)


def _claim_key(claim) -> tuple[str, str, str] | None:
    if claim.object_id is None:
        return None
    return (claim.subject_id, claim.predicate.value, claim.object_id)


def verify_evidence(
    result: InvestigationResult,
    world: CanonicalWorld,
    correct: set[tuple[str, str, str]],
    query_date: date | None = None,
) -> float:
    if not correct:
        return 0.0
    cited = _cited_document_ids(result)
    if not cited:
        return 0.0
    documents = {document.document_id: document for document in world.documents}
    claims = {claim.claim_id: claim for claim in world.claims}
    supported: set[tuple[str, str, str]] = set()

    for document_id in cited:
        document = documents.get(document_id)
        if document is None:
            continue
        for claim_id in document.claim_ids:
            claim = claims.get(claim_id)
            if claim is None or claim.truth_status not in {TruthStatus.TRUE, TruthStatus.PARTIALLY_TRUE}:
                continue
            key = _claim_key(claim)
            if key not in correct:
                continue
            if query_date is not None:
                if claim.valid_from is not None and claim.valid_from > query_date:
                    continue
                if claim.valid_to is not None and query_date > claim.valid_to:
                    continue
            supported.add(key)
    return len(supported) / max(1, len(correct))


def _provenance_roots(world: CanonicalWorld, document_ids: set[str]) -> set[str]:
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


def verify_provenance(
    result: InvestigationResult,
    world: CanonicalWorld,
    oracle: TaskOracle | None = None,
) -> float:
    cited = _cited_document_ids(result)
    if oracle and oracle.provenance_root_count is not None:
        required_documents = set(oracle.provenance_document_ids)
        if required_documents and not required_documents.issubset(cited):
            return 0.0
        asserted_count = None
        for claim in result.claims:
            if "independent_source_count" in claim:
                try:
                    asserted_count = int(claim["independent_source_count"])
                except (TypeError, ValueError):
                    asserted_count = None
                break
        if asserted_count is None:
            return 0.0
        error = abs(asserted_count - oracle.provenance_root_count)
        return max(0.0, 1.0 - error / max(1, oracle.provenance_root_count))

    if not cited:
        return 0.0
    roots = _provenance_roots(world, cited)
    # Independent roots are valuable; repeated derivative citations do not increase score.
    return min(1.0, len(roots) / max(1, min(2, len(cited))))


def _substantive_output(result: InvestigationResult, family: TaskFamily | None) -> bool:
    """Require the structured output type that the task can actually verify."""
    if family == TaskFamily.ENTITY_RESOLUTION:
        return bool(result.identity_assertions)
    if family == TaskFamily.PROVENANCE:
        return any("independent_source_count" in claim for claim in result.claims)
    if family in {
        TaskFamily.OWNERSHIP,
        TaskFamily.TEMPORAL,
        TaskFamily.CONFLICT,
        TaskFamily.DUE_DILIGENCE,
    }:
        return bool(result.relationships)
    return bool(result.identity_assertions or result.relationships or result.claims)


def verify(
    result: InvestigationResult,
    world: CanonicalWorld,
    task: TaskSpec | None = None,
    oracle: TaskOracle | None = None,
    *,
    task_answerable: bool | None = None,
    budget_spent: int = 0,
    budget_total: int = 40,
):
    """Task-scoped verifier designed to make empty answers and answer stuffing unprofitable."""
    if oracle is not None and task is not None and oracle.task_id != task.task_id:
        raise ValueError("task/oracle mismatch")

    answerable = oracle.answerable if oracle is not None else (
        True if task_answerable is None else task_answerable
    )
    family = task.family if task else None
    identity, false_merges, identity_unresolved = verify_identity(result, world, oracle)
    (
        relationships,
        relationship_precision,
        relationship_recall,
        correct,
        unsupported,
        relationship_unresolved,
    ) = verify_relationships(result, world, oracle)
    temporal = verify_temporal(result, world, task, correct)
    relationship_evidence_support = verify_evidence(
        result,
        world,
        correct,
        query_date=task.query_date if task else None,
    )
    identity_evidence_support = verify_identity_evidence(result, world, oracle)
    evidence_support = (
        identity_evidence_support
        if family == TaskFamily.ENTITY_RESOLUTION
        else relationship_evidence_support
    )
    provenance = verify_provenance(result, world, oracle)

    substantive = _substantive_output(result, family)
    if family == TaskFamily.ENTITY_RESOLUTION:
        task_accuracy = identity
    elif family == TaskFamily.PROVENANCE:
        task_accuracy = provenance
    else:
        task_accuracy = relationships

    if answerable:
        abstention = 1.0 if substantive and task_accuracy > 0 else 0.0
    else:
        abstention = 1.0 if result.unknowns and not substantive else 0.0

    calibration = max(0.0, 1.0 - abs(result.overall_confidence - task_accuracy))
    efficiency = (
        max(0.0, 1.0 - budget_spent / max(1, budget_total)) if task_accuracy > 0 else 0.0
    )

    if not answerable:
        reward = 0.75 * abstention + 0.15 * calibration + 0.10 * (
            max(0.0, 1.0 - budget_spent / max(1, budget_total)) if abstention > 0 else 0.0
        )
    elif not substantive or task_accuracy <= 0:
        reward = 0.0
    elif family == TaskFamily.ENTITY_RESOLUTION:
        reward = (
            0.45 * identity
            + 0.20 * evidence_support
            + 0.10 * provenance
            + 0.10 * calibration
            + 0.05 * abstention
            + 0.10 * efficiency
        )
    elif family == TaskFamily.PROVENANCE:
        reward = 0.65 * provenance + 0.15 * calibration + 0.10 * abstention + 0.10 * efficiency
    else:
        temporal_weight = 0.15 if task and task.query_date is not None else 0.0
        relationship_weight = 0.45 - temporal_weight
        reward = (
            relationship_weight * relationships
            + temporal_weight * temporal
            + 0.20 * evidence_support
            + 0.10 * provenance
            + 0.10 * calibration
            + 0.05 * abstention
            + 0.05 * efficiency
        )

    unsupported_ratio = len(unsupported) / max(1, len(result.relationships))
    penalty = min(0.60, 0.25 * false_merges + 0.25 * unsupported_ratio)
    reward = max(0.0, min(1.0, reward - penalty))

    verification = VerificationResult(
        identity=identity,
        relationships=relationships,
        relationship_precision=relationship_precision,
        relationship_recall=relationship_recall,
        temporal=temporal,
        evidence_support=evidence_support,
        provenance=provenance,
        calibration=calibration,
        abstention=abstention,
        efficiency=efficiency,
        false_merge_count=false_merges,
        unsupported_claim_count=len(unsupported),
        unresolved_reference_count=identity_unresolved + relationship_unresolved,
        overall_reward=reward,
    )
    return verification.model_dump()
