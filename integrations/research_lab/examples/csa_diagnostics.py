"""Non-neural diagnostic comparators for WIL-TRAIN-001 public no-fit fixtures.

Both baselines consume only model_view history/query; neither gets typed events.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from csa_fixture import SPLITS, make_split, model_view, public_rows

TRAIN_PUT = re.compile(r"Record \d+: (\w+) stores the (\w+) in the (\w+)\.")
TRAIN_DEL = re.compile(r"Record \d+: (\w+) removes the (\w+) from storage\.")
OOD_PUT = re.compile(r"Log \d+ states that the (\w+) belonging to (\w+) is now kept at the (\w+)\.")
OOD_DEL = re.compile(r"Log \d+ reports that the (\w+) belonging to (\w+) is no longer stored anywhere\.")
TRAIN_QUERY = re.compile(r"Where does (\w+) currently keep the (\w+)\?")
OOD_QUERY = re.compile(r"Identify the current storage location of (\w+)'s (\w+)\.")


def strong_symbolic(view: dict) -> str:
    """Source-grammar-aware symbolic control; intentionally uses prior grammar."""
    query = view["query"]
    match = TRAIN_QUERY.fullmatch(query) or OOD_QUERY.fullmatch(query)
    if match is None:
        raise ValueError("unrecognized query")
    owner, item = match.groups()
    state: dict[tuple[str, str], str] = {}
    for line in view["history"].splitlines():
        if match := TRAIN_PUT.fullmatch(line):
            w, obj, place = match.groups()
            state[(w, obj)] = place
        elif match := TRAIN_DEL.fullmatch(line):
            w, obj = match.groups()
            state.pop((w, obj), None)
        elif match := OOD_PUT.fullmatch(line):
            obj, w, place = match.groups()
            state[(w, obj)] = place
        elif match := OOD_DEL.fullmatch(line):
            obj, w = match.groups()
            state.pop((w, obj), None)
        elif line == "The audit has ended; no additional changes were recorded.":
            continue
        else:
            raise ValueError("unsupported line; no silent guessing")
    return state.get((owner, item), "UNKNOWN")


def naive_recency(view: dict) -> str:
    """Shortcut control: use last observed location, ignoring identity/retraction."""
    tokens = re.findall(r"(?:in|at) the (\w+)\.", view["history"])
    return tokens[-1] if tokens else "UNKNOWN"


def evaluate(pairs: int = 120, seed: int = 71407) -> dict:
    report: dict = {"mode": "NO_FIT", "models_trained": 0, "seed": seed, "splits": {}}
    for i, split in enumerate(SPLITS):
        cases = make_split(split, seed + 1_000_003 * i, pairs)
        rows = public_rows(cases)
        by_kind = {}
        for kind in ("relevant_edit", "irrelevant_edit", "retraction"):
            subset = [r for r in rows if r["kind"] == kind]
            by_kind[kind] = {
                "n": len(subset),
                "symbolic_correct": sum(strong_symbolic(model_view(r)) == r["answer"] for r in subset),
                "recency_correct": sum(naive_recency(model_view(r)) == r["answer"] for r in subset),
            }
        report["splits"][split] = {"examples": len(rows), "by_kind": by_kind,
            "symbolic_accuracy": sum(x["symbolic_correct"] for x in by_kind.values()) / len(rows),
            "recency_accuracy": sum(x["recency_correct"] for x in by_kind.values()) / len(rows)}
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = evaluate()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
