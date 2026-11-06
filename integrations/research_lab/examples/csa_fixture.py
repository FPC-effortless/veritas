"""WIL-TRAIN-001 public, synthetic, NO-FIT counterfactual state fixture.

This produces only TRAIN / diagnostic DEV examples. It does not generate a
sealed scientific TEST set, use neural models, or authorize any compute run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path

ENTITIES = ("Nira", "Tovo", "Lema", "Sari", "Deka", "Pavo", "Kina", "Rova")
ITEMS = ("badge", "parcel", "ledger", "token", "map", "camera", "book", "key")
PLACES = ("studio", "vault", "loft", "porch", "gallery", "shed", "library", "hall")
KINDS = ("relevant_edit", "irrelevant_edit", "retraction")
SPLITS = ("train", "dev_iid", "dev_ood_syntax")


def _event(kind: str, owner: str, item: str, place: str | None = None) -> dict:
    assert kind in ("put", "retract")
    return {"kind": kind, "owner": owner, "item": item, "place": place}


def replay(events: list[dict]) -> dict[tuple[str, str], str | None]:
    """Pure semantic oracle, not part of the model-visible observation."""
    state: dict[tuple[str, str], str | None] = {}
    for event in events:
        key = (event["owner"], event["item"])
        if event["kind"] == "put":
            if event["place"] not in PLACES:
                raise ValueError("put requires a known place")
            state[key] = event["place"]
        elif event["kind"] == "retract":
            state[key] = None
        else:
            raise ValueError("unrecognized event")
    return state


def render(event: dict, syntax: str, record_id: int) -> str:
    who, item, place = event["owner"], event["item"], event["place"]
    if syntax == "train":
        if event["kind"] == "put":
            return f"Record {record_id}: {who} stores the {item} in the {place}."
        return f"Record {record_id}: {who} removes the {item} from storage."
    if syntax == "ood":
        if event["kind"] == "put":
            return f"Log {record_id} states that the {item} belonging to {who} is now kept at the {place}."
        return f"Log {record_id} reports that the {item} belonging to {who} is no longer stored anywhere."
    raise ValueError(syntax)


def render_query(owner: str, item: str, syntax: str) -> str:
    return (f"Where does {owner} currently keep the {item}?" if syntax == "train"
            else f"Identify the current storage location of {owner}'s {item}.")


@dataclass(frozen=True)
class Case:
    pair_id: str
    kind: str
    split: str
    a: dict
    b: dict
    # Typed events are retained locally for fixture verification; never export
    # them in model-visible examples or write them to the public JSONL.
    events_a: tuple[dict, ...]
    events_b: tuple[dict, ...]
    key: tuple[str, str]


def model_view(row: dict) -> dict[str, str]:
    """Only these fields may reach a neural model's input adapter."""
    return {"history": row["history"], "query": row["query"]}


def make_case(rng: random.Random, index: int, kind: str, split: str) -> Case:
    if kind not in KINDS or split not in SPLITS:
        raise ValueError("Unknown kind/split")
    syntax = "ood" if split == "dev_ood_syntax" else "train"
    owner, other_owner, extra_owner = rng.sample(ENTITIES, 3)
    item, other_item, extra_item = rng.sample(ITEMS, 3)
    initial, new_a, new_b, extra_place, extra_place_2 = rng.sample(PLACES, 5)
    target = (owner, item)
    noise_key = (other_owner, other_item)

    # Prefix and suffix are exactly shared within each pair. Records contain
    # multiple keys to defeat a single-key or last-place lookup shortcut.
    prefix = [
        _event("put", owner, item, initial),
        _event("put", other_owner, other_item, extra_place),
        _event("put", extra_owner, extra_item, extra_place_2),
    ]
    rng.shuffle(prefix)
    # A distractor edit is fixed across both arms, including retraction pairs.
    common_noise = _event("put", extra_owner, extra_item, extra_place)
    prefix.append(common_noise)

    if kind == "relevant_edit":
        edit_a = _event("put", owner, item, new_a)
        edit_b = _event("put", owner, item, new_b)
    elif kind == "irrelevant_edit":
        edit_a = _event("put", noise_key[0], noise_key[1], new_a)
        edit_b = _event("put", noise_key[0], noise_key[1], new_b)
    else:
        edit_a = _event("retract", owner, item)
        edit_b = _event("put", owner, item, new_b)
        # Randomize whether A or B is the removal arm to avoid arm-label hints.
        if rng.getrandbits(1):
            edit_a, edit_b = edit_b, edit_a

    # Fixed suffix preserves the same final surface/query; the changed event
    # is not the final token sequence.
    suffix = "The audit has ended; no additional changes were recorded."
    question = render_query(owner, item, syntax)
    rows = []
    histories = []
    for edit in (edit_a, edit_b):
        events = prefix + [edit]
        history = "\n".join(render(ev, syntax, i + 1) for i, ev in enumerate(events))
        history += "\n" + suffix
        expected = replay(events).get(target)
        rows.append({
            "history": history,
            "query": question,
            "answer": expected if expected is not None else "UNKNOWN",
        })
        histories.append(tuple(events))
    if kind == "relevant_edit" and rows[0]["answer"] == rows[1]["answer"]:
        raise AssertionError("counterfactual labels must differ")
    if kind == "irrelevant_edit" and rows[0]["answer"] != rows[1]["answer"]:
        raise AssertionError("irrelevant edits must preserve the answer")
    if kind == "retraction" and {rows[0]["answer"], rows[1]["answer"]} != {"UNKNOWN", new_b}:
        raise AssertionError("retraction intervention mismatch")
    pair_id = f"{split}-{index:06d}"
    return Case(pair_id, kind, split, rows[0], rows[1], histories[0], histories[1], target)


