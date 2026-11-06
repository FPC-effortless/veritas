"""WIL-TRAIN-002: deterministic two-hop counterfactual state diagnostic.

No neural fits, no protected TEST data. Only TRAIN and publicly diagnostic DEV
splits. Typed events are NEVER returned by model_view().
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path

PROJECTS = ("amber", "blue", "coral", "dawn", "elm", "frost", "green", "harbor")
PEOPLE = ("Mira", "Tovo", "Nira", "Lema", "Sari", "Pavo", "Kina", "Rova")
PLACES = ("loft", "vault", "studio", "porch", "gallery", "shed", "library", "hall")
SPLITS = ("train", "dev_iid", "dev_ood_syntax", "dev_ood_comp")
KINDS = ("reassign", "relocate", "irrelevant_relocate", "unassign")
LENGTHS = (8, 32, 128)
SUFFIX = "The audit is complete. There are no further changes."


def condition(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def assigned_pair_allowed(project: str, person: str, split: str) -> bool:
    heldout = (PROJECTS.index(project) + PEOPLE.index(person)) % 4 == 0
    return heldout if split == "dev_ood_comp" else not heldout


def event(kind: str, project: str | None = None, person: str | None = None,
          place: str | None = None) -> dict:
    condition(kind in ("assign", "unassign", "locate", "vacate"), "unknown event")
    return {"kind": kind, "project": project, "person": person, "place": place}


def replay(events: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """Generative teacher, not a model-visible feature or the independent parser."""
    owners: dict[str, str] = {}
    locations: dict[str, str] = {}
    for ev in events:
        kind, project, person, place = (ev[k] for k in ("kind", "project", "person", "place"))
        if kind == "assign":
            condition(project in PROJECTS and person in PEOPLE, "invalid assignment")
            owners[project] = person
        elif kind == "unassign":
            condition(project in PROJECTS, "invalid unassignment")
            owners.pop(project, None)
        elif kind == "locate":
            condition(person in PEOPLE and place in PLACES, "invalid location")
            locations[person] = place
        elif kind == "vacate":
            condition(person in PEOPLE, "invalid vacancy")
            locations.pop(person, None)
        else:
            raise ValueError("unsupported event")
    return owners, locations


def answer(events: list[dict], project: str) -> str:
    owners, locations = replay(events)
    return locations.get(owners.get(project, ""), "UNKNOWN")


def render(ev: dict, serial: int, grammar: str) -> str:
    kind, p, who, place = (ev[k] for k in ("kind", "project", "person", "place"))
    if grammar == "base":
        if kind == "assign": return f"Record {serial}: Project {p} is assigned to {who}."
        if kind == "unassign": return f"Record {serial}: Project {p} has no assigned person."
        if kind == "locate": return f"Record {serial}: {who} is at the {place}."
        return f"Record {serial}: {who} has no current location."
    if grammar == "ood":
        if kind == "assign": return f"Entry {serial} appoints {who} as the custodian of project {p}."
        if kind == "unassign": return f"Entry {serial} revokes the custodian for project {p}."
        if kind == "locate": return f"Entry {serial} places the person named {who} inside the {place}."
        return f"Entry {serial} reports that the whereabouts of {who} are unknown."
    raise ValueError("unknown grammar")


def query(project: str, grammar: str) -> str:
    if grammar == "base": return f"Where is the custodian of project {project}?"
    if grammar == "ood": return f"State the location of whoever is responsible for project {project}."
    raise ValueError("unknown grammar")


@dataclass(frozen=True)
class Pair:
    ident: str
    kind: str
    split: str
    length: int
    project: str
    cross_project: str | None
    a: dict
    b: dict
    events_a: tuple[dict, ...]
    events_b: tuple[dict, ...]


def make_pair(rng: random.Random, split: str, length: int, kind: str, index: int) -> Pair:
    condition(split in SPLITS and kind in KINDS and length in LENGTHS, "bad spec")
    project, cross_project = rng.sample(PROJECTS, 2)
    eligible = [w for w in PEOPLE if assigned_pair_allowed(project, w, split)]
    worker_a, worker_b = rng.sample(eligible, 2)
    cross_eligible = [w for w in PEOPLE if w not in (worker_a, worker_b)
                      and assigned_pair_allowed(cross_project, w, "train")]
    if not cross_eligible:
        cross_eligible = [w for w in PEOPLE if w not in (worker_a, worker_b)]
    worker_c = rng.choice(cross_eligible)
    loc_a, loc_b, loc_c, new_a, new_b = rng.sample(PLACES, 5)
    base = [
        event("assign", project=project, person=worker_a),
        event("assign", project=cross_project, person=worker_c),
        event("locate", person=worker_a, place=loc_a),
        event("locate", person=worker_b, place=loc_b),
        event("locate", person=worker_c, place=loc_c),
    ]
    noncritical_projects = [p for p in PROJECTS if p not in (project, cross_project)]
    noncritical_workers = [w for w in PEOPLE if w not in (worker_a, worker_b, worker_c)]
    noise: list[dict] = []
    while len(base) + len(noise) < length - 1:
        if rng.getrandbits(1):
            p = rng.choice(noncritical_projects)
            w = rng.choice([w for w in PEOPLE if assigned_pair_allowed(p, w, "train")])
            noise.append(event("assign", project=p, person=w))
        else:
            noise.append(event("locate", person=rng.choice(noncritical_workers),
                               place=rng.choice(PLACES)))
    prefix = base + noise
    rng.shuffle(prefix)
    if kind == "reassign":
        edit_a = event("assign", project=project, person=worker_a)
        edit_b = event("assign", project=project, person=worker_b)
    elif kind == "relocate":
        edit_a = event("locate", person=worker_a, place=new_a)
        edit_b = event("locate", person=worker_a, place=new_b)
    elif kind == "irrelevant_relocate":
        edit_a = event("locate", person=worker_c, place=new_a)
        edit_b = event("locate", person=worker_c, place=new_b)
    else:
        edit_a = event("unassign", project=project)
        edit_b = event("assign", project=project, person=worker_b)
        if rng.getrandbits(1):
            edit_a, edit_b = edit_b, edit_a

    grammar = "ood" if split == "dev_ood_syntax" else "base"
    out = []
    event_rows = []
    for edit in (edit_a, edit_b):
        evs = prefix + [edit]
        hist = "\n".join(render(ev, pos + 1, grammar) for pos, ev in enumerate(evs)) + "\n" + SUFFIX
        out.append({"history": hist, "query": query(project, grammar), "answer": answer(evs, project)})
        event_rows.append(tuple(evs))
    p = Pair(f"{split}-{length}-{index:06d}", kind, split, length, project,
             cross_project if kind == "irrelevant_relocate" else None,
             out[0], out[1], event_rows[0], event_rows[1])
    validate_pair(p)
    return p


def validate_pair(p: Pair) -> None:
    condition(len(p.events_a) == len(p.events_b) == p.length, "wrong event count")
    condition(p.events_a[:-1] == p.events_b[:-1], "event prefix changed")
    condition(p.events_a[-1] != p.events_b[-1], "missing changed event")
    condition(p.a["query"] == p.b["query"], "query changed")
    ah, bh = p.a["history"].splitlines(), p.b["history"].splitlines()
    condition(ah[:-2] == bh[:-2] and ah[-1] == bh[-1] == SUFFIX, "history mismatch")
    condition(len(ah) == len(bh) == p.length + 1, "history length mismatch")
    for row, es in ((p.a, p.events_a), (p.b, p.events_b)):
        condition(row["answer"] == answer(list(es), p.project), "teacher label drift")
        condition(set(model_view(row)) == {"history", "query"}, "oracle input leak")
    if p.kind == "irrelevant_relocate":
        condition(p.a["answer"] == p.b["answer"], "irrelevant answer changed")
        condition(p.cross_project is not None, "missing cross query")
        condition(answer(list(p.events_a), p.cross_project) != answer(list(p.events_b), p.cross_project),
                  "cross query not sensitive")
    else:
        condition(p.a["answer"] != p.b["answer"], "relevant change did not flip answer")
    # The exact frozen candidate is withheld as an (project, worker) pair,
    # not an unseen individual project or worker token.
    final_assigned = [es for es in (p.events_a, p.events_b) if es[-1]["kind"] == "assign"]
    if p.split == "dev_ood_comp":
        for es in (p.events_a, p.events_b):
            seed_assignment = next(ev for ev in es if ev["kind"] == "assign" and ev["project"] == p.project)
            condition(assigned_pair_allowed(p.project, seed_assignment["person"], p.split),
                      "test heldout composition not withheld")
        for es in final_assigned:
            condition(assigned_pair_allowed(p.project, es[-1]["person"], p.split),
                      "test final assignment not withheld")
    else:
        for es in (p.events_a, p.events_b):
            for ev in es:
                if ev["kind"] == "assign":
                    condition(assigned_pair_allowed(ev["project"], ev["person"], "train"),
                              "TRAIN/DEV contamination by heldout assignment")


def model_view(row: dict) -> dict[str, str]:
    return {"history": row["history"], "query": row["query"]}


def generate(split: str, length: int, pairs: int, seed: int) -> list[Pair]:
    condition(pairs >= len(KINDS) and pairs % len(KINDS) == 0, "pairs must be multiple of four")
    condition(split in SPLITS and length in LENGTHS, "invalid split/length")
    rng = random.Random(seed)
    kinds = list(KINDS) * (pairs // len(KINDS))
    rng.shuffle(kinds)
    return [make_pair(rng, split, length, kind, i) for i, kind in enumerate(kinds)]


def labeled_rows(pairs: list[Pair]) -> list[dict]:
    return [{"pair_id": p.ident, "kind": p.kind, "split": p.split, "length": p.length,
             "arm": arm, **row} for p in pairs for arm, row in (("a", p.a), ("b", p.b))]


def cross_rows(pairs: list[Pair]) -> list[dict]:
    out = []
    for p in pairs:
        if p.kind != "irrelevant_relocate":
            continue
        grammar = "ood" if p.split == "dev_ood_syntax" else "base"
        for arm, row, evs in (("a", p.a, p.events_a), ("b", p.b, p.events_b)):
            out.append({"pair_id": p.ident, "kind": "cross_relevance", "split": p.split,
                        "length": p.length, "arm": arm, "history": row["history"],
                        "query": query(p.cross_project, grammar),
                        "answer": answer(list(evs), p.cross_project)})
    return out


def emit(root: Path, seed: int = 49621, n: int = 40) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"mode": "PUBLIC_DIAGNOSTIC_NO_FIT", "seed": seed, "pairs_per_split_length": n,
                      "files": {}}
    for si, split in enumerate(SPLITS):
        for length in LENGTHS:
            pairs = generate(split, length, n, seed + 1000003 * si + length * 67)
            primary = labeled_rows(pairs)
            secondary = cross_rows(pairs)
            file = f"{split}_L{length}.jsonl"
            raw = b"".join((json.dumps(r, sort_keys=True) + "\n").encode() for r in primary + secondary)
            (root / file).write_bytes(raw)
            manifest["files"][file] = {"sha256": hashlib.sha256(raw).hexdigest(),
                                        "primary": len(primary), "secondary": len(secondary),
                                        "pairs": n}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=49621)
    parser.add_argument("--pairs", type=int, default=40)
    x = parser.parse_args()
    print(json.dumps(emit(x.output, x.seed, x.pairs), indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
