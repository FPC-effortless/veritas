"""Installed, account-free public baseline comparison; never scientific promotion."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from trainlab.runner import (
    LabError,
    contained_file,
    digest,
    list_runs,
    load_config,
    read_json,
    run_experiment,
    verify_run,
    write_json,
)

AGENTS = ("public_evidence_reference", "projection_trust")
CUTOFF = "2026-01-01T00:00:00Z"
SCHEMA = "veritas.ecosystem-comparison.v1"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _runtime():
    trees = {}
    for package in ("investigation_world", "forge_data", "trainlab", "research_lab"):
        spec = importlib.util.find_spec(package)
        if spec is None or spec.origin is None:
            raise LabError("install all four ecosystem packages from the same checkout")
        root = Path(spec.origin).parent
        trees[package] = _sha(
            {file.relative_to(root).as_posix(): digest(file) for file in sorted(root.rglob("*.py"))}
        )
    return {
        "python": sys.version.split()[0],
        "source_trees": trees,
        "packages": {
            name: importlib.metadata.version(name)
            for name in (
                "investigation-world",
                "forge-temporal-data",
                "trainlab-local",
                "research-lab-os",
                "pydantic",
            )
        },
        "scope": "PYTHON_SOURCE_TREES_AND_SELECTED_VERSIONS_NOT_FULL_OS_ATTESTATION",
    }


def _fixture(index):
    from investigation_world.companyworld import (
        CompanySystem,
        CompanyWorldEpisode,
        CompanyWorldOracle,
        CompanyWorldRecord,
        CompanyWorldTask,
        OperationalFactTarget,
    )

    family = index % 3
    system = (CompanySystem.WMS, CompanySystem.AUTH_SERVICE, CompanySystem.AP_WORKFLOW)[family]
    kind = ("SHIPMENT", "AUTHORITY", "SUPPLIER_INVOICE")[family]
    field = ("delivered_quantity", "approval_limit_usd", "duplicate_status")[family]
    task_type = (
        "INVESTIGATE_MISSING_SHIPMENT",
        "INVESTIGATE_AUTHORITY_BREACH",
        "INVESTIGATE_DUPLICATE_INVOICE",
    )[family]
    target = f"OBJECT-{index}"
    value = (index + 1, 1000 + index, "DUPLICATE")[family]
    direct = CompanyWorldRecord(
        record_id=f"SOURCE-{index}",
        system=system,
        record_type=("carrier_manifest", "policy_rule", "supplier_submission")[family],
        object_type=kind,
        object_id=target,
        fields={field: value}
        if family != 2
        else {"submission_kind": "resubmission", "submitted_reference": target},
        source_file="PUBLIC_CONSTRUCTED_FIXTURE",
        related_object_ids=[target],
    )
    projection = CompanyWorldRecord(
        record_id=f"PROJECTION-{index}",
        system=system,
        record_type="system_projection",
        object_type=kind,
        object_id=target,
        fields={field: "UNIQUE" if family == 2 else value + 100},
        source_file="PUBLIC_CONSTRUCTED_FIXTURE",
    )
    task = CompanyWorldTask(
        task_id=f"TASK-{index}",
        world_id="public-ecosystem-demo-v1",
        task_type=task_type,
        objective="Resolve a source/projection discrepancy using admissible evidence.",
        target_object_type=kind,
        target_object_id=target,
        permitted_systems=[system],
    )
    return CompanyWorldEpisode(
        episode_id=f"EPISODE-{index}",
        world_id=task.world_id,
        task=task,
        records=[direct, projection],
        oracle=CompanyWorldOracle(
            task_id=task.task_id,
            answer_class="PUBLIC_CONSTRUCTED",
            expected_resolution="Use source evidence.",
            facts=[
                OperationalFactTarget(
                    object_type=kind,
                    object_id=target,
                    field_name=field,
                    expected_value=value,
                    supporting_record_ids=[direct.record_id],
                )
            ],
        ),
    )


def _protocol(directory):
    protocol = read_json(contained_file(directory, "protocol.json"))
    if (
        set(protocol)
        != {
            "schema",
            "manifest_sha256",
            "expected_sha256",
            "driver_sha256",
            "runtime",
            "agents",
            "split",
            "cutoff",
            "seed",
        }
        or protocol["schema"] != "veritas.ecosystem-protocol.v1"
        or protocol["agents"] != list(AGENTS)
        or protocol["split"] != "validation"
        or protocol["cutoff"] != CUTOFF
        or protocol["seed"] != 7
        or protocol["runtime"] != _runtime()
        or protocol["driver_sha256"] != digest(Path(__file__))
    ):
        raise LabError("protocol or installed runtime differs from the frozen comparison")
    return protocol


def _examples(directory, protocol):
    from forge_data.dataset import Dataset

    dataset = Dataset(directory / "dataset", manifest_sha256=protocol["manifest_sha256"])
    rows = dataset.examples("validation", cutoff=CUTOFF, feature_fields=["episode"])
    payloads = [row["features"]["episode"] for row in rows]
    if (
        not payloads
        or any(row["target"] is not None for row in rows)
        or any(
            set(p) != {"episode_id", "world_id", "task", "records", "metadata"} for p in payloads
        )
    ):
        raise LabError("expected only public episode payloads without evaluator targets")
    return dataset, payloads


def _recipe(directory, agent, protocol, cases):
    return {
        "schema": "trainlab.experiment.v2",
        "name": agent,
        "description": "Public constructed scripted baseline; no trained weights or qualification.",
        "command": [sys.executable, "driver.py", "agent", agent],
        "seed": protocol["seed"],
        "timeout_seconds": 60,
        "source_kind": "CONSTRUCTED",
        "split_identity": protocol["manifest_sha256"],
        "inputs": [
            "driver.py",
            "protocol.json",
            *[
                "dataset/" + name
                for name in ("manifest.json", "train.jsonl", "validation.jsonl", "test.jsonl")
            ],
        ],
        "artifacts": ["predictions.json"],
        "metrics": {"submission_count": "max"},
        "budget": {"agent_invocations": cases, "trained_parameters": 0, "tuning_trials": 0},
        "workload": {"kind": "test", "training_method": None, "execution": "single_process"},
        "checks": {"submission_count": {"min": cases, "max": cases}},
    }


def agent(name):
    import os

    from investigation_world.benchmark.policies import (
        ProjectionTrustPolicy,
        PublicEvidenceReferencePolicy,
    )

    directory = Path.cwd()
    protocol = _protocol(directory)
    _, payloads = _examples(directory, protocol)
    policy = PublicEvidenceReferencePolicy() if name == AGENTS[0] else ProjectionTrustPolicy()
    predictions = {
        payload["episode_id"]: policy(payload).model_dump(mode="json") for payload in payloads
    }
    _protocol(directory)  # Source/runtime changes during execution invalidate the result.
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    write_json(output / "predictions.json", {"agent": name, "predictions": predictions})
    write_json(output / "metrics.json", {"submission_count": len(predictions)})


def _assess(root):
    from investigation_world.benchmark.policies import EmptyPolicy, PublicEvidenceReferencePolicy
    from investigation_world.companyworld import CompanyWorldEpisode, verifier
    from investigation_world.core.models import InvestigationResult

    directory = root / "agents"
    protocol = _protocol(directory)
    dataset, payloads = _examples(directory, protocol)
    expected_path = contained_file(root, "operator/episodes.json")
    if digest(expected_path) != protocol["expected_sha256"]:
        raise LabError("evaluator fixture changed")
    episodes = [CompanyWorldEpisode.model_validate(value) for value in read_json(expected_path)]
    expected = {episode.episode_id: episode for episode in episodes}
    for payload in payloads:
        episode = expected[payload["episode_id"]]
        if episode.public_payload() != payload:
            raise LabError("public/evaluator episode binding differs")
        if (
            verifier.verify_companyworld(EmptyPolicy()(payload), episode).overall_reward != 0
            or verifier.verify_companyworld(
                PublicEvidenceReferencePolicy()(payload), episode
            ).overall_reward
            != 1
        ):
            raise LabError("constructed positive/negative verifier controls failed")
    runs = list_runs(root / "runs")
    if len(runs) != 2 or {run["name"] for run in runs} != set(AGENTS):
        raise LabError("comparison requires exactly the two declared baseline runs")
    results = {}
    for run_record in runs:
        run_directory = root / "runs" / run_record["id"]
        if run_record["status"] != "succeeded" or not verify_run(run_directory)["valid"]:
            raise LabError("run execution or artifact integrity failed")
        recipe = _recipe(directory, run_record["name"], protocol, len(payloads))
        if load_config(contained_file(run_directory, "experiment.json")) != recipe:
            raise LabError("saved recipe differs from comparison protocol")
        for record_key, config_key in (
            ("name", "name"),
            ("description", "description"),
            ("command", "command"),
            ("seed", "seed"),
            ("source_kind", "source_kind"),
            ("split_identity", "split_identity"),
            ("budget", "budget"),
            ("metric_directions", "metrics"),
        ):
            if run_record[record_key] != recipe[config_key]:
                raise LabError("run metadata differs from saved recipe")
        if run_record["inputs"] != {
            name: digest(contained_file(directory, name)) for name in recipe["inputs"]
        }:
            raise LabError("declared inputs changed after execution")
        submitted = read_json(contained_file(run_directory, "output/predictions.json"))
        if set(submitted) != {"agent", "predictions"} or submitted["agent"] != run_record["name"]:
            raise LabError("prediction producer differs from declared agent")
        predictions = submitted["predictions"]
        if set(predictions) != {p["episode_id"] for p in payloads}:
            raise LabError("missing or unexpected submissions")
        rewards = [
            verifier.verify_companyworld(
                InvestigationResult.model_validate(predictions[p["episode_id"]]),
                expected[p["episode_id"]],
            ).overall_reward
            for p in payloads
        ]
        results[run_record["name"]] = {
            "run_id": run_record["id"],
            "receipt_sha256": digest(run_directory / "run.json"),
            "predictions_sha256": run_record["artifacts"]["predictions.json"],
            "mean_reward": sum(rewards) / len(rewards),
            "cases": len(rewards),
            "elapsed_seconds": run_record["elapsed_seconds"],
        }
    _protocol(directory)
    return {
        "schema": SCHEMA,
        "source_kind": "CONSTRUCTED",
        "dataset": {"manifest_sha256": protocol["manifest_sha256"], **dataset.summary()},
        "code_environment": protocol["runtime"],
        "models": {name: {"kind": "SCRIPTED_PUBLIC_POLICY", "checkpoint": None} for name in AGENTS},
        "training": {"status": "NOT_PERFORMED", "compute_scope": "PROCESS_WALL_TIME_ONLY"},
        "protocol_sha256": digest(directory / "protocol.json"),
        "results": results,
        "verification": {
            "producer": "verify_companyworld",
            "controls": "PASS_CONSTRUCTED",
            "split": "validation",
            "test_scoring": "NOT_PERFORMED",
            "independence": "SCORER_SEPARATE_FROM_AGENT_PROCESSES_NOT_EXTERNAL_REVIEW",
        },
        "promotion": {
            "decision": "NOT_PROMOTED",
            "scientific_qualification": "NOT_QUALIFIED",
            "reason": "PUBLIC_CONSTRUCTED_BASELINE_COMPARISON_ONLY",
        },
    }


def _envelope(root, report):
    from investigation_world.evidence import (
        EvidenceArtifactRef,
        EvidenceOutcome,
        EvidenceProducerRef,
        EvidenceRecord,
        EvidenceSubjectRef,
        EvidenceVisibility,
    )

    protocol = _protocol(root / "agents")
    observed = max(read_json(path)["finished_at"] for path in (root / "runs").glob("*/run.json"))
    record = EvidenceRecord(
        evidence_type="ecosystem.public_baseline_comparison",
        outcome=EvidenceOutcome.OBSERVED,
        visibility=EvidenceVisibility.PUBLIC,
        claim=(
            "Constructed scripted-baseline comparison. "
            "Scientific qualification and promotion are not established."
        ),
        subjects=(
            EvidenceSubjectRef(
                kind="dataset",
                subject_id="public-ecosystem-dataset-v1",
                content_sha256=protocol["manifest_sha256"],
            ),
            EvidenceSubjectRef(
                kind="protocol",
                subject_id="public-ecosystem-protocol-v1",
                content_sha256=report["protocol_sha256"],
            ),
            EvidenceSubjectRef(
                kind="verifier",
                subject_id="companyworld-verifier-source-tree",
                content_sha256=protocol["runtime"]["source_trees"]["investigation_world"],
            ),
        ),
        producer=EvidenceProducerRef(
            producer_id="public-ecosystem-demo",
            producer_version="1",
            content_sha256=protocol["driver_sha256"],
        ),
        artifacts=(
            EvidenceArtifactRef(
                artifact_id="public-ecosystem-comparison",
                role="domain_report",
                content_sha256=digest(contained_file(root, "comparison.json")),
                media_type="application/json",
            ),
        ),
        observed_at=datetime.fromisoformat(observed),
        provenance={"scope": "PUBLIC_CONSTRUCTED", "review": "NOT_EXTERNALLY_REVIEWED"},
    )
    return record.model_dump(mode="json")


def verify(root: Path):
    root = root.resolve()
    report = _assess(root)
    if read_json(contained_file(root, "comparison.json")) != report or read_json(
        contained_file(root, "evidence.json")
    ) != _envelope(root, report):
        raise LabError("stored report/evidence differs from reverified results")
    return report


def run(root: Path):
    from forge_data.core import canonical, release

    from .adapters import import_forge, import_trainlab
    from .core import Controller
    from .evidence import link, put_node

    if root.exists() or root.is_symlink():
        raise LabError("comparison output must be a new directory")
    root.mkdir(parents=True)
    root = root.resolve()
    directory = root / "agents"
    directory.mkdir()
    (root / "operator").mkdir()
    episodes = [_fixture(index) for index in range(30)]
    write_json(root / "operator/episodes.json", [e.model_dump(mode="json") for e in episodes])
    spec = {
        "dataset_id": "public-ecosystem-fixture-v1",
        "source_id": "fixture/companyworld",
        "source_version": "v1",
        "adapter": "operations-jsonl",
        "license_id": "Apache-2.0",
        "provenance_uri": "https://github.com/FPC-effortless/veritas",
        "ai_use_allowed": True,
        "redistribution_allowed": True,
        "privacy_reviewed": True,
        "split_salt": "public-ecosystem-fixed-v1",
    }
    write_json(root / "source.json", spec)
    rows = [
        {
            "episode_id": e.episode_id,
            "subject_id": f"subject-{i}",
            "record_id": e.episode_id,
            "observed_at": CUTOFF,
            "available_at": CUTOFF,
            "observation": {"episode": e.public_payload()},
            "action": None,
            "outcome": {"status": "unknown", "verified": False},
        }
        for i, e in enumerate(episodes)
    ]
    (root / "source.jsonl").write_bytes(b"".join(canonical(row) for row in rows))
    release(root / "source.jsonl", root / "source.json", directory / "dataset")
    shutil.copyfile(__file__, directory / "driver.py")
    protocol = {
        "schema": "veritas.ecosystem-protocol.v1",
        "manifest_sha256": digest(directory / "dataset/manifest.json"),
        "expected_sha256": digest(root / "operator/episodes.json"),
        "driver_sha256": digest(Path(__file__)),
        "runtime": _runtime(),
        "agents": list(AGENTS),
        "split": "validation",
        "cutoff": CUTOFF,
        "seed": 7,
    }
    write_json(directory / "protocol.json", protocol)
    dataset, payloads = _examples(directory, protocol)
    for name in AGENTS:
        path = directory / (name + ".json")
        write_json(path, _recipe(directory, name, protocol, len(payloads)))
        result = run_experiment(path, root / "runs")
        if result["status"] != "succeeded":
            raise LabError("baseline execution failed; inspect retained local run logs")
    report = _assess(root)
    write_json(root / "comparison.json", report)
    write_json(root / "evidence.json", _envelope(root, report))
    lab = Controller(root / "research_lab")
    import_forge(lab, directory / "dataset", dataset.manifest_sha256)
    for path in (root / "runs").glob("*"):
        import_trainlab(lab, path)
    finding = "comparison." + _sha(report)[:24]
    put_node(lab, finding, "finding", report)
    for record in report["results"].values():
        link(lab, finding, "derived_from", "trainlab." + record["run_id"])
    return verify(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "verify"):
        commands.add_parser(command).add_argument("directory", type=Path)
    commands.add_parser("agent").add_argument("name", choices=AGENTS)
    args = parser.parse_args()
    try:
        if args.command == "agent":
            agent(args.name)
            return 0
        result = run(args.directory) if args.command == "run" else verify(args.directory)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(2, f"ecosystem: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
