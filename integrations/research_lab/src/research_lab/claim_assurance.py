"""Measured, replayed and authenticated scoped claims; never frontier qualification.

Uses existing Research Lab replay/synthesis and TrainLab capture/bundle contracts.
The key trust list is supplied by the recipient, never inferred from a signature.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from trainlab.diagnostic_bundle import create
from trainlab.prediction_artifacts import _bytes
from trainlab.runner import contained_file, digest, load_config, read_json, write_json

from .core import LabError, identity
from .evidence import put_node, synthesize
from .execution import _run, validate_completion


def _require(condition, message):
    if not condition:
        raise LabError(message)


def _captured_run(lab, task_id, run_id):
    from trainlab.adequacy_capture import verify_capture

    run = _run(lab, run_id)
    _require(
        run.get("execution_purpose") == "research"
        and run.get("research_adequacy") == "EXECUTED_CRITERIA_MET"
        and run.get("claim_eligibility") == "DECLARED_CONDITIONS_ONLY",
        "claim requires reconciled research execution, not diagnostics or historical replay",
    )
    directory = lab.root / "runs" / run_id
    config = load_config(contained_file(directory, "experiment.json"))
    plan = read_json(contained_file(directory, "research_adequacy.json"))
    contract = plan["contract"]
    capture = contract.get("capture")
    _require(
        type(capture) is dict
        and set(capture) == {"artifact", "adapter", "metric"}
        and capture["adapter"] == "pytorch_cpu_classification_v1"
        and capture["artifact"] in run["artifacts"],
        "supported measured capture is required for claim promotion",
    )
    report = read_json(
        contained_file(directory, "output/" + capture["artifact"]), limit=16 * 1024 * 1024
    )
    receipt = read_json(contained_file(directory, "output/" + contract["execution"]["artifact"]))
    verification = verify_capture(report, receipt, config, run["inputs"])
    _require(
        verification.get("valid") is True and verification.get("admissible") == 1,
        "measured capture did not verify",
    )
    _require(
        capture["metric"] == "accuracy"
        and run["metrics"].get("accuracy") == verification["metrics"].get("accuracy"),
        "claim metric must match rescored predictions",
    )
    materials = {}
    for label, path in {
        "run.json": directory / "run.json",
        "experiment.json": directory / "experiment.json",
        "capture.json": directory / "output" / capture["artifact"],
        "execution_adequacy.json": directory / "execution_adequacy.json",
        "plan.json": directory / "research_adequacy.json",
    }.items():
        with path.open("rb") as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        materials[run_id + "/" + label] = raw
    materials[run_id + "/contract.json"] = plan["source_texts"][
        config["research_adequacy"]["file"]
    ].encode()
    for relative, expected in {
        **run["files"],
        **{"output/" + name: pin for name, pin in run["artifacts"].items()},
    }.items():
        with contained_file(directory, relative).open("rb") as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        _require(hashlib.sha256(raw).hexdigest() == expected, "run review material changed")
        materials[run_id + "/" + relative] = raw
    return (
        {
            "task_id": task_id,
            "run_id": run_id,
            "record_sha256": digest(directory / "run.json"),
            "contract_sha256": config["research_adequacy"]["sha256"],
            "capture_sha256": run["artifacts"][capture["artifact"]],
            "execution_sha256": run["files"]["execution_adequacy.json"],
        },
        verification["replay_sha256"],
        materials,
    )


def claim_evidence(lab, protocol_id):
    """Recompute every expected primary/replay; no best-seed or partial-coverage promotion."""
    p = lab.protocol(protocol_id)
    _require(p["metric"] == "accuracy", "only measured classification accuracy is supported")
    summary = synthesize(lab, protocol_id)
    _require(
        summary["conclusion"] in ("BOUNDED_CONTRAST_SUPPORTED", "BOUNDED_CONTRAST_NOT_SUPPORTED")
        and summary["evidence_pin"] is not None,
        "claim prerequisites incomplete or invalid",
    )
    tasks = [x for x in lab.status()["tasks"] if x["protocol"] == protocol_id]
    primary = sorted((x for x in tasks if x["role"] == "experiment"), key=lambda x: x["id"])
    replicas = [x for x in tasks if x["role"] == "replication"]
    _require(
        len(replicas) == 1 and len(primary) == 2 * len(p["seeds"]),
        "complete candidate/control seed population required",
    )
    replica = replicas[0]
    validate_completion(lab, replica, replica["result"])
    _require(
        replica["status"] == "succeeded" and replica["result"]["all_match"],
        "fresh replay must agree",
    )
    rows = []
    materials = {}
    material_bytes = 0

    def retain(name, raw):
        nonlocal material_bytes
        material_bytes += len(raw)
        _require(material_bytes <= 8 * 1024 * 1024, "offline review materials exceed 8 MiB")
        materials[name] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "base64": base64.b64encode(raw).decode("ascii"),
        }

    for task in primary:
        validate_completion(lab, task, task["result"])
        original, original_projection, original_materials = _captured_run(
            lab, task["id"], task["result"]["run_id"]
        )
        replay_id = replica["result"]["replays"][task["id"]]["run_id"]
        replay, replay_projection, replay_materials = _captured_run(
            lab, task["id"] + ".replay", replay_id
        )
        _require(
            original_projection == replay_projection,
            "measured primary/replay capture differs despite declared metric agreement",
        )
        rows.extend((original, replay))
        for name, raw in {**original_materials, **replay_materials}.items():
            retain(name, raw)
    _require(
        len({row["run_id"] for row in rows}) == len(rows),
        "primary/replay executions must have distinct retained run identities",
    )
    snapshot = lab.snapshot(protocol_id)
    manifest = read_json(contained_file(snapshot, "snapshot.json"))
    for name in [*manifest, "snapshot.json"]:
        with contained_file(snapshot, name).open("rb") as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        if name != "snapshot.json":
            _require(hashlib.sha256(raw).hexdigest() == manifest[name], "snapshot material changed")
        retain("source/" + name, raw)
    _require(synthesize(lab, protocol_id) == summary, "claim evidence changed during preparation")
    return {
        "schema": "research_lab.claim-assurance.v1",
        "status": "TESTED",
        "claim": {
            "protocol_id": protocol_id,
            "protocol_sha256": identity(p),
            "scope": p["scope"],
            "metric": p["metric"],
            "direction": p["direction"],
            "minimum_effect": p["minimum_effect"],
            "seeds": p["seeds"],
            "conclusion": summary["conclusion"],
            "evaluation_scope": "TRAIN_ONLY_OBSERVED_CLASSIFICATION",
        },
        "evidence_pin": summary["evidence_pin"],
        "synthesis": summary,
        "runs": rows,
        "review_materials": materials,
        "replay_scope": "CLEAN_DIRECTORY_SAME_HOST_AND_RUNTIME",
        "author": p["author"],
        "scientific_qualification": "NOT_QUALIFIED",
    }


def prepare_claim_review(lab, protocol_id, destination, *, data_classification):
    """Prepare sensitive local review material; does not sanitize, sign or publish it."""
    destination = Path(destination)
    _require(
        data_classification in ("PUBLIC_AUTHORIZED", "CONSTRUCTED_PUBLIC"),
        "explicit authorized bundle data classification required",
    )
    _require(not destination.exists(), "new review destination required")
    evidence = claim_evidence(lab, protocol_id)
    raw = _bytes(evidence)
    pin = hashlib.sha256(raw).hexdigest()
    destination.mkdir(parents=True, mode=0o700)
    (destination / "assurance.json").write_bytes(raw)
    spec = {
        "schema": "trainlab.diagnostic-bundle-spec.v1",
        "title": "Scoped research claim review",
        "data_classification": data_classification,
        "packs": [
            {
                "id": "research-assurance",
                "version": "1",
                "applicability": "Measured replayed exact scoped claim",
                "dependencies": ["TrainLab", "Research Lab"],
                "cost": "bounded local checks",
                "evidence_requirements": ["exact claim, capture, execution and replay identities"],
                "limitations": ["not scientific qualification or external replication"],
            }
        ],
        "findings": [
            {
                "id": "research-assurance",
                "pack_id": "research-assurance",
                "kind": "conclusion",
                "summary": evidence["claim"]["conclusion"],
                "status": "TESTED",
                "reviews": [],
                "evidence": {"path": "assurance.json", "sha256": pin, "pointer": []},
            }
        ],
    }
    write_json(destination / "spec.json", spec)
    manifest = create(
        destination / "spec.json", digest(destination / "spec.json"), destination / "bundle"
    )
    return {
        "bundle": str(destination / "bundle"),
        "manifest_sha256": manifest,
        "evidence_sha256": pin,
        "claim_promotion": "PENDING_AUTHENTICATED_REVIEW",
        "scientific_qualification": "NOT_QUALIFIED",
    }


def verify_claim_review(
    lab,
    protocol_id,
    root,
    manifest_sha256,
    envelope_path,
    *,
    signer,
    trusted_signers,
    trusted_signers_sha256,
):
    """Fresh evidence + current independently supplied trust policy; never cached acceptance."""
    from trainlab.assurance_review import verify_assurance_review

    evidence = claim_evidence(lab, protocol_id)
    pin = hashlib.sha256(_bytes(evidence)).hexdigest()
    review = verify_assurance_review(
        root,
        manifest_sha256,
        envelope_path,
        signer=signer,
        trusted_signers=trusted_signers,
        trusted_signers_sha256=trusted_signers_sha256,
        author=evidence["author"],
        expected_evidence_sha256=pin,
    )
    _require(
        review["status"] == "AUTHENTICATED_ACCEPT", "explicit authenticated acceptance required"
    )
    return {
        "schema": "research_lab.claim-promotion.v1",
        "status": "SCOPED_CLAIM_REVIEWED",
        "claim": evidence["claim"],
        "evidence_sha256": pin,
        "review": review,
        "scientific_qualification": "NOT_QUALIFIED",
        "external_replication": "NOT_PERFORMED",
        "publication_authorization": "NOT_GRANTED",
    }


def promote_claim(
    lab,
    protocol_id,
    root,
    manifest_sha256,
    envelope_path,
    *,
    signer,
    trusted_signers,
    trusted_signers_sha256,
):
    """Record an immutable scoped decision only after recomputing all prerequisites."""
    report = verify_claim_review(
        lab,
        protocol_id,
        root,
        manifest_sha256,
        envelope_path,
        signer=signer,
        trusted_signers=trusted_signers,
        trusted_signers_sha256=trusted_signers_sha256,
    )
    # The node is an audit record, not a perpetual authorization; consumers must
    # call verify_claim_review with current evidence/trust before relying on it.
    node = "claim." + identity(report)
    put_node(lab, node, "finding", report)
    return {**report, "node": node}
