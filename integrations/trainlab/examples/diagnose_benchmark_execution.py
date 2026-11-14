"""Run pinned paired state references and shortcut controls on public examples."""

import argparse
import hashlib
import inspect
import json
from copy import deepcopy
from pathlib import Path

from trainlab.benchmark_execution import execute, freeze_panel
from trainlab.runner import write_json


def forward_state(case):
    values = {}
    aliases = {}
    for op, key, value in case["events"]:
        aliases.pop(key, None)
        if op == "LINK":
            values.pop(key, None)
            aliases[key] = value
        elif op == "SET":
            values[key] = value
        elif op == "COPY":
            values[key] = values.get(value)
        else:
            values.pop(key, None)
    target = case["query"]
    return values.get(aliases.get(target, target))


def backward_history(case):
    def lookup(target, events):
        for index in range(len(events) - 1, -1, -1):
            op, key, payload = events[index]
            if key != target:
                continue
            if op == "SET":
                return payload
            if op == "DELETE":
                return None
            source_history = events[:index] if op == "COPY" else events
            return lookup(payload, source_history)
        return None

    return lookup(case["query"], case["events"])


def latest_literal(case):
    return next((value for op, _, value in reversed(case["events"]) if op == "SET"), None)


def wrong_reference(case):
    return "incorrect"


def visible_label_shortcut(case):
    return case["cue"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    root = parser.parse_args().root
    root.mkdir(parents=True, exist_ok=False)
    rows = []
    for group, before, after in (("alpha", "red", "blue"), ("beta", "gold", "green")):
        for behavior in ("COPY", "LINK"):
            prefix = [["SET", "source", before], [behavior, "alias", "source"]]
            original = [[*item] for item in prefix] + [["SET", "unrelated", "noise"]]
            edited = original + [["DELETE", "source", None], ["SET", "source", after]]
            preserved = before if behavior == "COPY" else after
            rows.append(
                {
                    "id": group + "-" + behavior,
                    "group": group,
                    "original": {"events": original, "query": "alias", "cue": before},
                    "intervened": {"events": edited, "query": "alias", "cue": preserved},
                    "expected_original": before,
                    "expected_intervened": preserved,
                    "expect_change": behavior == "LINK",
                }
            )
    arms = {
        "reference_a": forward_state,
        "reference_b": backward_history,
        "shortcut": latest_literal,
    }
    variants = {
        "clean": (rows, arms, 384),
        "wrong_reference": (rows, {**arms, "reference_a": wrong_reference}, 384),
        "insufficient_groups": (rows[:2], arms, 384),
        "visible_label_shortcut": (rows, {**arms, "shortcut": visible_label_shortcut}, 384),
        "call_budget": (rows, arms, 2),
    }
    expected = {
        "clean": "TESTED",
        "wrong_reference": "FAILED",
        "insufficient_groups": "FAILED",
        "visible_label_shortcut": "FAILED",
        "call_budget": "INCONCLUSIVE",
    }
    result = {}
    for name, (cases, callbacks, limit) in variants.items():
        # Only the positive shortcut control receives a visible expected answer.
        cases = deepcopy(cases)
        if name != "visible_label_shortcut":
            for row in cases:
                for side in ("original", "intervened"):
                    del row[side]["cue"]
        frozen = freeze_panel(
            cases,
            source_sha256={
                arm: hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()
                for arm, fn in callbacks.items()
            },
            minimum_changed_groups=2,
            minimum_invariant_groups=2,
            maximum_shortcut_accuracy=0.5,
        )
        write_json(root / f"{name}-panel.json", frozen)
        report = execute(root / name, callbacks, max_calls=limit, **frozen)
        if report["status"] != expected[name]:
            raise RuntimeError(f"unexpected benchmark control state {name}: {report['status']}")
        result[name] = {
            "status": report["status"],
            "findings": sorted({finding["kind"] for finding in report["findings"]}),
            "calls": report["summary"]["observed_invocations"],
        }
    write_json(root / "summary.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
