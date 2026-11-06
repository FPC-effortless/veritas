"""ENGINEERING_ONLY lifecycle harness; no neural training or architecture ranking.

Run with ``candidate`` (exact carried store) or ``control`` (reset before query).
The forward implementation sees only visible events. A reverse-scan reference
and independently retained generator invariants score its answers after execution.
All operations and symbols are public constructed fixtures, not protected TEST.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from collections import defaultdict
from pathlib import Path

UNKNOWN = 4
CATEGORIES = ("present", "corrected", "deleted", "absent")
DELAYS = (0, 8, 24)
MUTATIONS = (0, 2, 4)
MODES = ("carry", "reset", "no_overwrite", "no_delete", "read_permuted")
BOOTSTRAP_RESAMPLES = 400


def predict(events, mode="carry"):
    """The implementation receives event tuples only, never scoring metadata."""
    if mode not in MODES:
        raise ValueError("unsupported implementation mode")
    memory = {}
    answers = []
    for operation, key, value in events:
        if operation == "WRITE":
            if mode != "no_overwrite" or key not in memory:
                memory[key] = value
        elif operation == "DELETE":
            if mode != "no_delete":
                memory.pop(key, None)
        elif operation == "QUERY":
            if mode == "reset":
                memory.clear()
            read_key = (key + 1) % 8 if mode == "read_permuted" else key
            answers.append(memory.get(read_key, UNKNOWN))
        elif operation != "DISTRACTOR":
            raise ValueError("unsupported visible operation")
    if len(answers) != 1:
        raise ValueError("fixture requires exactly one query")
    return answers[0]


def reference(events):
    """Score by backwards lookup, independently of the implementation's state."""
    query_indices = [i for i, event in enumerate(events) if event[0] == "QUERY"]
    if len(query_indices) != 1:
        raise ValueError("reference requires one query")
    query_index = query_indices[0]
    query_key = events[query_index][1]
    for operation, key, value in reversed(events[:query_index]):
        if key == query_key:
            if operation == "WRITE":
                return value
            if operation == "DELETE":
                return UNKNOWN
    return UNKNOWN


def scorer_self_check():
    """Handwritten answers catch reference, future-lookahead and control errors."""
    fixtures = [
        ([("QUERY", 0, None)], UNKNOWN),
        ([("WRITE", 0, 1), ("QUERY", 0, None)], 1),
        ([("WRITE", 0, 1), ("WRITE", 0, 2), ("QUERY", 0, None)], 2),
        ([("WRITE", 0, 1), ("DELETE", 0, None), ("QUERY", 0, None)], UNKNOWN),
        ([("WRITE", 1, 3), ("QUERY", 0, None)], UNKNOWN),
        ([("WRITE", 0, 1), ("QUERY", 0, None), ("WRITE", 0, 2)], 1),
        ([("DELETE", 0, None), ("WRITE", 0, 3), ("QUERY", 0, None)], 3),
        ([("WRITE", 0, 2), ("DISTRACTOR", 0, 1), ("QUERY", 0, None)], 2),
    ]
    for events, expected in fixtures:
        if reference(events) != expected or predict(events) != expected:
            raise RuntimeError("independent scorer/implementation self-check failed")
    if predict(fixtures[2][0], "no_overwrite") != 1:
        raise RuntimeError("no-overwrite negative control is not effective")
    if predict(fixtures[3][0], "no_delete") != 1:
        raise RuntimeError("no-delete negative control is not effective")


def _distractor(rng):
    return ("DISTRACTOR", rng.randrange(8), rng.randrange(4))


