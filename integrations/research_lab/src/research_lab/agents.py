"""Bounded role work orders for an operator's existing agent command/provider.

The provider reads frozen lab_context.json and writes the TrainLab output contract.
No provider, account, model budget, or autonomous-scientist ability is invented.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from trainlab.runner import contained_file, digest, load_config, read_json, write_json

from .core import AGENT_ROLES, LabError, canonical, identity, name, number, text_list
from .evidence import ingest_proposal, link, put_node, validate_proposal

ORDER_FIELDS = {
    "schema",
    "id",
    "program",
    "author",
    "role",
    "resource",
    "slots",
    "max_attempts",
    "priority",
    "objective",
    "acceptance",
    "context_nodes",
    "dependencies",
    "recipe",
    "source_commit",
}


def register_order(lab, order, recipes_root):
    if (
        not isinstance(order, dict)
        or set(order) != ORDER_FIELDS
        or order["schema"] != "research_lab.work_order.v1"
    ):
        raise LabError("unsupported agent work order")
    for key in ("id", "program", "author", "resource"):
        name(order[key])
    if order["role"] not in AGENT_ROLES:
        raise LabError("unsupported agent role")
    if (
        not isinstance(order["objective"], str)
        or not order["objective"].strip()
        or len(order["objective"]) > 8000
    ):
        raise LabError("agent objective is required")
    text_list(order["acceptance"])
    for key in ("slots", "max_attempts"):
        if type(order[key]) is not int or not 1 <= order[key] <= 10:
            raise LabError("invalid agent execution envelope")
    number(order["priority"])
    import re

    if not isinstance(order["source_commit"], str) or not re.fullmatch(
        "[a-f0-9]{40}", order["source_commit"]
    ):
        raise LabError("agent source commit must be pinned")
    for key in ("context_nodes", "dependencies"):
        if not isinstance(order[key], list) or len(order[key]) > 128:
            raise LabError("invalid agent context/dependencies")
        for value in order[key]:
            name(value)
    root = Path(recipes_root).resolve()
    config = load_config(contained_file(root, order["recipe"]))
    if "agent_result.json" not in config["artifacts"]:
        raise LabError("agent recipe must retain agent_result.json")
    if "lab_context.json" in config["inputs"]:
        raise LabError("lab_context.json is reserved for controller-owned context")
    pin = identity(order)
    with lab.transaction() as db:
        prior = db.execute("SELECT pin FROM protocols WHERE id=?", (order["id"],)).fetchone()
        if prior:
            if prior[0] != pin:
                raise LabError("agent work order is immutable")
            lab._verify_snapshot(db, order["id"])
            return pin
        program = db.execute("SELECT * FROM programs WHERE id=?", (order["program"],)).fetchone()
        resource = db.execute("SELECT * FROM resources WHERE id=?", (order["resource"],)).fetchone()
        if not program or not resource or resource["slots"] < order["slots"]:
            raise LabError("missing agent program or registered resource")
        if resource["rate_microusd"] and not program["allow_paid"]:
            raise LabError("paid agent execution requires explicit program authorization")
        lab._freeze_author(db, order["author"])
        nodes = []
        for node_id in order["context_nodes"]:
            row = db.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
            if not row:
                raise LabError("agent context node is missing")
            nodes.append({**dict(row), "body": json.loads(row["body"])})
        for task_id in order["dependencies"]:
            row = db.execute(
                "SELECT p.program FROM tasks t JOIN protocols p ON p.id=t.protocol WHERE t.id=?",
                (task_id,),
            ).fetchone()
            if not row or row[0] != order["program"]:
                raise LabError("agent dependencies must exist in the same program")
        context = {
            "schema": "research_lab.agent_context.v1",
            "order": order,
            "nodes": nodes,
            "authority": "PROPOSALS_ONLY; no scientific or publication authority",
        }
        snapshots = lab.root / "snapshots"
        snapshots.mkdir(exist_ok=True)
        destination = lab.snapshot(order["id"])
        if destination.exists():
            raise LabError("orphan agent snapshot exists")
        with tempfile.TemporaryDirectory(dir=snapshots) as temporary:
            stage = Path(temporary) / "source"
            stage.mkdir()
            if (
                sum(contained_file(root, item).stat().st_size for item in config["inputs"])
                > 128 * 1024 * 1024
            ):
                raise LabError("agent snapshot exceeds size limit")
            for item in config["inputs"]:
                if item in {"protocol.json", "snapshot.json", "lab-agent.json"}:
                    raise LabError("reserved agent snapshot name")
                target = stage / item
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(contained_file(root, item), target)
            write_json(stage / "lab_context.json", context)
            write_json(
                stage / "lab-agent.json",
                {**config, "inputs": [*config["inputs"], "lab_context.json"]},
            )
            write_json(stage / "protocol.json", order)
            manifest = {
                x.relative_to(stage).as_posix(): digest(x)
                for x in sorted(stage.rglob("*"))
                if x.is_file()
            }
            write_json(stage / "snapshot.json", manifest)
            stage.rename(destination)
        db.execute(
            "INSERT INTO protocols VALUES (?,?,?,?,?)",
            (order["id"], order["program"], canonical(order), pin, identity(manifest)),
        )
        lab._task(
            db,
            order,
            order["id"] + ".agent",
            order["role"],
            {"recipe": "lab-agent.json"},
            order["dependencies"],
            config["timeout_seconds"],
        )
        lab._event(
            db,
            "agent_order_frozen",
            {"id": order["id"], "pin": pin, "context_pin": identity(context)},
        )
    return pin


def validate_agent_output(lab, task, output):
    fields = {"schema", "role", "summary", "findings", "proposals", "source_nodes", "next_actions"}
    if (
        not isinstance(output, dict)
        or set(output) != fields
        or output["schema"] != "research_lab.agent_result.v1"
    ):
        raise LabError("unsupported agent result")
    if (
        output["role"] != task["role"]
        or not isinstance(output["summary"], str)
        or not output["summary"].strip()
    ):
        raise LabError("agent result role/summary mismatch")
    text_list(output["next_actions"])
    if not isinstance(output["findings"], list) or not isinstance(output["proposals"], list):
        raise LabError("agent findings and proposals must be lists")
    for proposal in output["proposals"]:
        validate_proposal(proposal)
    if not isinstance(output["source_nodes"], list):
        raise LabError("agent citations must name registered context nodes")
    context = read_json(lab.snapshot(task["protocol"]) / "lab_context.json")
    allowed = {x["id"] for x in context["nodes"]}
    if any(x not in allowed for x in output["source_nodes"]):
        raise LabError("agent cited a source absent from frozen context")
    # The record remains model-authored evidence, even when schema-valid.
    return output


def index_agent_output(lab, task, result, *, db=None):
    output = read_json(lab.root / "runs" / result["run_id"] / "output" / "agent_result.json")
    validate_agent_output(lab, task, output)
    node_id = "agent." + task["protocol"]
    put_node(
        lab,
        node_id,
        "evidence",
        {
            "origin": "AGENT_AUTHORED_UNVERIFIED",
            "result": output,
            "run_receipt": result,
            "scientific_qualification": "NOT_QUALIFIED",
        },
        db=db,
    )
    for source in output["source_nodes"]:
        link(lab, node_id, "derived_from", source, db=db)
    for proposal in output["proposals"]:
        ingest_proposal(lab, proposal, db=db)
        link(lab, "proposal." + proposal["id"], "derived_from", node_id, db=db)
    return {"node_id": node_id}
