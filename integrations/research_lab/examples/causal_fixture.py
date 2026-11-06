"""Constructed keyed-state intervention; no fitted model or qualification claim.

TrainLab owns process timing/runtime/input hashes. This fixture writes deterministic
paired predictions so another worker can reproduce the actual diagnostic bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

STRATA = ("read", "correction", "deletion", "absent")
ARMS = ("carry", "reset", "state_swap", "no_overwrite", "always_unknown")
N_HISTORIES = 2048
N_KEYS = 16
N_VALUES = 4


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def generate(seed):
    """Vary QUERY position independently by sampling total length before events."""
    rng = random.Random(seed)
    histories = []
    for index in range(N_HISTORIES):
        category = STRATA[index % len(STRATA)]
        query = rng.randrange(N_KEYS)
        length = rng.randrange(6, 17)
        unrelated = [key for key in range(N_KEYS) if key != query]
        events = []
        for _ in range(length):
            key = rng.choice(unrelated)
            events.append(
                ["WRITE", key, rng.randrange(N_VALUES)]
                if rng.randrange(4)
                else ["DELETE", key, None]
            )
        # Every swap donor contains a genuine populated state, even if later
        # random distractors delete all other unrelated keys.
        sentinel = unrelated[-1]
        events[-1] = ["WRITE", sentinel, rng.randrange(N_VALUES)]
        first_value = rng.randrange(N_VALUES)
        if category == "read":
            slot = rng.randrange(length - 1)
            events[slot] = ["WRITE", query, first_value]
        elif category in ("correction", "deletion"):
            first, second = sorted(rng.sample(range(length - 1), 2))
            events[first] = ["WRITE", query, first_value]
            events[second] = (
                ["WRITE", query, (first_value + rng.randrange(1, N_VALUES)) % N_VALUES]
                if category == "correction"
                else ["DELETE", query, None]
            )
        histories.append({"id": index, "category": category, "events": events, "query": query})
    rng.shuffle(histories)
    return histories


def reference(history):
    """Independent reverse last-event lookup; deliberately uses no keyed store."""
    relevant = [event for event in history["events"] if event[1] == history["query"]]
    category = history["category"]
    if category == "read":
        valid = len(relevant) == 1 and relevant[0][0] == "WRITE"
    elif category == "correction":
        valid = (
            len(relevant) == 2
            and [event[0] for event in relevant] == ["WRITE", "WRITE"]
            and relevant[0][2] != relevant[1][2]
        )
    elif category == "deletion":
        valid = len(relevant) == 2 and [event[0] for event in relevant] == ["WRITE", "DELETE"]
    else:
        valid = category == "absent" and not relevant
    if not valid:
        raise RuntimeError("independent lifecycle-category audit failed")
    for operation, key, value in reversed(history["events"]):
        if key == history["query"]:
            return value if operation == "WRITE" else None
    return None


def execute(events, *, overwrite=True):
    state = {}
    for operation, key, value in events:
        if operation == "DELETE":
            state.pop(key, None)
        elif operation == "WRITE":
            if overwrite or key not in state:
                state[key] = value
        else:
            raise RuntimeError("unsupported operation")
    return state


def evaluate(seed):
    histories = generate(seed)
    targets = [reference(history) for history in histories]
    states = [execute(history["events"]) for history in histories]
    if not all(states):
        raise RuntimeError("swap donors must have populated states")
    rows = []
    counters = {arm: Counter() for arm in ARMS}
    counts = Counter(history["category"] for history in histories)
    if dict(counts) != dict.fromkeys(STRATA, N_HISTORIES // len(STRATA)):
        raise RuntimeError("unbalanced lifecycle strata")
    for index, (history, target) in enumerate(zip(histories, targets)):
        query = history["query"]
        reset_state = dict(states[index])
        reset_state.clear()  # Only the observation/query boundary is intervened on.
        donor = (index + 1) % N_HISTORIES
        outputs = {
            "carry": states[index].get(query),
            "reset": reset_state.get(query),
            "state_swap": states[donor].get(query),
            "no_overwrite": execute(history["events"], overwrite=False).get(query),
            "always_unknown": None,
        }
        if outputs["carry"] != target:
            raise RuntimeError("reference mismatch: fixture or adapter is invalid")
        present = "value_present" if target is not None else "unknown_target"
        for arm, prediction in outputs.items():
            correct = int(prediction == target)
            counters[arm][history["category"]] += correct
            counters[arm][present] += correct
        rows.append(
            {
                **history,
                "target": target,
                "outputs": outputs,
                "swap_donor_id": histories[donor]["id"],
            }
        )
    denominators = {**counts, "value_present": sum(v is not None for v in targets)}
    denominators["unknown_target"] = N_HISTORIES - denominators["value_present"]
    scores = {}
    for arm in ARMS:
        by_category = {name: counters[arm][name] / count for name, count in denominators.items()}
        scores[arm] = {
            "macro_lifecycle_accuracy": sum(by_category[name] for name in STRATA) / len(STRATA),
            "accuracy": sum(counters[arm][name] for name in STRATA) / N_HISTORIES,
            "by_category": by_category,
            "errors_by_category": {
                name: count - counters[arm][name] for name, count in denominators.items()
            },
        }
    if any(scores["carry"]["by_category"][name] != 1 for name in STRATA):
        raise RuntimeError("reference must be perfect separately in every lifecycle stratum")
    effect = (
        scores["carry"]["macro_lifecycle_accuracy"] - scores["reset"]["macro_lifecycle_accuracy"]
    )
    diagnostics = {
        "schema": "research_lab.causal_diagnostic.v1",
        "source_kind": "CONSTRUCTED",
        "scientific_qualification": "NOT_QUALIFIED",
        "fitted_models": 0,
        "seed": seed,
        "histories": N_HISTORIES,
        "category_counts": dict(denominators),
        "operations_observed": sum(len(history["events"]) for history in histories),
        "arms": scores,
        "carry_minus_reset": effect,
        "minimum_effect": 0.20,
        "hypothesis_threshold_met": effect >= 0.20,
        "history_sha256": hashlib.sha256(canonical(histories).encode()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "timing_and_runtime_source": "TrainLab run.json; no production latency claim",
        "limitations": [
            "Deterministic exact keyed-store diagnostic; "
            "no training or learned-architecture ranking.",
            "Reset removes the only value channel; "
            "this is causal state-use evidence within the fixture.",
            "Generator seeds are not independent dataset-distribution replications.",
        ],
    }
    return {"schema": "research_lab.paired_predictions.v1", "seed": seed, "rows": rows}, diagnostics


def main():
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] not in ("candidate", "control")):
        raise SystemExit("usage: causal_fixture.py [candidate|control]")
    selected = "reset" if len(sys.argv) == 2 and sys.argv[1] == "control" else "carry"
    seed = int(os.environ["TRAINLAB_SEED"])
    if not 0 <= seed <= 2**32 - 1:
        raise ValueError("TRAINLAB_SEED must be an unsigned 32-bit integer")
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    output.mkdir(parents=True, exist_ok=True)
    predictions, diagnostics = evaluate(seed)
    documents = {
        "metrics.json": {"score": diagnostics["arms"][selected]["macro_lifecycle_accuracy"]},
        "predictions.json": predictions,
        "diagnostics.json": diagnostics,
    }
    for name, document in documents.items():
        (output / name).write_text(canonical(document) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