def generate(seed):
    """120 binding families x 4 lifecycle histories x 9 cells x 2 paired arms.

    The four category siblings share bindings, unrelated writes, neutral context
    and query positions. The deletion/absence variants therefore do not count as
    independent data replications of their present/corrected siblings.
    """
    rng = random.Random(seed)
    keys = list(range(8)) * 15
    values = list(range(4)) * 30
    rng.shuffle(keys)
    rng.shuffle(values)
    base_hashes = set()
    for family, (query_key, old_value) in enumerate(zip(keys, values)):
        new_value = (old_value + rng.randrange(1, 4)) % 4
        other_keys = [key for key in range(8) if key != query_key]
        rng.shuffle(other_keys)
        unrelated = [
            ("WRITE", key, rng.randrange(4)) for key in other_keys[: rng.choice((2, 3, 4))]
        ]
        prefix = [_distractor(rng) for _ in range(rng.randrange(6))]
        trailing = [_distractor(rng) for _ in range(rng.randrange(6))]
        # The insertion position varies independently of the visible lifecycle.
        insert_at = rng.randrange(len(unrelated) + 1)
        bases = {}
        for category in CATEGORIES:
            first = (
                ("DISTRACTOR", query_key, old_value)
                if category == "absent"
                else ("WRITE", query_key, old_value)
            )
            initial = unrelated[:insert_at] + [first] + unrelated[insert_at:]
            last = {
                "present": ("DISTRACTOR", query_key, new_value),
                "corrected": ("WRITE", query_key, new_value),
                "deleted": ("DELETE", query_key, None),
                "absent": ("DISTRACTOR", query_key, new_value),
            }[category]
            bases[category] = prefix + initial + [last]
            # Exclude exact duplicates between distinct base histories. Identical
            # m=0 intervention pairs are intentional and retain their pairing.
            base_bytes = json.dumps(bases[category], separators=(",", ":")).encode()
            base_hash = hashlib.sha256(base_bytes).hexdigest()
            if base_hash in base_hashes:
                raise RuntimeError("duplicate base history; panel is invalid")
            base_hashes.add(base_hash)
        for delay in DELAYS:
            for mutation_count in MUTATIONS:
                slots = [
                    ("DISTRACTOR", rng.choice(other_keys), rng.randrange(4)) for _ in range(delay)
                ]
                mutations = []
                neutrals = []
                for _ in range(mutation_count):
                    key = rng.choice(other_keys)
                    operation = rng.choice(("WRITE", "DELETE"))
                    value = rng.randrange(4) if operation == "WRITE" else None
                    mutations.append((operation, key, value))
                    neutrals.append(("DISTRACTOR", key, value))
                order = list(range(delay + mutation_count))
                rng.shuffle(order)
                for category in CATEGORIES:
                    expected = {
                        "present": old_value,
                        "corrected": new_value,
                        "deleted": UNKNOWN,
                        "absent": UNKNOWN,
                    }[category]
                    for arm, edits in (("distractor", neutrals), ("mutation", mutations)):
                        suffix = slots + edits
                        suffix = [suffix[index] for index in order]
                        events = bases[category] + suffix + [("QUERY", query_key, None)] + trailing
                        yield {
                            "id": f"f{family:03d}-{category}-d{delay}-m{mutation_count}-{arm}",
                            "base_id": f"f{family:03d}-{category}",
                            "family": family,
                            "category": category,
                            "delay": delay,
                            "mutation_count": mutation_count,
                            "arm": arm,
                            "events": events,
                            "expected": expected,
                            "stale_value": old_value
                            if category in ("corrected", "deleted")
                            else None,
                            "query_key": query_key,
                        }


def _stats(rows, mode):
    count = len(rows)
    value_rows = [row for row in rows if row["category"] in ("present", "corrected")]
    lifecycle_rows = [row for row in rows if row["category"] in ("corrected", "deleted")]
    return {
        "count": count,
        "accuracy": sum(row["predictions"][mode] == row["expected"] for row in rows) / count,
        "value_query_count": len(value_rows),
        "value_query_accuracy": (
            sum(row["predictions"][mode] == row["expected"] for row in value_rows) / len(value_rows)
            if value_rows
            else None
        ),
        "unknown_answer_rate": sum(row["predictions"][mode] == UNKNOWN for row in rows) / count,
        "stale_answer_rate": (
            sum(row["predictions"][mode] == row["stale_value"] for row in lifecycle_rows)
            / len(lifecycle_rows)
            if lifecycle_rows
            else None
        ),
    }


