"""Research graph, conservative synthesis, receipts and publication preparation."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

from trainlab.runner import contained_file, digest, read_json, verify_run, write_json

from .core import LabError, canonical, identity, name, text_list


def put_node(lab, node_id, kind, body, *, db=None):
    if db is None:
        with lab.transaction() as transaction:
            return put_node(lab, node_id, kind, body, db=transaction)
    name(node_id)
    if kind not in {
        "objective",
        "proposal",
        "hypothesis",
        "experiment",
        "evidence",
        "finding",
        "paper",
        "failure",
        "next_test",
    }:
        raise LabError("unknown research node kind")
    payload = canonical(body)
    if not isinstance(body, dict) or len(payload.encode()) > 1024 * 1024:
        raise LabError("research node must be a bounded object")
    pin = identity({"kind": kind, "body": body})
    prior = db.execute("SELECT pin FROM nodes WHERE id=?", (node_id,)).fetchone()
    if prior and prior[0] != pin:
        raise LabError("research nodes are immutable; create a revision and supersedes link")
    if prior:
        return pin
    db.execute("INSERT OR IGNORE INTO nodes VALUES (?,?,?,?)", (node_id, kind, payload, pin))
    lab._event(db, "knowledge_recorded", {"id": node_id, "kind": kind, "pin": pin})
    return pin


def link(lab, source, relation, target, *, db=None):
    if db is None:
        with lab.transaction() as transaction:
            return link(lab, source, relation, target, db=transaction)
    if relation not in {
        "supports",
        "contradicts",
        "tests",
        "replicates",
        "supersedes",
        "derived_from",
        "next",
    }:
        raise LabError("unsupported research relation")
    db.execute("INSERT OR IGNORE INTO links VALUES (?,?,?)", (source, relation, target))
    lab._event(db, "knowledge_linked", {"source": source, "relation": relation, "target": target})


def retrieve(lab, query=""):
    if not isinstance(query, str) or len(query) > 1000:
        raise LabError("bounded knowledge query required")
    # Native LIKE supports exact keyword retrieval without another embedding store.
    pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with lab.connect() as db:
        nodes = [
            dict(r)
            for r in db.execute(
                (
                    "SELECT * FROM nodes WHERE id LIKE ? ESCAPE '\\' OR body LIKE ? "
                    "ESCAPE '\\' LIMIT 200"
                ),
                (pattern, pattern),
            )
        ]
        links = [dict(r) for r in db.execute("SELECT * FROM links")]
    for node in nodes:
        node["body"] = json.loads(node["body"])
    ids = {x["id"] for x in nodes}
    return {
        "nodes": nodes,
        "links": [x for x in links if x["source"] in ids or x["target"] in ids],
        "retrieval_scope": "BOUNDED_LITERAL_RETRIEVAL",
        "novelty": "NOT_ESTABLISHED",
    }


def validate_proposal(proposal):
    fields = {
        "schema",
        "id",
        "author",
        "question",
        "hypothesis",
        "competing_explanations",
        "predictions",
        "controls",
        "ablations",
        "primary_metric",
        "direction",
        "minimum_effect",
        "seeds",
        "stopping_rule",
        "limitations",
        "next_discriminating_test",
    }
    if (
        not isinstance(proposal, dict)
        or set(proposal) not in (fields, fields | {"execution"})
        or proposal["schema"] != "research_lab.proposal.v1"
    ):
        raise LabError("unsupported proposal schema")
    if "execution" in proposal:
        execution = proposal["execution"]
        if not isinstance(execution, dict) or set(execution) != {"profile"}:
            raise LabError("proposal execution may select only an admitted profile")
        name(execution["profile"])
    for key in ("controls", "ablations", "limitations", "competing_explanations", "predictions"):
        text_list(
            proposal[key], minimum=2 if key in ("predictions", "competing_explanations") else 1
        )
    name(proposal["id"])
    name(proposal["author"])
    for key in (
        "question",
        "hypothesis",
        "primary_metric",
        "stopping_rule",
        "next_discriminating_test",
    ):
        if (
            not isinstance(proposal[key], str)
            or not proposal[key].strip()
            or len(proposal[key]) > 8000
        ):
            raise LabError("proposal requires bounded scientific text")
    from .core import number

    number(proposal["minimum_effect"])
    if proposal["direction"] not in ("min", "max"):
        raise LabError("invalid proposal direction")
    if (
        not isinstance(proposal["seeds"], list)
        or len(proposal["seeds"]) < 3
        or any(type(s) is not int or not 0 <= s <= 2**32 - 1 for s in proposal["seeds"])
        or len(set(proposal["seeds"])) != len(proposal["seeds"])
    ):
        raise LabError("proposal needs distinct fixed seeds")
    return proposal


def ingest_proposal(lab, proposal, *, db=None):
    validate_proposal(proposal)
    return put_node(lab, "proposal." + proposal["id"], "proposal", proposal, db=db)


def direct(lab):
    """Transparent prioritization of supplied questions, not an invented scientist."""
    graph = retrieve(lab)
    proposals = [x for x in graph["nodes"] if x["kind"] == "proposal"]
    state = lab.status()
    # A discriminating proposal names alternatives, interventions and a stopping rule.
    # This heuristic ranks design completeness; it does not establish scientific value.
    rows = []
    for node in proposals:
        p = node["body"]
        rows.append(
            {
                "proposal": node["id"],
                "question": p["question"],
                "design_score": min(4, len(p["competing_explanations"]))
                + min(4, len(p["controls"]))
                + min(4, len(p["ablations"])),
                "next_test": p["next_discriminating_test"],
                "proposal_pin": node["pin"],
            }
        )
    return {
        "queue": sorted(rows, key=lambda x: (-x["design_score"], x["proposal"])),
        "programs": state["programs"],
        "decision_scope": "DESIGN_COMPLETENESS_HEURISTIC",
        "autonomous_scientific_reasoning": "NOT_ESTABLISHED",
    }


def synthesize(lab, protocol_id):
    from .execution import _run, evidence_pin, validate_completion

    p = lab.protocol(protocol_id)
    if p["schema"] != "research_lab.protocol.v1":
        raise LabError("agent work orders do not have a scientific contrast synthesis")
    tasks = [x for x in lab.status()["tasks"] if x["protocol"] == protocol_id]
    primary = [x for x in tasks if x["role"] == "experiment"]
    by_seed = {}
    errors = []
    try:
        with lab.connect() as db:
            lab._verify_snapshot(db, protocol_id)
    except (LabError, OSError, ValueError) as exc:
        errors.append(str(exc))
    for task in primary:
        if task["status"] != "succeeded":
            continue
        try:
            validate_completion(lab, task, task["result"])
            run = _run(lab, task["result"]["run_id"])
            arm = (
                "candidate" if task["id"] == f"{protocol_id}.candidate.{run['seed']}" else "control"
            )
            by_seed.setdefault(run["seed"], {})[arm] = run["metrics"][p["metric"]]
        except (LabError, OSError, ValueError) as exc:
            errors.append(str(exc))
    complete = all(set(by_seed.get(s, {})) == {"candidate", "control"} for s in p["seeds"])
    sign = 1 if p["direction"] == "max" else -1
    effects = [
        {
            "seed": s,
            **by_seed[s],
            "effect": sign * (by_seed[s]["candidate"] - by_seed[s]["control"]),
        }
        for s in p["seeds"]
        if set(by_seed.get(s, {})) == {"candidate", "control"}
    ]
    replica = next(x for x in tasks if x["role"] == "replication")
    review = next(x for x in tasks if x["role"] == "review")
    reviewed = False
    if review["status"] == "succeeded":
        try:
            validate_completion(lab, review, review["result"])
            reviewed = review["result"]["verdict"] == "clean"
        except (LabError, OSError, ValueError) as exc:
            errors.append(str(exc))
    replicated = False
    if replica["status"] == "succeeded":
        try:
            validate_completion(lab, replica, replica["result"])
            replicated = replica["result"]["all_match"]
        except (LabError, OSError, ValueError) as exc:
            errors.append(str(exc))
    if errors:
        conclusion = "INVALID_EVIDENCE"
    elif not complete:
        conclusion = "INCOMPLETE"
    elif not replicated:
        conclusion = "REPLICATION_PENDING_OR_DISAGREES"
    elif not reviewed:
        conclusion = "INDEPENDENT_REVIEW_PENDING_OR_BLOCKING"
    else:
        conclusion = (
            "BOUNDED_CONTRAST_SUPPORTED"
            if all(x["effect"] >= p["minimum_effect"] for x in effects)
            else "BOUNDED_CONTRAST_NOT_SUPPORTED"
        )
    return {
        "schema": "research_lab.synthesis.v1",
        "protocol": protocol_id,
        "protocol_pin": identity(p),
        "scope": p["scope"],
        "conclusion": conclusion,
        "seed_effects": effects,
        "minimum_effect": p["minimum_effect"],
        "effect_range": [min(x["effect"] for x in effects), max(x["effect"] for x in effects)]
        if effects
        else None,
        "uncertainty": "DESCRIPTIVE_SEED_RANGE_ONLY; no pooled IID or universal guarantee",
        "reviewed": reviewed,
        "replicated": replicated,
        "errors": errors,
        "limitations": p["limitations"],
        "next_discriminating_test": p["next_test"],
        "scientific_qualification": "NOT_QUALIFIED",
        "publication_authorization": "NOT_GRANTED",
        "evidence_pin": evidence_pin(lab, protocol_id)
        if complete and replicated and not errors
        else None,
    }


def _prepare_packet(lab, protocol_id, destination):
    """Local operator packet; never submits or attests external publication."""
    destination = Path(destination)
    if destination.exists():
        raise LabError("publication destination must be new")
    summary = synthesize(lab, protocol_id)
    if summary["errors"]:
        raise LabError("invalid research evidence cannot be packaged as frozen inputs")
    destination.mkdir(parents=True, mode=0o700)
    write_json(destination / "synthesis.json", summary)
    source = lab.snapshot(protocol_id)
    inputs = read_json(contained_file(source, "snapshot.json"))
    for filename in [*inputs, "snapshot.json"]:
        target = destination / "frozen_inputs" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(contained_file(source, filename), target)
    with lab.connect() as db:
        lab._verify_snapshot(db, protocol_id, root=destination / "frozen_inputs")
    state = lab.status()
    tasks = [x for x in state["tasks"] if x["protocol"] == protocol_id]
    task_ids = {x["id"] for x in tasks}
    attempts = [x for x in state["attempts"] if x["task"] in task_ids]
    write_json(destination / "tasks.json", {"tasks": tasks})
    write_json(destination / "attempts.json", {"attempts": attempts})
    write_json(destination / "knowledge.json", retrieve(lab))
    run_ids = set()
    for item in [*tasks, *attempts]:
        for payload in (item["result"], item["checkpoint"]):
            for key in ("run_id", "active_run_id"):
                if key in payload:
                    run_ids.add(payload[key])
            for key in ("replays", "completed_replays"):
                run_ids.update(x["run_id"] for x in payload.get(key, {}).values())
    for run_id in sorted(run_ids):
        root = lab.root / "runs" / name(run_id)
        record = read_json(contained_file(root, "run.json"))
        if record["status"] == "running":
            raise LabError(
                "a linked execution is still unfinished; preserve the store before packaging"
            )
        if not verify_run(root)["valid"]:
            raise LabError("a linked execution has invalid file evidence")
        files = {"run.json", *record["files"], *("output/" + x for x in record["artifacts"])}
        for filename in files:
            target = destination / "runs" / run_id / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(contained_file(root, filename), target)
        copied = destination / "runs" / run_id
        if read_json(copied / "run.json") != record or not verify_run(copied)["valid"]:
            raise LabError("copied execution evidence differs from the saved receipt")
    manuscript = (
        f"# {lab.protocol(protocol_id)['question']}\n\n"
        f"Status: {summary['conclusion']}. Scope: {summary['scope']}.\n\n"
        "## Methods\n\nFrozen protocol, code, declared input hashes, seeds and controls accompany "
        "this draft, together with every saved task/attempt and its linked, allowlisted "
        "TrainLab execution files. Lost executions with no linked receipt remain unverified. "
        "Clean-directory replay is distinct from external replication.\n\n"
        "## Results\n\n"
        + "\n".join(
            f"- Seed {x['seed']}: candidate {x['candidate']:.6g}; "
            f"control {x['control']:.6g}; effect {x['effect']:.6g}."
            for x in summary["seed_effects"]
        )
        + "\n\n## Limitations\n\n"
        + "\n".join("- " + x for x in summary["limitations"])
        + "\n\nScientific qualification: NOT_QUALIFIED. External publication: NOT_AUTHORIZED.\n\n"
        "## Next discriminating test\n\n" + summary["next_discriminating_test"] + "\n"
    )
    (destination / "MANUSCRIPT.md").write_text(manuscript)
    manifest = {
        x.relative_to(destination).as_posix(): digest(x)
        for x in sorted(destination.rglob("*"))
        if x.is_file()
    }
    write_json(
        destination / "manifest.json",
        {
            "files": manifest,
            "generated_at": time.time(),
            "scope": "LOCAL_OPERATOR_PACKET_NOT_A_PUBLIC_RELEASE",
        },
    )
    return {
        "path": str(destination),
        "manifest_sha256": digest(destination / "manifest.json"),
        "readiness": summary["conclusion"],
        "external_replication": "NOT_PERFORMED",
    }


def prepare_publication(lab, protocol_id, destination):
    """Atomically publish a verified local operator packet, never an external paper."""
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise LabError("publication destination must be new")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".lab-packet-") as temporary:
        stage = Path(temporary) / "packet"
        result = _prepare_packet(lab, protocol_id, stage)
        # Detect mutation during copying before making the packet available.
        fresh = synthesize(lab, protocol_id)
        if fresh != read_json(stage / "synthesis.json"):
            raise LabError("research evidence changed while packaging")
        stage.rename(destination)
    return {**result, "path": str(destination)}
