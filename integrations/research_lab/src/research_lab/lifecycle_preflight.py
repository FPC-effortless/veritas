"""Bounded lifecycle data preflight and reviewed once-only TrainLab dispatch.

Trusted local commands/reviewers, not a sandbox or scientific qualification.
Only TRAIN/validation are selected; Forge still verifies all release bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from forge_data.dataset import Dataset
from trainlab.runner import (
    LabError,
    _constant,
    _pairs,
    contained_file,
    digest,
    load_config,
    read_json,
    run_experiment,
    write_json,
)

from investigation_world.benchmark.lifecycle_observability import audit_pair

from .adapters import import_forge, import_trainlab
from .core import Controller, name
from .ecosystem import _runtime, _sha
from .evidence import link, put_node

SCHEMA = "veritas.lifecycle-preflight.v1"
SPLITS = ("train", "validation")
STRATA = ("overwrite", "delete_recreate")
DATA_FILES = ("manifest.json", "train.jsonl", "validation.jsonl", "test.jsonl")


def _require(condition, message):
    if not condition:
        raise LabError(message)


def _pinned_json(path, pin):
    with path.open("rb") as stream:
        data = stream.read(1024 * 1024 + 1)
    _require(len(data) <= 1024 * 1024 and hashlib.sha256(data).hexdigest() == pin,
             "pinned JSON mismatch")
    return json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant), data


def _files(spec, source):
    _require(isinstance(spec, dict) and set(spec) == {
        "schema", "dataset", "manifest_sha256", "cutoff", "pairs", "recipe",
        "design", "minimum_groups"
    } and spec["schema"] == SCHEMA, "invalid preflight specification")
    _require(type(spec["minimum_groups"]) is int and 30 <= spec["minimum_groups"] <= 2048,
             "existing 30-group floor cannot be weakened")
    _require(isinstance(spec["dataset"], str), "invalid dataset path")
    required = {spec["dataset"] + "/" + n for n in DATA_FILES}
    required.update((spec["pairs"], spec["design"]))
    recipe_path = contained_file(source, spec["recipe"])
    _require(recipe_path.parent == source, "recipe must be in the source root")
    recipe = load_config(recipe_path)
    _require(recipe["source_kind"] == "CONSTRUCTED"
             and recipe["split_identity"] == spec["manifest_sha256"]
             and required <= set(recipe["inputs"]), "recipe input/manifest binding mismatch")
    _require(contained_file(source, spec["design"]).stat().st_size > 0, "design is required")
    files = required | set(recipe["inputs"]) | {spec["recipe"]}
    for filename in files:
        contained_file(source, filename)
    _require(len(files) <= 128, "too many frozen inputs")
    return files


def prepare(spec_path: Path, root: Path):
    spec_path, root = Path(spec_path).resolve(), Path(root).resolve()
    spec = read_json(spec_path)
    files = _files(spec, spec_path.parent)
    _require(not root.exists(), "preflight destination must be new")
    root.mkdir(parents=True, mode=0o700)
    for filename in sorted(files):
        target = root / "inputs" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(contained_file(spec_path.parent, filename), target)
    protocol = {
        "schema": SCHEMA, "spec": spec, "runtime": _runtime(),
        "files": {n: digest(contained_file(root / "inputs", n)) for n in sorted(files)},
    }
    write_json(root / "protocol.json", protocol)
    return {"protocol_sha256": digest(root / "protocol.json")}


def _load(root, pin):
    protocol_path = contained_file(root, "protocol.json")
    p, _ = _pinned_json(protocol_path, pin)
    _require(set(p) == {"schema", "spec", "runtime", "files"} and p["schema"] == SCHEMA,
             "invalid frozen protocol")
    _require(p["runtime"] == _runtime(), "frozen runtime changed")
    inputs = root / "inputs"
    _require(set(p["files"]) == _files(p["spec"], inputs), "frozen input closure differs")
    for filename, expected in p["files"].items():
        _require(digest(contained_file(inputs, filename)) == expected, "frozen input changed")
    return p


def assess(root: Path, pin: str):
    """Recompute necessary conditions; never trust a stored diagnostic verdict."""
    root = Path(root).resolve()
    p = _load(root, pin)
    spec, inputs = p["spec"], root / "inputs"
    data = Dataset(inputs / spec["dataset"], manifest_sha256=spec["manifest_sha256"])
    rows = {}
    for split in SPLITS:
        examples = data.examples(split, cutoff=spec["cutoff"], feature_fields=["memory"])
        _require(len(examples) == data.summary()["split_records"][split] and examples,
                 "preflight must cover the entire development split at the declared cutoff")
        for row in examples:
            _require(row["target"] is None, "target-bearing development rows unsupported")
            rows[row["record_id"]] = (split, row)
    pairs = read_json(contained_file(inputs, spec["pairs"]))
    _require(isinstance(pairs, list) and 1 <= len(pairs) <= 2048, "bounded pair list required")
    stats = {s: {t: {"pairs": 0, "sensitive_pairs": 0, "preserved_pairs": 0,
                    "groups": set(), "sensitive_groups": set(), "preserved_groups": set()}
                 for t in STRATA} for s in SPLITS}
    used = set()
    for pair in pairs:
        _require(isinstance(pair, dict) and set(pair) == {"records", "stratum"}
                 and isinstance(pair["stratum"], str) and pair["stratum"] in STRATA,
                 "invalid pair descriptor")
        ids = pair["records"]
        _require(isinstance(ids, list) and len(ids) == 2
                 and all(isinstance(i, str) and i in rows and i not in used for i in ids)
                 and ids[0] != ids[1], "pair must select two unused development rows")
        (split, left), (other_split, right) = (rows[i] for i in ids)
        _require(split == other_split and left["subject_id"] == right["subject_id"],
                 "pair crosses split or declared group")
        used.update(ids)
        diagnostic = audit_pair(left["features"]["memory"], right["features"]["memory"],
                                pair["stratum"])
        interventions = [v for r in diagnostic["rows"] for v in r["interventions"]]
        sensitive = any(v["changed_composed_keys"] for v in interventions)
        preserved = any(w["preserved_at_own_final_query"]
                        and w["saved_key"] in v["changed_composed_keys"]
                        for v in interventions for w in v["absence_snapshots"])
        count = stats[split][pair["stratum"]]
        count["pairs"] += 1
        count["groups"].add(left["subject_id"])
        for prefix, present in (("sensitive", sensitive), ("preserved", preserved)):
            count[prefix + "_pairs"] += int(present)
            if present:
                count[prefix + "_groups"].add(left["subject_id"])
    _require(used == set(rows), "pair inventory omits development rows")
    reasons = []
    for split in SPLITS:
        for stratum in STRATA:
            count = stats[split][stratum]
            for field in ("groups", "sensitive_groups", "preserved_groups"):
                count[field] = len(count[field])
            checks = [("groups", "INSUFFICIENT_DECLARED_GROUPS")]
            if stratum == "delete_recreate":
                checks += [("sensitive_groups", "INSUFFICIENT_ABSENCE_SENSITIVE_GROUPS"),
                           ("preserved_groups", "INSUFFICIENT_PRESERVED_ABSENCE_GROUPS")]
            for field, code in checks:
                if count[field] < spec["minimum_groups"]:
                    reasons.append({"split": split, "stratum": stratum, "code": code})
    return {
        "schema": SCHEMA, "protocol_sha256": pin, "manifest_sha256": spec["manifest_sha256"],
        "status": "BLOCKED" if reasons else "READY_FOR_REVIEW", "reasons": reasons,
        "minimum_groups": spec["minimum_groups"], "counts": stats,
        "grouping": "DECLARED_FORGE_SUBJECTS_NOT_VERIFIED_CAUSAL_DIVERSITY",
        "scientific_qualification": "NOT_QUALIFIED",
        "scope": "DEVELOPMENT_OBSERVABILITY_NECESSARY_CONDITIONS_ONLY",
    }


def _immutable(path, value):
    if path.exists():
        _require(read_json(path) == value, "saved preflight evidence changed")
    else:
        write_json(path, value)


def record(root: Path, pin: str):
    """Retain blocked and review-ready findings without publishing row identifiers."""
    root = Path(root).resolve()
    report = assess(root, pin)
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    _immutable(reports / (_sha(report) + ".json"), report)
    _immutable(root / "preflight.json", report)
    lab = Controller(root / "research_lab")
    spec = read_json(root / "protocol.json")["spec"]
    import_forge(lab, root / "inputs" / spec["dataset"], spec["manifest_sha256"])
    finding = "preflight." + _sha(report)[:24]
    put_node(lab, finding, "finding", report)
    link(lab, finding, "derived_from", "forge." + spec["manifest_sha256"][:24])
    return report


def verify(root: Path, pin: str):
    """Read-only report verification, with no command or graph writes."""
    root = Path(root).resolve()
    report = assess(root, pin)
    for filename in ("preflight.json", "reports/" + _sha(report) + ".json"):
        _require(read_json(contained_file(root, filename)) == report,
                 "saved preflight evidence changed")
    return report


def dispatch(root: Path, pin: str, review_path: Path, review_sha256: str):
    """A trusted reviewed recipe runs at most once, including interrupted attempts."""
    root = Path(root).resolve()
    report = record(root, pin)
    _require(report["status"] == "READY_FOR_REVIEW", "preflight blocked; no dispatch")
    review_path = Path(review_path).resolve()
    review, review_bytes = _pinned_json(review_path, review_sha256)
    _require(isinstance(review, dict) and set(review) == {
        "schema", "protocol_sha256", "report_sha256", "verdict", "findings",
        "independence", "reviewer", "summary"
    }, "invalid pre-execution review")
    _require(review["schema"] == "veritas.lifecycle-preflight-review.v1"
             and review["protocol_sha256"] == pin and review["report_sha256"] == _sha(report)
             and review["verdict"] == "clean" and review["findings"] == []
             and review["independence"] == "SEPARATE_SESSION_OPERATOR_ASSERTED"
             and isinstance(review["summary"], str) and 0 < len(review["summary"].strip()) <= 4000,
             "review is stale, blocking or lacks independence")
    name(review["reviewer"])
    attempt = root / "execution"
    try:
        attempt.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise LabError("attempt already reserved; no automatic retry") from exc
    (attempt / "review.json").write_bytes(review_bytes)
    _require(digest(attempt / "review.json") == review_sha256, "retained review pin mismatch")
    # A crash from here onward leaves the reservation intact. Trusted local code
    # can still change files or bypass this CLI; this is not OS-level enforcement.
    p = _load(root, pin)
    run = run_experiment(contained_file(root / "inputs", p["spec"]["recipe"]), attempt / "runs")
    _load(root, pin)
    lab = Controller(root / "research_lab")
    import_trainlab(lab, attempt / "runs" / run["id"])
    review_id = "preflight-review." + review_sha256[:24]
    put_node(lab, review_id, "evidence", review)
    link(lab, review_id, "derived_from", "preflight." + _sha(report)[:24])
    link(lab, "trainlab." + run["id"], "derived_from", review_id)
    return {"status": run["status"], "run_id": run["id"], "review_sha256": review_sha256,
            "protocol_sha256": pin, "scientific_qualification": "NOT_QUALIFIED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("prepare")
    build.add_argument("spec", type=Path)
    build.add_argument("root", type=Path)
    for action in ("record", "verify", "dispatch"):
        command = commands.add_parser(action)
        command.add_argument("root", type=Path)
        command.add_argument("--protocol-sha256", required=True)
        if action == "dispatch":
            command.add_argument("--review", type=Path, required=True)
            command.add_argument("--review-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.spec, args.root)
        elif args.command == "dispatch":
            result = dispatch(args.root, args.protocol_sha256, args.review, args.review_sha256)
        else:
            result = {"record": record, "verify": verify}[args.command](
                args.root, args.protocol_sha256)
        payload = {"report_sha256": _sha(result), "report": result} if args.command in (
            "record", "verify"
        ) else result
        print(json.dumps(payload, indent=2, sort_keys=True))
        success = args.command == "prepare" or result.get("status") == (
            "succeeded" if args.command == "dispatch" else "READY_FOR_REVIEW"
        )
        return 0 if success else 1
    except (OSError, ValueError, KeyError, TypeError):
        # Detailed source/row identifiers belong in private diagnostics, not CLI errors.
        parser.exit(2, "lifecycle preflight: invalid, changed or unadmitted evidence\n")


if __name__ == "__main__":
    raise SystemExit(main())