def make_split(split: str, seed: int, n_pairs: int) -> list[Case]:
    if split not in SPLITS or n_pairs < 3 or n_pairs % len(KINDS):
        raise ValueError("n_pairs must be positive multiple of three and >=3")
    rng = random.Random(seed)
    kinds = list(KINDS) * (n_pairs // len(KINDS))
    rng.shuffle(kinds)
    cases = [make_case(rng, i, kind, split) for i, kind in enumerate(kinds)]
    validate(cases)
    return cases


def validate(cases: list[Case]) -> dict:
    seen: set[tuple[str, str]] = set()
    for case in cases:
        a, b = case.a, case.b
        assert case.pair_id not in seen
        assert a["query"] == b["query"]
        assert a["history"].splitlines()[-1] == b["history"].splitlines()[-1]
        assert a["history"].splitlines()[:-2] == b["history"].splitlines()[:-2]
        assert len(case.events_a) == len(case.events_b) == 5
        assert case.events_a[:-1] == case.events_b[:-1]
        assert sum(x != y for x, y in zip(case.events_a, case.events_b)) == 1
        for row, events in ((a, case.events_a), (b, case.events_b)):
            replay_answer = replay(list(events)).get(case.key)
            assert row["answer"] == (replay_answer or "UNKNOWN")
            assert set(model_view(row)) == {"history", "query"}
            assert row["answer"] not in model_view(row)
        if case.kind == "irrelevant_edit":
            assert a["answer"] == b["answer"]
        else:
            assert a["answer"] != b["answer"]
        # Pair-specific unobserved-history control: any fixed answer for the
        # same query scores no more than 1/2 on these *conflicting* arms.
        seen.add(case.pair_id)
    return {
        "pair_count": len(cases),
        "row_count": len(cases) * 2,
        "by_kind": {k: sum(x.kind == k for x in cases) for k in KINDS},
        "opposite_answer_pairs": sum(c.a["answer"] != c.b["answer"] for c in cases),
        "same_answer_pairs": sum(c.a["answer"] == c.b["answer"] for c in cases),
    }


def public_rows(cases: list[Case]) -> list[dict]:
    """Labeled *diagnostic* rows; hide metadata and oracle from model input."""
    out = []
    for case in cases:
        for arm, row in (("a", case.a), ("b", case.b)):
            out.append({"pair_id": case.pair_id, "arm": arm, "kind": case.kind,
                        "split": case.split, **row})
    return out


def export(root: Path, seed: int, pairs: int) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict] = {}
    for i, split in enumerate(SPLITS):
        # Distinct deterministic streams; public DEV is NOT a sealed TEST.
        cases = make_split(split, seed + 1_000_003 * i, pairs)
        text = "".join(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n"
                       for row in public_rows(cases))
        path = root / f"csa_{split}.jsonl"
        path.write_text(text, encoding="utf-8")
        files[split] = {"file": path.name, "sha256": hashlib.sha256(text.encode()).hexdigest(),
                        **validate(cases)}
    manifest = {"protocol": "WIL-TRAIN-001-NOFIT-v0.1", "seed": seed,
                "not_scientific_test": True, "no_model_training": True,
                "model_visible_fields": ["history", "query"], "splits": files}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=71407)
    parser.add_argument("--pairs", type=int, default=120)
    args = parser.parse_args()
    print(json.dumps(export(args.output, args.seed, args.pairs), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
