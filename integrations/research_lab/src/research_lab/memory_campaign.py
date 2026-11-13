"""Frozen public memory campaigns around existing Forge and TrainLab interfaces."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from forge_data.dataset import Dataset
from investigation_world.benchmark.memory_comparison import score, state
from investigation_world.evidence import (
    EvidenceArtifactRef,
    EvidenceOutcome,
    EvidenceProducerRef,
    EvidenceRecord,
    EvidenceSubjectRef,
    EvidenceVisibility,
)
from trainlab.runner import (
    LabError,
    contained_file,
    digest,
    load_config,
    read_json,
    run_experiment,
    verify_run,
    write_json,
)

from .adapters import import_forge, import_trainlab
from .core import Controller
from .ecosystem import _runtime, _sha
from .evidence import link, put_node

SCHEMA = "veritas.memory-campaign.v1"
PREDICTIONS = "memory_predictions.json"


def _id(value):
    return isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value)


def _spec(spec, directory):
    if not isinstance(spec, dict) or set(spec) != {
        "schema", "dataset", "cutoff", "split", "design", "slots"
    } or spec["schema"] != SCHEMA or spec["split"] not in ("train", "validation"):
        raise LabError("public train/validation campaign specification required")
    manifest = contained_file(directory, spec["dataset"] + "/manifest.json")
    design = contained_file(directory, spec["design"])
    if not design.stat().st_size:
        raise LabError("a nonempty experimental design is required")
    dataset = Dataset(manifest.parent, manifest_sha256=digest(manifest))
    examples = dataset.examples(
        spec["split"], cutoff=spec["cutoff"], feature_fields=["memory"]
    )
    if not examples or len(examples) > 10000:
        raise LabError("campaign requires 1-10000 examples")
    for example in examples:
        if example["target"] is not None:
            raise LabError("this adapter accepts public diagnostic prefixes without labels")
        state(example["features"]["memory"])
    slots = spec["slots"]
    if not isinstance(slots, list) or not 2 <= len(slots) <= 64:
        raise LabError("declare 2-64 arm/seed slots")
    ids, cells, arms, seeds, files = set(), set(), set(), set(), {spec["design"]}
    data_files = {
        spec["dataset"] + "/" + filename
        for filename in ("manifest.json", "train.jsonl", "validation.jsonl", "test.jsonl")
    }
    files.update(data_files)
    for slot in slots:
        if (
            not isinstance(slot, dict) or set(slot) != {"id", "arm", "seed", "recipe"}
            or not _id(slot["id"]) or not _id(slot["arm"])
            or type(slot["seed"]) is not int or not 0 <= slot["seed"] < 2**32
        ):
            raise LabError("invalid campaign slot")
        cell = (slot["arm"], slot["seed"])
        if slot["id"] in ids or cell in cells:
            raise LabError("duplicate slot or arm/seed")
        ids.add(slot["id"])
        cells.add(cell)
        arms.add(slot["arm"])
        seeds.add(slot["seed"])
        recipe_path = contained_file(directory, slot["recipe"])
        if recipe_path.parent != directory:
            raise LabError("recipes must share the campaign source directory")
        recipe = load_config(recipe_path)
        if (
            recipe["seed"] != slot["seed"]
            or recipe["split_identity"] != dataset.manifest_sha256
            or recipe["source_kind"] != "CONSTRUCTED"
            or PREDICTIONS not in recipe["artifacts"]
            or not data_files <= set(recipe["inputs"])
            or spec["design"] not in recipe["inputs"]
        ):
            raise LabError("recipe must bind seed, Forge release, design and predictions")
        files.add(slot["recipe"])
        files.update(recipe["inputs"])
    if len(arms) < 2 or cells != {(arm, seed) for arm in arms for seed in seeds}:
        raise LabError("all arms must declare the same seed grid")
    hashes = {name: digest(contained_file(directory, name)) for name in sorted(files)}
    return dataset, examples, hashes


def prepare(spec_path: Path, root: Path):
    """Archive declared source/data/checkpoint files before any command executes."""
    source = spec_path.absolute().parent
    spec = read_json(contained_file(source, spec_path.name))
    _, _, hashes = _spec(spec, source)
    if root.exists() or root.is_symlink():
        raise LabError("campaign output must be new")
    root.mkdir(parents=True)
    directory = root / "inputs"
    directory.mkdir()
    for name, expected in hashes.items():
        destination = directory / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(contained_file(source, name), destination)
        if digest(destination) != expected:
            raise LabError("input changed during archival")
    protocol = {
        "schema": SCHEMA, "spec": spec, "input_sha256": hashes, "runtime": _runtime()
    }
    write_json(root / "protocol.json", protocol)
    return {"protocol_sha256": digest(root / "protocol.json"), "slots": len(spec["slots"])}


def _load(root, protocol_sha256):
    if digest(contained_file(root, "protocol.json")) != protocol_sha256:
        raise LabError("protocol differs from independently retained preparation pin")
    protocol = read_json(root / "protocol.json")
    if (
        not isinstance(protocol, dict)
        or set(protocol) != {"schema", "spec", "input_sha256", "runtime"}
        or protocol["schema"] != SCHEMA or protocol["runtime"] != _runtime()
    ):
        raise LabError("unsupported protocol or changed installed runtime")
    dataset, examples, hashes = _spec(protocol["spec"], root / "inputs")
    if hashes != protocol["input_sha256"]:
        raise LabError("archived inputs changed")
    return protocol, dataset, examples


def _attempt(root, slot, examples):
    directory = root / "runs" / slot["id"]
    if directory.exists() and (not directory.is_dir() or directory.is_symlink()):
        return {"status": "INVALID", "reason": "INVALID_ATTEMPT_DIRECTORY"}
    attempts = sorted(directory.iterdir()) if directory.exists() else []
    if not attempts:
        return {"status": "MISSING"}
    if len(attempts) != 1:
        return {"status": "INVALID", "reason": "MULTIPLE_ATTEMPTS_REQUIRE_NEW_CAMPAIGN"}
    run_dir = attempts[0]
    try:
        record = read_json(contained_file(run_dir, "run.json"))
        if record.get("status") == "running":
            return {"status": "UNFINISHED", "reason": "NO_FINALIZED_RECEIPT"}
        if not verify_run(run_dir)["valid"]:
            raise LabError("receipt integrity")
        recipe = load_config(contained_file(root / "inputs", slot["recipe"]))
        saved = load_config(contained_file(run_dir, "experiment.json"))
        if saved != recipe or record["id"] != run_dir.name:
            raise LabError("saved recipe or run identity")
        for record_key, config_key in (
            ("name", "name"), ("description", "description"), ("command", "command"),
            ("seed", "seed"), ("source_kind", "source_kind"),
            ("split_identity", "split_identity"), ("budget", "budget"),
            ("metric_directions", "metrics"),
        ):
            if record[record_key] != recipe[config_key]:
                raise LabError("run metadata binding")
        expected_inputs = {
            name: digest(contained_file(root / "inputs", name)) for name in recipe["inputs"]
        }
        if record["inputs"] != expected_inputs:
            raise LabError("run input binding")
        result = {
            "status": record["status"].upper(),
            "run_id": record["id"], "receipt_sha256": digest(run_dir / "run.json"),
            "process_wall_seconds": record["elapsed_seconds"],
            "cost_scope": "WHOLE_COMMAND_NOT_INFERENCE_COST",
        }
        if record["status"] == "succeeded":
            payload = read_json(contained_file(run_dir, "output/" + PREDICTIONS))
            if (
                not isinstance(payload, dict) or set(payload) != {"predictions"}
            ):
                raise LabError("prediction artifact schema")
            result["metrics"] = score(examples, payload["predictions"])
            result["predictions_sha256"] = record["artifacts"][PREDICTIONS]
        return result
    except (OSError, ValueError, KeyError, TypeError):
        # Keep unsafe receipt fields and local exception paths out of summaries.
        return {"status": "INVALID", "reason": "RECEIPT_OR_PREDICTION_VALIDATION_FAILED"}


def assess(root: Path, protocol_sha256: str):
    protocol, dataset, examples = _load(root, protocol_sha256)
    slots = {
        slot["id"]: {
            "arm": slot["arm"], "seed": slot["seed"],
            **_attempt(root, slot, examples),
        }
        for slot in protocol["spec"]["slots"]
    }
    declared = set(slots)
    runs = root / "runs"
    unexpected = runs.exists() and any(path.name not in declared for path in runs.iterdir())
    complete = not unexpected and all(item["status"] == "SUCCEEDED" for item in slots.values())
    return {
        "schema": SCHEMA, "protocol_sha256": protocol_sha256,
        "dataset_manifest_sha256": dataset.manifest_sha256,
        "split": protocol["spec"]["split"], "examples": len(examples),
        "slots": slots, "unexpected_run_directories": bool(unexpected),
        "execution": "COMPLETE" if complete else "INCOMPLETE",
        "scientific_qualification": "NOT_QUALIFIED",
        "frontier_qualification": "NOT_YET_FRONTIER_QUALIFIED",
        "inference_cost": "NOT_MEASURED",
        "matched_supervision_and_compute": "DESIGN_REVIEW_REQUIRED",
        "independent_review": "NOT_ESTABLISHED",
    }


def _envelope(root, report):
    timestamps = [
        read_json(root / "runs" / slot_id / result["run_id"] / "run.json")["finished_at"]
        for slot_id, result in report["slots"].items() if "run_id" in result
    ]
    if not timestamps:
        return None
    protocol = read_json(root / "protocol.json")
    record = EvidenceRecord(
        evidence_type="ecosystem.public_memory_campaign",
        outcome=EvidenceOutcome.OBSERVED,
        visibility=EvidenceVisibility.PUBLIC,
        claim="Public diagnostic campaign observations; no scientific qualification.",
        subjects=(
            EvidenceSubjectRef(
                kind="protocol", subject_id="public-memory-campaign",
                content_sha256=report["protocol_sha256"],
            ),
            EvidenceSubjectRef(
                kind="dataset", subject_id="public-memory-prefixes",
                content_sha256=report["dataset_manifest_sha256"],
            ),
        ),
        producer=EvidenceProducerRef(
            producer_id="veritas-memory-scorer", producer_version="1",
            content_sha256=protocol["runtime"]["source_trees"]["investigation_world"],
        ),
        artifacts=(
            EvidenceArtifactRef(
                artifact_id="memory-campaign-report", role="domain_report",
                content_sha256=digest(root / "reports" / (_sha(report) + ".json")),
                media_type="application/json",
            ),
        ),
        observed_at=max(datetime.fromisoformat(value) for value in timestamps),
        provenance={"scope": "PUBLIC_CONSTRUCTED", "review": "NOT_EXTERNALLY_REVIEWED"},
    )
    return record.model_dump(mode="json")


def run(root: Path, protocol_sha256: str):
    """Execute each missing slot once; never silently retry a failed seed."""
    protocol, _, _ = _load(root, protocol_sha256)
    for slot in protocol["spec"]["slots"]:
        destination = root / "runs" / slot["id"]
        if destination.exists():
            continue
        # Recheck snapshots between arms; trusted commands share the local account.
        _load(root, protocol_sha256)
        run_experiment(contained_file(root / "inputs", slot["recipe"]), destination)
    report = assess(root, protocol_sha256)
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    report_id = _sha(report)
    report_path = reports / (report_id + ".json")
    write_json(report_path, report)
    write_json(root / "report.json", report)
    lab = Controller(root / "research_lab")
    dataset_id = report["dataset_manifest_sha256"]
    import_forge(lab, root / "inputs" / protocol["spec"]["dataset"], dataset_id)
    finding = "memory." + report_id[:24]
    put_node(lab, finding, "finding", report)
    envelope = _envelope(root, report)
    write_json(root / "evidence.json", {"record": envelope})
    if envelope is not None:
        node = "memory-evidence." + report_id[:24]
        put_node(lab, node, "evidence", envelope)
        link(lab, finding, "derived_from", node)
    link(lab, finding, "derived_from", "forge." + dataset_id[:24])
    for slot_id, result in report["slots"].items():
        if "run_id" in result:
            directory = root / "runs" / slot_id / result["run_id"]
            import_trainlab(lab, directory)
            link(lab, finding, "derived_from", "trainlab." + result["run_id"])
    return report


def verify(root: Path, protocol_sha256: str):
    """Read-only rescoring: no recipe commands and no evidence graph writes."""
    report = assess(root, protocol_sha256)
    if read_json(contained_file(root, "report.json")) != report:
        raise LabError("saved report differs from recomputed campaign")
    archived = contained_file(root, "reports/" + _sha(report) + ".json")
    if read_json(archived) != report:
        raise LabError("archived report differs from recomputed campaign")
    if read_json(contained_file(root, "evidence.json")) != {"record": _envelope(root, report)}:
        raise LabError("shared evidence differs from recomputed campaign")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("spec", type=Path)
    prepare_parser.add_argument("root", type=Path)
    for command in ("run", "assess", "verify"):
        child = commands.add_parser(command)
        child.add_argument("root", type=Path)
        child.add_argument("--protocol-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.spec, args.root)
        else:
            operation = {"run": run, "assess": assess, "verify": verify}[args.command]
            result = operation(args.root, args.protocol_sha256)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0 if args.command == "prepare" or result["execution"] == "COMPLETE" else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"memory campaign: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
