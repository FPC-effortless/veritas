from __future__ import annotations

from copy import deepcopy
from statistics import mean
from typing import Any, Callable

from investigation_world.benchmark.policies import PublicEvidenceReferencePolicy
from investigation_world.calibration.fixtures import diagnostic_fixture
from investigation_world.calibration.full_context import _claims, _json_object, _prompt
from investigation_world.companyworld.verifier import verify_companyworld

GenerateFn = Callable[[str], str]


_CONFLICT_FIELDS: dict[str, tuple[str, Any]] = {
    "INVESTIGATE_MISSING_SHIPMENT": ("delivered_quantity", 0),
    "INVESTIGATE_DUPLICATE_INVOICE": ("duplicate_status", "NOT_DUPLICATE"),
    "INVESTIGATE_AUTHORITY_BREACH": ("approval_limit_usd", 10_000_000),
    "O2C_FULFILLMENT_TIMING": ("ship_commitment_status", "ON_TIME"),
    "P2P_RECONCILIATION": ("reconciliation_status", "MATCH"),
}


def perturb_public_payload(
    public_payload: dict[str, Any],
    *,
    distractor_count: int = 6,
    include_conflicting_projection: bool = True,
) -> dict[str, Any]:
    """Add public-only distractors and a non-authoritative conflicting system projection.

    The perturbation never reads verifier/oracle state. It is designed to preserve
    answerability while making evidence selection harder.
    """
    payload = deepcopy(public_payload)
    records = list(payload.get("records", []))
    task = dict(payload.get("task", {}))
    episode_id = str(payload.get("episode_id", "CW"))

    for index in range(max(0, distractor_count)):
        records.append(
            {
                "record_id": f"ABL-{episode_id}-DIST-{index:02d}",
                "system": "EMAIL" if index % 2 == 0 else "PROCESS",
                "record_type": "irrelevant_operational_context",
                "object_type": "UNRELATED_CASE",
                "object_id": f"UNRELATED-{index:02d}",
                "fields": {
                    "status": "OPEN" if index % 2 == 0 else "CLOSED",
                    "priority": (index % 3) + 1,
                    "amount_usd": 1000 + index * 137,
                },
                "source_file": "ablation/generated_distractor.json",
                "observed_at": None,
                "related_object_ids": [],
            }
        )

    task_type = str(task.get("task_type", ""))
    target_id = str(task.get("target_object_id", ""))
    target_type = str(task.get("target_object_type", ""))
    conflict = _CONFLICT_FIELDS.get(task_type)
    if include_conflicting_projection and conflict is not None:
        field_name, wrong_value = conflict
        records.append(
            {
                "record_id": f"ABL-{episode_id}-CONFLICT",
                "system": "ERP",
                "record_type": "system_projection",
                "object_type": target_type,
                "object_id": target_id,
                "fields": {field_name: wrong_value},
                "source_file": "ablation/conflicting_projection.json",
                "observed_at": None,
                "related_object_ids": [],
            }
        )

    payload["records"] = records
    metadata = dict(payload.get("metadata", {}))
    metadata["ablation"] = {
        "kind": "noise_and_conflicting_projection",
        "distractor_count": max(0, distractor_count),
        "conflicting_projection": bool(include_conflicting_projection and conflict is not None),
    }
    payload["metadata"] = metadata
    return payload


def _score_payload(generate: GenerateFn, episode, payload: dict[str, Any]) -> tuple[float, bool]:
    raw = generate(_prompt("diagnostic", payload))
    parsed = _json_object(raw)
    result = _claims(parsed, episode.task.model_dump(mode="json"))
    return verify_companyworld(result, episode).overall_reward, bool(parsed)


def run_diagnostic_noise_ablation(
    generate: GenerateFn,
    *,
    model_name: str,
    distractor_count: int = 6,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    clean_scores: list[float] = []
    perturbed_scores: list[float] = []
    reference_scores: list[float] = []
    clean_parse_failures = 0
    perturbed_parse_failures = 0

    reference = PublicEvidenceReferencePolicy()
    for episode in diagnostic_fixture():
        clean_payload = episode.public_payload()
        perturbed_payload = perturb_public_payload(
            clean_payload,
            distractor_count=distractor_count,
            include_conflicting_projection=True,
        )

        clean_score, clean_parsed = _score_payload(generate, episode, clean_payload)
        perturbed_score, perturbed_parsed = _score_payload(generate, episode, perturbed_payload)
        reference_score = verify_companyworld(reference(perturbed_payload), episode).overall_reward

        clean_scores.append(clean_score)
        perturbed_scores.append(perturbed_score)
        reference_scores.append(reference_score)
        clean_parse_failures += int(not clean_parsed)
        perturbed_parse_failures += int(not perturbed_parsed)
        rows.append(
            {
                "episode_id": episode.episode_id,
                "clean_score": round(clean_score, 6),
                "perturbed_score": round(perturbed_score, 6),
                "delta": round(perturbed_score - clean_score, 6),
                "reference_score_on_perturbed": round(reference_score, 6),
                "clean_parsed": clean_parsed,
                "perturbed_parsed": perturbed_parsed,
            }
        )

    clean_mean = mean(clean_scores) if clean_scores else 0.0
    perturbed_mean = mean(perturbed_scores) if perturbed_scores else 0.0
    return {
        "schema_version": "0.1.0",
        "experiment": "diagnostic_noise_conflict_ablation",
        "model": model_name,
        "episodes": len(rows),
        "distractor_count": distractor_count,
        "clean_mean": round(clean_mean, 6),
        "perturbed_mean": round(perturbed_mean, 6),
        "absolute_delta": round(perturbed_mean - clean_mean, 6),
        "clean_parse_failures": clean_parse_failures,
        "perturbed_parse_failures": perturbed_parse_failures,
        "public_reference_perturbed_mean": round(mean(reference_scores), 6) if reference_scores else 0.0,
        "public_reference_preserved": bool(reference_scores and min(reference_scores) >= 1.0 - 1e-12),
        "episodes_detail": rows,
    }