def _paired_effect(rows, mode, seed):
    pairs = defaultdict(dict)
    for row in rows:
        pairs[(row["family"], row["category"], row["delay"], row["mutation_count"])][row["arm"]] = (
            row
        )
    clusters = defaultdict(list)
    cell_differences = defaultdict(list)
    for (family, category, delay, mutation_count), pair in pairs.items():
        if set(pair) != {"distractor", "mutation"}:
            raise RuntimeError("missing matched intervention arm")
        left, right = pair["mutation"], pair["distractor"]
        if left["length"] != right["length"] or left["query_index"] != right["query_index"]:
            raise RuntimeError("intervention arms differ in length or query position")
        delta = int(left["predictions"][mode] == left["expected"]) - int(
            right["predictions"][mode] == right["expected"]
        )
        clusters[family].append(delta)
        cell_differences[f"{category}/d{delay}/m{mutation_count}"].append(delta)
    cluster_means = [sum(values) / len(values) for _, values in sorted(clusters.items())]
    rng = random.Random(seed ^ 0x524F4255)
    bootstrap = sorted(
        sum(rng.choice(cluster_means) for _ in cluster_means) / len(cluster_means)
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    return {
        "difference": "mutation_accuracy-minus-length-matched-distractor_accuracy",
        "mean": sum(cluster_means) / len(cluster_means),
        "cell_means": {
            key: sum(values) / len(values) for key, values in sorted(cell_differences.items())
        },
        "interval": [bootstrap[9], bootstrap[389]],
        "interval_method": (
            "Descriptive 95% percentile cluster bootstrap: resample the 120 binding families "
            "with replacement 400 times, retain all four lifecycle siblings and nine cells "
            "inside each family, compute the equally weighted family-mean paired effect; "
            "sorted order statistics 10 and 390 (one-based). Fixed RNG seed = data_seed XOR "
            "0x524F4255. One data seed is one synthetic panel; repeated conditions are not "
            "independent samples. No neural-model or distribution-shift certificate."
        ),
        "resamples": BOOTSTRAP_RESAMPLES,
        "clusters": len(cluster_means),
    }


def run(seed, selected_arm):
    if selected_arm not in ("candidate", "control"):
        raise ValueError("select candidate or control")
    scorer_self_check()
    rows = []
    for case in generate(seed):
        events = case["events"]
        expected = reference(events)
        if expected != case["expected"]:
            raise RuntimeError("reference disagrees with independent generator invariant")
        predictions = {mode: predict(events, mode) for mode in MODES}
        # A visible vocabulary relabelling is a semantic invariant. The read-only
        # permutation ablation above instead corrupts addressing inside predict.
        renamed = [(operation, (key + 1) % 8, value) for operation, key, value in events]
        irrelevant_map = {key: key for key in range(8)}
        irrelevant_keys = [key for key in range(8) if key != case["query_key"]]
        for index, key in enumerate(irrelevant_keys):
            irrelevant_map[key] = irrelevant_keys[(index + 1) % len(irrelevant_keys)]
        irrelevant_renamed = [(op, irrelevant_map[key], value) for op, key, value in events]
        predictions["consistent_key_permutation"] = predict(renamed)
        predictions["irrelevant_key_permutation"] = predict(irrelevant_renamed)
        if (
            predictions["carry"] != expected
            or reference(renamed) != expected
            or predictions["consistent_key_permutation"] != expected
            or reference(irrelevant_renamed) != expected
            or predictions["irrelevant_key_permutation"] != expected
        ):
            raise RuntimeError("symbolic carry or key-permutation invariant failed")
        row = {key: value for key, value in case.items() if key not in ("events", "query_key")}
        row.update(
            input_sha256=hashlib.sha256(
                json.dumps(events, separators=(",", ":")).encode()
            ).hexdigest(),
            length=len(events),
            query_index=next(i for i, event in enumerate(events) if event[0] == "QUERY"),
            predictions=predictions,
        )
        rows.append(row)
    if len(rows) != 480 * 3 * 3 * 2 or len({row["base_id"] for row in rows}) != 480:
        raise RuntimeError("incomplete factorial panel")
    all_modes = (*MODES, "consistent_key_permutation", "irrelevant_key_permutation")
    summary = {mode: _stats(rows, mode) for mode in all_modes}
    category_stats = {
        category: {
            mode: _stats([row for row in rows if row["category"] == category], mode)
            for mode in all_modes
        }
        for category in CATEGORIES
    }
    if category_stats["corrected"]["no_overwrite"]["accuracy"] != 0:
        raise RuntimeError("correction panel failed to reject the no-overwrite control")
    if category_stats["deleted"]["no_delete"]["accuracy"] != 0:
        raise RuntimeError("deletion panel failed to reject the no-delete control")
    if summary["read_permuted"]["value_query_accuracy"] >= 1:
        raise RuntimeError("address permutation control was not detected")
    cell_stats = {}
    for category in CATEGORIES:
        for delay in DELAYS:
            for count in MUTATIONS:
                for arm in ("distractor", "mutation"):
                    selected = [
                        row
                        for row in rows
                        if (row["category"], row["delay"], row["mutation_count"], row["arm"])
                        == (category, delay, count, arm)
                    ]
                    cell_stats[f"{category}/d{delay}/m{count}/{arm}"] = {
                        mode: _stats(selected, mode) for mode in all_modes
                    }
    selected_mode = "carry" if selected_arm == "candidate" else "reset"
    diagnostics = {
        "schema": "research_lab.robustness_fixture.v1",
        "scope": "ENGINEERING_ONLY",
        "scientific_qualification": "NOT_QUALIFIED",
        "neural_training": "NOT_PERFORMED",
        "architecture_comparison": "NOT_PERFORMED",
        "seed": seed,
        "selected_arm": selected_arm,
        "selected_implementation": selected_mode,
        "base_histories": 480,
        "binding_families": 120,
        "cases": len(rows),
        "delays": DELAYS,
        "mutation_counts": MUTATIONS,
        "summary": summary,
        "categories": category_stats,
        "cells": cell_stats,
        "paired_mutation_effect": {mode: _paired_effect(rows, mode, seed) for mode in MODES},
        "primary_value_query_gain_over_reset": (
            summary["carry"]["value_query_accuracy"] - summary["reset"]["value_query_accuracy"]
        ),
        "permutation_semantics": {
            "consistent_key_permutation": (
                "Rename every visible key, including query, by key+1 modulo 8."
            ),
            "irrelevant_key_permutation": (
                "Rotate only nonqueried visible keys; leave query key fixed."
            ),
            "read_permuted": (
                "Keep visible inputs and reference unchanged; corrupt only the implementation's "
                "lookup address to key+1 modulo 8. This is an addressing ablation, not a "
                "semantically changed query scored against its old label."
            ),
        },
        "replay": (
            "Regenerate cases from this exact script and TRAINLAB_SEED; "
            "predictions retain input hashes."
        ),
        "limitations": [
            (
                "Exact symbolic stores and deliberately broken controls only; no "
                "learned memory capability."
            ),
            (
                "No fitted parameters, training dataset, model selection, held-out"
                " learned-model evaluation or source-rights claim."
            ),
            (
                "Category siblings, cells and paired arms share histories; "
                "independent units are binding families."
            ),
            (
                "Intervals are descriptive synthetic harness diagnostics; success "
                "cannot qualify neural architectures."
            ),
            (
                "The frozen proposal's conditional neural-fit/Transformer/GRU "
                "comparisons remain unperformed."
            ),
        ],
    }
    return {"score": summary[selected_mode]["value_query_accuracy"]}, rows, diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=("candidate", "control"))
    args = parser.parse_args()
    seed = int(os.environ["TRAINLAB_SEED"])
    if not 0 <= seed <= 2**32 - 1:
        raise ValueError("TRAINLAB_SEED must be an unsigned 32-bit integer")
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    metrics, predictions, diagnostics = run(seed, args.arm)
    for filename, payload in (
        ("metrics.json", metrics),
        ("predictions.json", predictions),
        ("diagnostics.json", diagnostics),
    ):
        with (output / filename).open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.write("\n")


if __name__ == "__main__":
    main()
