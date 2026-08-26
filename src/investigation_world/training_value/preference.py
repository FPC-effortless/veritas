from __future__ import annotations

import copy
import json
from typing import Any

from investigation_world.calibration.full_context import _claims
from investigation_world.companyworld.verifier import verify_companyworld
from investigation_world.training_value.diagnostic_sft import build_diagnostic_examples


def _candidate_payloads(chosen: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    claims = chosen.get("claims") if isinstance(chosen.get("claims"), list) else []

    wrong_delay = copy.deepcopy(chosen)
    for claim in wrong_delay.get("claims", []):
        if claim.get("field_name") == "fulfillment_delay_days":
            try:
                claim["value"] = float(claim.get("value", 0.0)) + 1.0
            except (TypeError, ValueError):
                claim["value"] = 1.0
    candidates.append(wrong_delay)

    wrong_status = copy.deepcopy(chosen)
    for claim in wrong_status.get("claims", []):
        if claim.get("field_name") == "ship_commitment_status":
            claim["value"] = "ON_TIME" if str(claim.get("value")) != "ON_TIME" else "LATE"
    candidates.append(wrong_status)

    wrong_both = copy.deepcopy(wrong_delay)
    for claim in wrong_both.get("claims", []):
        if claim.get("field_name") == "ship_commitment_status":
            claim["value"] = "ON_TIME" if str(claim.get("value")) != "ON_TIME" else "LATE"
    candidates.append(wrong_both)

    unsupported = copy.deepcopy(chosen)
    unsupported["evidence_record_ids"] = []
    candidates.append(unsupported)

    # Keep only candidates that actually differ from the chosen payload.
    chosen_text = json.dumps(chosen, sort_keys=True)
    return [item for item in candidates if json.dumps(item, sort_keys=True) != chosen_text]


def _score_payload(payload: dict[str, Any], episode) -> float:
    result = _claims(payload, episode.task.model_dump(mode="json"))
    return verify_companyworld(result, episode).overall_reward


def build_verifier_ranked_preferences(
    *,
    count: int = 24,
    start_index: int = 100,
    world_id: str = "CW-TRAINING-PREFERENCE",
) -> list[dict[str, Any]]:
    rows = build_diagnostic_examples(count=count, start_index=start_index, world_id=world_id)
    preferences: list[dict[str, Any]] = []
    for row in rows:
        episode = row["episode"]
        chosen_payload = json.loads(str(row["target"]))
        chosen_reward = _score_payload(chosen_payload, episode)
        ranked = sorted(
            ((_score_payload(candidate, episode), candidate) for candidate in _candidate_payloads(chosen_payload)),
            key=lambda item: item[0],
        )
        if not ranked:
            continue
        rejected_reward, rejected_payload = ranked[0]
        if chosen_reward <= rejected_reward:
            continue
        preferences.append(
            {
                "episode": episode,
                "prompt": row["prompt"],
                "chosen": json.dumps(chosen_payload, sort_keys=True),
                "rejected": json.dumps(rejected_payload, sort_keys=True),
                "chosen_reward": round(chosen_reward, 6),
                "rejected_reward": round(rejected_reward, 6),
                "reward_margin": round(chosen_reward - rejected_reward, 6),
            }
        )
    return preferences
