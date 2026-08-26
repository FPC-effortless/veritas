from __future__ import annotations

import copy
import random
from typing import Any, Iterable

from investigation_world.foundry.models import MutationKind, MutationLineage, stable_hash


_PRIVATE_KEYS = {
    "oracle", "ground_truth", "hidden_ground_truth", "true_value", "expected_value",
    "supporting_record_ids", "private_truth", "answer_class", "expected_resolution",
}


def _assert_public(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in _PRIVATE_KEYS:
                raise ValueError(f"private field present in public payload: {key}")
            _assert_public(child)
    elif isinstance(value, list):
        for child in value:
            _assert_public(child)


def apply_mutation(
    public_payload: dict[str, Any],
    *,
    task_id: str,
    kind: MutationKind,
    seed: int,
    parameters: dict[str, Any] | None = None,
    protected_record_ids: Iterable[str] = (),
) -> tuple[dict[str, Any], MutationLineage]:
    _assert_public(public_payload)
    payload = copy.deepcopy(public_payload)
    params = dict(parameters or {})
    rng = random.Random(seed)
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    protected = set(protected_record_ids)

    if kind == MutationKind.REORDER_RECORDS:
        rng.shuffle(records)
    elif kind == MutationKind.INJECT_DISTRACTOR:
        distractor_id = f"FOUNDRY-DISTRACTOR-{stable_hash([task_id, seed])[:12].upper()}"
        records.append({
            "record_id": distractor_id,
            "system": params.get("system", "PUBLIC"),
            "record_type": "foundry_distractor",
            "object_type": "DISTRACTOR",
            "object_id": distractor_id,
            "fields": {"note": params.get("note", "Unrelated operational record.")},
            "source_file": "foundry/generated",
            "related_object_ids": [],
        })
    elif kind == MutationKind.REDACT_OPTIONAL_FIELD:
        candidates = []
        for record in records:
            if not isinstance(record, dict) or record.get("record_id") in protected:
                continue
            fields = record.get("fields")
            if isinstance(fields, dict):
                for field_name in fields:
                    candidates.append((record, field_name))
        if candidates:
            record, field_name = rng.choice(candidates)
            record["fields"].pop(field_name, None)
            params["redacted_field"] = field_name
            params["redacted_record_id"] = record.get("record_id")
    elif kind == MutationKind.TIGHTEN_BUDGET:
        task = payload.setdefault("task", {})
        constraints = task.setdefault("constraints", {})
        factor = float(params.get("factor", 0.75))
        current = float(constraints.get("budget", params.get("base_budget", 100.0)))
        constraints["budget"] = max(1.0, current * factor)
    elif kind == MutationKind.TOOL_FAILURE:
        task = payload.setdefault("task", {})
        constraints = task.setdefault("constraints", {})
        failures = constraints.setdefault("foundry_tool_failures", [])
        failures.append({"system": params.get("system", "UNKNOWN"), "at_step": int(params.get("at_step", 0))})
    elif kind == MutationKind.PERMISSION_CHANGE:
        task = payload.setdefault("task", {})
        constraints = task.setdefault("constraints", {})
        constraints["foundry_permission_change"] = params
    else:
        raise ValueError(kind)

    mutation_id = f"MUT-{stable_hash([task_id, kind.value, seed, params])[:16].upper()}"
    lineage = MutationLineage(
        mutation_id=mutation_id,
        kind=kind,
        parent_task_id=task_id,
        seed=seed,
        parameters=params,
    )
    _assert_public(payload)
    return payload, lineage
