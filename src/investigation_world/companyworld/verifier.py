from __future__ import annotations

import math
from typing import Any

from investigation_world.companyworld.models import (
    CompanyWorldEpisode,
    CompanyWorldVerificationResult,
    OperationalFactTarget,
)
from investigation_world.core.models import InvestigationResult


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        lowered = stripped.casefold()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            return float(stripped)
        except ValueError:
            return lowered
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return value


def _equal(left: Any, right: Any) -> bool:
    a = _normalize(left)
    b = _normalize(right)
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)
    return a == b


def _claim_key(claim: dict[str, Any]) -> tuple[str, str, str] | None:
    object_type = claim.get("object_type")
    object_id = claim.get("object_id")
    field_name = claim.get("field_name")
    if not object_type or not object_id or not field_name:
        return None
    return (str(object_type), str(object_id), str(field_name))


def _cited_record_ids(result: InvestigationResult) -> set[str]:
    cited: set[str] = set()
    for item in result.evidence:
        record_id = item.get("record_id") or item.get("document_id")
        if record_id:
            cited.add(str(record_id))
    return cited


def _fact_map(facts: list[OperationalFactTarget]) -> dict[tuple[str, str, str], OperationalFactTarget]:
    return {fact.key(): fact for fact in facts}


def verify_companyworld(
    result: InvestigationResult,
    episode: CompanyWorldEpisode,
    *,
    budget_spent: int = 0,
    budget_total: int = 40,
) -> CompanyWorldVerificationResult:
    """Score an operational investigation against CompanyWorld evaluator truth.

    Agent claims use the existing InvestigationResult.claims surface with dictionaries shaped as:
    {object_type, object_id, field_name, value}. Evidence entries cite record_id (document_id is
    accepted as a compatibility alias).
    """

    oracle = episode.oracle
    truth = _fact_map(oracle.facts)
    predicted: dict[tuple[str, str, str], Any] = {}
    unresolved = 0
    for claim in result.claims:
        key = _claim_key(claim)
        if key is None or "value" not in claim:
            unresolved += 1
            continue
        predicted[key] = claim.get("value")

    correct: set[tuple[str, str, str]] = set()
    incorrect: set[tuple[str, str, str]] = set()
    for key, value in predicted.items():
        target = truth.get(key)
        if target is not None and _equal(value, target.expected_value):
            correct.add(key)
        else:
            incorrect.add(key)

    precision = len(correct) / max(1, len(predicted))
    recall = len(correct) / max(1, len(truth))
    fact_score = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)

    cited = _cited_record_ids(result)
    supported = 0
    for key in correct:
        required = set(truth[key].supporting_record_ids)
        if required and cited.intersection(required):
            supported += 1
    evidence_support = supported / max(1, len(correct)) if correct else 0.0

    substantive = bool(predicted)
    if oracle.answerable:
        abstention = 1.0 if substantive and fact_score > 0 else 0.0
    else:
        abstention = 1.0 if result.unknowns and not substantive else 0.0

    calibration = max(0.0, 1.0 - abs(result.overall_confidence - fact_score))
    efficiency = (
        max(0.0, 1.0 - budget_spent / max(1, budget_total))
        if fact_score > 0
        else 0.0
    )

    if not oracle.answerable:
        reward = 0.75 * abstention + 0.15 * calibration + 0.10 * (
            max(0.0, 1.0 - budget_spent / max(1, budget_total)) if abstention else 0.0
        )
    elif not substantive or fact_score <= 0:
        reward = 0.0
    else:
        reward = (
            0.60 * fact_score
            + 0.20 * evidence_support
            + 0.10 * calibration
            + 0.05 * abstention
            + 0.05 * efficiency
        )
        false_ratio = len(incorrect) / max(1, len(predicted))
        reward -= min(0.35, 0.25 * false_ratio)
        reward = max(0.0, min(1.0, reward))

    return CompanyWorldVerificationResult(
        fact_score=fact_score,
        fact_precision=precision,
        fact_recall=recall,
        evidence_support=evidence_support,
        calibration=calibration,
        abstention=abstention,
        efficiency=efficiency,
        false_fact_count=len(incorrect),
        unresolved_fact_count=unresolved,
        overall_reward=reward,
    )
