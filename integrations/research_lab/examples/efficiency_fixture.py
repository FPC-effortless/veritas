"""Exact symbolic state/replay mechanism fixture; no neural-model qualification.

Both CLI arms execute the complete frozen paired timing experiment. ``candidate``
reports its worst primary-cell time reduction. ``control`` reports zero, the
explicit diagnostic null contrast, rather than inventing a second timing effect.
Only predictions.json is deterministic; timing evidence is intentionally variable.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

UNKNOWN = -1
CATEGORIES = ("present", "corrected", "deleted", "absent")
WARMUPS = 3
ROUNDS = 15
KEYS = (8, 32)
LENGTHS = (64, 256, 1024)
QUERIES = (4, 16)
THREAD_SETTINGS = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def workload(seed, keys, length, queries, *, suffix=False, final_category=None):
    """Freeze complete streams; only unrelated keys are used for filler edits."""
    identity = {
        "seed": seed,
        "keys": keys,
        "length": length,
        "queries": queries,
        "suffix": suffix,
        "final_category": final_category,
    }
    rng = random.Random(int(fingerprint(identity), 16))
    events = []
    labels = []

    def filler(count):
        for _ in range(count):
            key = rng.randrange(4, keys)
            if rng.random() < 0.25:
                events.append(("delete", key, None))
            else:
                events.append(("write", key, rng.randrange(16)))

    for number in range(queries):
        category = final_category or CATEGORIES[number % 4]
        key = CATEGORIES.index(category)
        prep = {
            "present": [("write", key, 3)],
            "corrected": [("write", key, 4), ("write", key, 9)],
            "deleted": [("write", key, 7), ("delete", key, None)],
            "absent": [],
        }[category]
        query_position = (
            length - 1 if final_category else ((number + 1) * length // (queries + 1)) - 1
        )
        remaining = query_position - len(events) - len(prep)
        if remaining < 0:
            raise AssertionError("frozen query spacing cannot fit lifecycle setup")
        if suffix:
            events.extend(prep)
            filler(remaining)
        else:
            filler(remaining)
            events.extend(prep)
        events.append(("query", key, None))
        labels.append(category)
    filler(length - len(events))
    assert len(events) == length
    assert sum(event[0] == "query" for event in events) == queries
    return identity, events, labels


def reference(events, labels):
    """Independent backwards event-list oracle, never a live-state dictionary."""
    answers = []
    categories = []
    for index, (operation, key, _) in enumerate(events):
        if operation != "query":
            continue
        prior = [event for event in events[:index] if event[1] == key and event[0] != "query"]
        if not prior:
            category, answer = "absent", UNKNOWN
        elif prior[-1][0] == "delete":
            category, answer = "deleted", UNKNOWN
        else:
            answer = prior[-1][2]
            values = {value for action, _, value in prior if action == "write"}
            category = "corrected" if len(values) > 1 else "present"
        categories.append(category)
        answers.append(answer)
    if categories != labels:
        raise AssertionError("independent lifecycle category reconstruction disagrees")
    return answers


def apply(state, event):
    operation, key, value = event
    if operation == "write":
        state[key] = value
    elif operation == "delete":
        state.pop(key, None)


def retained(events):
    state = {}
    answers = []
    transitions = 0
    maximum_live = 0
    for event in events:
        if event[0] == "query":
            answers.append(state.get(event[1], UNKNOWN))
        else:
            apply(state, event)
            transitions += 1
            maximum_live = max(maximum_live, len(state))
    return answers, transitions, len(events), maximum_live


def replay(events):
    answers = []
    transitions = 0
    visits = 0
    maximum_live = 0
    for index, event in enumerate(events):
        visits += 1
        if event[0] != "query":
            continue
        state = {}
        for prefix_index in range(index):
            previous = events[prefix_index]
            visits += 1
            if previous[0] != "query":
                apply(state, previous)
                transitions += 1
                maximum_live = max(maximum_live, len(state))
        answers.append(state.get(event[1], UNKNOWN))
    return answers, transitions, visits, maximum_live


def reset_rebuild(events):
    """Incremental updates plus explicit clear/rebuild at each query boundary."""
    state = {}
    answers = []
    transitions = 0
    visits = 0
    maximum_live = 0
    for index, event in enumerate(events):
        visits += 1
        if event[0] != "query":
            apply(state, event)
            transitions += 1
            maximum_live = max(maximum_live, len(state))
            continue
        state.clear()
        for prefix_index in range(index):
            previous = events[prefix_index]
            visits += 1
            if previous[0] != "query":
                apply(state, previous)
                transitions += 1
                maximum_live = max(maximum_live, len(state))
        answers.append(state.get(event[1], UNKNOWN))
    return answers, transitions, visits, maximum_live


def noop(events):
    """Same prefix traversals without memory semantics; not a quality baseline."""
    visits = 0
    for index, event in enumerate(events):
        visits += 1
        if event[0] == "query":
            for prefix_index in range(index):
                _ = events[prefix_index]
                visits += 1
    return visits


def expected_counters(events):
    # Independent enumerations avoid borrowing counters from either executor.
    transitions = sum(action != "query" for action, _, _ in events)
    query_indices = [i for i, event in enumerate(events) if event[0] == "query"]
    replay_transitions = sum(
        sum(event[0] != "query" for event in events[:index]) for index in query_indices
    )
    visits = len(events) + sum(query_indices)
    return {
        "retained": [transitions, len(events)],
        "replay": [replay_transitions, visits],
        "reset_rebuild": [transitions + replay_transitions, visits],
        "noop_visits": visits,
    }


def timed(function, events):
    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    result = function(events)
    cpu_ns = time.process_time_ns() - cpu_start
    wall_ns = time.perf_counter_ns() - wall_start
    return result, {"cpu_ns": cpu_ns, "wall_ns": wall_ns}


def check_result(name, result, answers, counters):
    if name == "noop":
        if result != counters["noop_visits"]:
            raise AssertionError("no-op event visit accounting failed")
    elif result[0] != answers or list(result[1:3]) != counters[name]:
        raise AssertionError(f"{name} reference correctness or operation accounting failed")


def measure(identity, events, labels):
    excluded_start = time.process_time_ns()
    answers = reference(events, labels)
    counters = expected_counters(events)
    category_counts = dict(sorted(Counter(labels).items()))
    expected_categories = (
        {identity["final_category"]} if identity["final_category"] else set(CATEGORIES)
    )
    if set(category_counts) != expected_categories or any(
        count <= 0 for count in category_counts.values()
    ):
        raise AssertionError("missing lifecycle category")
    functions = {
        "retained": retained,
        "replay": replay,
        "reset_rebuild": reset_rebuild,
        "noop": noop,
    }
    footprints = {}
    for name, function in functions.items():
        result = function(events)
        check_result(name, result, answers, counters)
        if name != "noop":
            footprints[name] = {"maximum_live_entries": result[3]}
    setup_cpu_ns = time.process_time_ns() - excluded_start
    for _ in range(WARMUPS):
        for name, function in functions.items():
            check_result(name, function(events), answers, counters)
    rounds = []
    validation_cpu_ns = 0
    for repetition in range(ROUNDS):
        order = ["retained", "replay"] if repetition % 2 == 0 else ["replay", "retained"]
        order += ["reset_rebuild", "noop"] if repetition % 2 == 0 else ["noop", "reset_rebuild"]
        values = {}
        for name in order:
            result, timing = timed(functions[name], events)
            validation_start = time.process_time_ns()
            check_result(name, result, answers, counters)
            validation_cpu_ns += time.process_time_ns() - validation_start
            if timing["cpu_ns"] <= 0 or timing["wall_ns"] <= 0:
                raise AssertionError("clock resolution insufficient for measured workload")
            values[name] = timing
        rounds.append({"round": repetition, "order": order, "timings": values})
    summaries = {}
    for name in functions:
        cpu_values = [item["timings"][name]["cpu_ns"] for item in rounds]
        wall_values = [item["timings"][name]["wall_ns"] for item in rounds]
        summaries[name] = {
            "median_cpu_ns": statistics.median(cpu_values),
            "min_cpu_ns": min(cpu_values),
            "max_cpu_ns": max(cpu_values),
            "median_wall_ns": statistics.median(wall_values),
            "min_wall_ns": min(wall_values),
            "max_wall_ns": max(wall_values),
            "median_cpu_ns_per_query": statistics.median(cpu_values) / len(answers),
        }
    paired = [
        (item["timings"]["replay"]["cpu_ns"] - item["timings"]["retained"]["cpu_ns"])
        / item["timings"]["replay"]["cpu_ns"]
        for item in rounds
    ]
    reduction = (
        summaries["replay"]["median_cpu_ns"] - summaries["retained"]["median_cpu_ns"]
    ) / summaries["replay"]["median_cpu_ns"]
    deterministic = {
        "identity": identity,
        "workload_sha256": fingerprint(events),
        "answers": answers,
        "category_counts": category_counts,
        "accuracy_by_category": dict.fromkeys(category_counts, 1.0),
        "expected_and_observed_counters": counters,
        "correctness": "ALL_EXACT",
        "history_canonical_bytes": len(encoded(events)),
        "retained_requires_history": False,
        "replay_requires_history": True,
        "footprints": footprints,
    }
    diagnostics = {
        "identity": identity,
        "rounds": rounds,
        "summaries": summaries,
        "fractional_cpu_reduction": reduction,
        "median_paired_fractional_cpu_reduction": statistics.median(paired),
        "paired_fractional_cpu_reduction_range": [min(paired), max(paired)],
        "excluded_reference_and_counter_setup_cpu_ns": setup_cpu_ns,
        "excluded_timed_result_validation_cpu_ns": validation_cpu_ns,
    }
    return deterministic, diagnostics


def cpu_identity():
    cpu = platform.processor() or "unavailable"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.partition(":")[2].strip()
                break
    except OSError:
        pass
    return cpu


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("candidate", "control"):
        raise SystemExit("usage: efficiency_fixture.py candidate|control")
    arm = sys.argv[1]
    for key, value in THREAD_SETTINGS.items():
        os.environ[key] = value
    seed = int(os.environ["TRAINLAB_SEED"])
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    output.mkdir(parents=True, exist_ok=True)
    whole_cpu_start = time.process_time_ns()
    whole_wall_start = time.perf_counter_ns()
    generation_cpu_ns = 0
    deterministic = []
    diagnostics = []
    conditions = [
        (keys, length, queries, False, None)
        for keys in KEYS
        for length in LENGTHS
        for queries in QUERIES
    ]
    conditions += [(keys, 1024, queries, True, None) for keys in KEYS for queries in QUERIES]
    conditions += [(keys, 1024, 1, True, category) for keys in KEYS for category in CATEGORIES]
    for keys, length, queries, suffix, final_category in conditions:
        generation_start = time.process_time_ns()
        identity, events, labels = workload(
            seed, keys, length, queries, suffix=suffix, final_category=final_category
        )
        generation_cpu_ns += time.process_time_ns() - generation_start
        prediction, timing = measure(identity, events, labels)
        deterministic.append(prediction)
        diagnostics.append(timing)
        if time.perf_counter_ns() - whole_wall_start > 60_000_000_000:
            raise TimeoutError("fixed 60-second fixture budget exceeded; run incomplete")
    primary = [
        row["fractional_cpu_reduction"]
        for row in diagnostics
        if row["identity"]["length"] == 1024
        and row["identity"]["queries"] == 16
        and not row["identity"]["suffix"]
        and row["identity"]["final_category"] is None
    ]
    if len(primary) != 2:
        raise AssertionError("primary grid incomplete")
    observed_score = min(primary)
    predictions = {
        "schema": "research_lab.efficiency_predictions.v1",
        "source_kind": "CONSTRUCTED",
        "seed": seed,
        "workloads": deterministic,
        "scope": "EXACT_SYMBOLIC_STATE_EXECUTION_AND_ACCOUNTING_ONLY",
        "qualification": "NOT_QUALIFIED",
    }
    predictions["prediction_payload_sha256"] = fingerprint(predictions)
    evidence = {
        "schema": "research_lab.efficiency_diagnostics.v1",
        "arm": arm,
        "seed": seed,
        "warmups_per_mode_per_workload": WARMUPS,
        "paired_timing_rounds_per_workload": ROUNDS,
        "workload_count": len(conditions),
        "observed_primary_candidate_score": observed_score,
        "primary_gate_this_seed": "PASS" if observed_score >= 0.2 else "FAIL",
        "control_score_semantics": (
            "ZERO_CONTRAST_DIAGNOSTIC_NULL; both arms execute the identical full paired experiment"
        ),
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "cpu": cpu_identity(),
            "workers": 1,
            "thread_settings": THREAD_SETTINGS,
            "cpu_clock": vars(time.get_clock_info("process_time")),
            "wall_clock": vars(time.get_clock_info("perf_counter")),
        },
        "excluded_workload_generation_cpu_ns": generation_cpu_ns,
        "total_fixture_cpu_ns_before_serialization": time.process_time_ns() - whole_cpu_start,
        "total_fixture_wall_ns_before_serialization": time.perf_counter_ns() - whole_wall_start,
        "measurements": diagnostics,
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "proposal_sha256": hashlib.sha256(
            (Path(__file__).parent / "proposals" / "efficiency.json").read_bytes()
        ).hexdigest(),
        "prediction_payload_sha256": predictions["prediction_payload_sha256"],
        "limitations": [
            "Exact symbolic stores; no trained neural architecture or superiority claim.",
            (
                "Only one independently generated workload seed is handled per "
                "invocation; aggregate the three frozen seeds externally."
            ),
            (
                "Single host and 15 dependent timing repeats per workload; no "
                "population confidence interval is claimed."
            ),
            (
                "Byte figures count canonical serialized histories, not heap RSS, "
                "peak process memory or deployment RAM."
            ),
            (
                "The harness retains full events for replay and scoring; "
                "retained_requires_history describes executor semantics, not total"
                " harness RAM."
            ),
            (
                "Live-entry maxima are instrumented inside both timers; this is "
                "the measured instrumented implementation, not bare dictionary "
                "speed."
            ),
            "No-op traversal measures loop overhead only; it does not answer queries.",
            (
                "Reset/rebuild also processes arriving updates, so its transition "
                "count includes incremental work plus replay work."
            ),
            (
                "No GPU, energy meter, monetary cost, optimized KV cache or equal-"
                "byte learned memory comparison."
            ),
            (
                "Timing changes across exact replications. Compare deterministic "
                "predictions exactly and numeric scores only under the separately "
                "preregistered tolerance."
            ),
            (
                "Reference scoring, generation, result validation and "
                "serialization are outside per-workload timers; their process "
                "scope is reported separately where measured."
            ),
            (
                "No scientific, frontier, commercial, publication or autonomous-"
                "agent qualification is conferred."
            ),
        ],
        "qualification": "NOT_QUALIFIED",
    }
    serialization_start = time.process_time_ns()
    prediction_text = json.dumps(predictions, indent=2, sort_keys=True, allow_nan=False) + "\n"
    evidence["excluded_prediction_serialization_cpu_ns"] = (
        time.process_time_ns() - serialization_start
    )
    (output / "predictions.json").write_text(prediction_text)
    (output / "diagnostics.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    (output / "metrics.json").write_text(
        json.dumps({"score": observed_score if arm == "candidate" else 0.0}, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "arm": arm,
                "seed": seed,
                "workloads": len(conditions),
                "observed_candidate_score": observed_score,
                "qualification": "NOT_QUALIFIED",
            }
        )
    )


if __name__ == "__main__":
    main()
