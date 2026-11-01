"""TrainLab execution, lease heartbeats and clean declared-input replay."""

from __future__ import annotations

import shutil
import sqlite3
import threading
import time

from trainlab.runner import contained_file, load_config, read_json, run_experiment, verify_run

from .core import Controller, LabError, identity, name


def _run(lab, run_id):
    name(run_id)
    directory = lab.root / "runs" / run_id
    record = read_json(contained_file(directory, "run.json"))
    if (
        record["id"] != run_id
        or record["status"] != "succeeded"
        or not verify_run(directory)["valid"]
    ):
        raise LabError("run evidence is incomplete or changed")
    return record


def _match_recipe(lab, task, run):
    cfg = load_config(lab.snapshot(task["protocol"]) / task["descriptor"]["recipe"])
    for key, source_key in (
        ("seed", "seed"),
        ("command", "command"),
        ("split_identity", "split_identity"),
        ("budget", "budget"),
        ("source_kind", "source_kind"),
        ("metric_directions", "metrics"),
    ):
        if run[key] != cfg[source_key]:
            raise LabError("run does not match frozen recipe")
    from trainlab.runner import digest

    expected = {
        filename: digest(contained_file(lab.snapshot(task["protocol"]), filename))
        for filename in cfg["inputs"]
    }
    if run["inputs"] != expected:
        raise LabError("run input closure differs from frozen snapshot")
    saved = read_json(lab.root / "runs" / run["id"] / "experiment.json")
    if saved != cfg:
        raise LabError("saved experiment differs from frozen recipe")


def evidence_pin(lab, protocol_id):
    """Bind review to every completed primary/replay result and the frozen protocol."""
    p = lab.protocol(protocol_id)
    with lab.connect() as db:
        lab._verify_snapshot(db, protocol_id)
    state = lab.status()
    tasks = [x for x in state["tasks"] if x["protocol"] == protocol_id and x["role"] != "review"]
    if any(x["status"] != "succeeded" for x in tasks):
        raise LabError("review requires every primary and replay task")
    for task in tasks:
        validate_completion(lab, task, task["result"])
    return identity(
        {
            "protocol": p,
            "tasks": [
                {"id": x["id"], "owner": x["owner"], "attempt": x["attempt"], "result": x["result"]}
                for x in sorted(tasks, key=lambda t: t["id"])
            ],
        }
    )


def validate_completion(lab, task, result):
    if not isinstance(result, dict):
        raise LabError("completion result must be an object")
    if task["role"] not in ("replication", "review"):
        if set(result) != {"run_id", "record_pin"}:
            raise LabError("invalid experiment completion")
        run = _run(lab, result["run_id"])
        _match_recipe(lab, task, run)
        if identity(run) != result["record_pin"]:
            raise LabError("run receipt changed")
        if task["role"] != "experiment":
            from .agents import validate_agent_output

            output = read_json(lab.root / "runs" / run["id"] / "output" / "agent_result.json")
            validate_agent_output(lab, task, output)
        return
    if task["role"] == "replication":
        p = lab.protocol(task["protocol"])
        if set(result) != {"replays", "environment_scope", "all_match"}:
            raise LabError("invalid replication receipt")
        if result["environment_scope"] != "CLEAN_DIRECTORY_SAME_HOST_AND_RUNTIME":
            raise LabError("unsupported replication environment claim")
        if set(result["replays"]) != set(task["dependencies"]):
            raise LabError("missing replication seed or arm")
        matches = []
        for key, receipt in result["replays"].items():
            original_task = lab.task(key)
            original = _run(lab, original_task["result"]["run_id"])
            if identity(original) != receipt["original_pin"]:
                raise LabError("replication original receipt changed")
            replay = _run(lab, receipt["run_id"])
            _match_recipe(lab, original_task, replay)
            if replay["id"] == original["id"] or identity(replay) != receipt["record_pin"]:
                raise LabError("replication cannot reuse primary execution")
            match = abs(replay["metrics"][p["metric"]] - original["metrics"][p["metric"]]) <= p[
                "replication_tolerance"
            ] and all(
                replay["artifacts"][a] == original["artifacts"][a] for a in p["replay_artifacts"]
            )
            if receipt["match"] is not match:
                raise LabError("replication match assertion is invalid")
            matches.append(match)
        if result["all_match"] is not all(matches):
            raise LabError("replication summary assertion is invalid")
        return
    if task["role"] == "review":
        if set(result) != {"evidence_pin", "verdict", "findings", "independence", "summary"}:
            raise LabError("invalid review receipt")
        if result["evidence_pin"] != evidence_pin(lab, task["protocol"]):
            raise LabError("review is stale for current evidence")
        if result["verdict"] not in ("clean", "blocking") or not isinstance(
            result["findings"], list
        ):
            raise LabError("review requires an explicit verdict and findings")
        if result["independence"] != "SEPARATE_SESSION_OPERATOR_ASSERTED":
            raise LabError("review requires explicit separate-session provenance")
        if result["verdict"] == "clean" and result["findings"]:
            raise LabError("clean review cannot contain unresolved findings")
        if not isinstance(result["summary"], str) or not result["summary"].strip():
            raise LabError("review summary is required")
        return
    raise LabError("unknown completion role")


def execute_claim(lab: Controller, task):
    """Execute a claimed experiment or replay; reviewers supply their own analysis."""
    if task["role"] == "review":
        raise LabError("review needs a separately authored review receipt")
    stop = threading.Event()
    cancel = threading.Event()

    def pulse():
        while not stop.wait(5):
            try:
                lab.heartbeat(task["id"], task["token"])
            except (LabError, OSError, sqlite3.Error):
                cancel.set()
                return

    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    started = time.perf_counter()
    try:
        snapshot = lab.snapshot(task["protocol"])
        if task["role"] != "replication":
            work = lab.root / "workspaces" / f"{task['id']}-{task['attempt']}"
            work.parent.mkdir(exist_ok=True)
            shutil.copytree(snapshot, work)
            run = run_experiment(
                work / task["descriptor"]["recipe"], lab.root / "runs", cancel=cancel
            )
            lab.checkpoint(task["id"], task["token"], {"run_id": run["id"], "phase": "recorded"})
            if run["status"] != "succeeded":
                raise LabError("TrainLab execution failed; retained run " + run["id"])
            result = {"run_id": run["id"], "record_pin": identity(run)}
        else:
            p = lab.protocol(task["protocol"])
            work = lab.root / "replay_workspaces" / f"{task['id']}-{task['attempt']}"
            work.parent.mkdir(exist_ok=True)
            shutil.copytree(snapshot, work)
            replays: dict[str, dict] = {}
            for key in task["dependencies"]:
                original_task = lab.task(key)
                original = _run(lab, original_task["result"]["run_id"])
                run = run_experiment(
                    work / original_task["descriptor"]["recipe"], lab.root / "runs", cancel=cancel
                )
                lab.checkpoint(
                    task["id"],
                    task["token"],
                    {"completed_replays": replays, "active_run_id": run["id"]},
                )
                if run["status"] != "succeeded":
                    raise LabError("replication execution failed; retained run " + run["id"])
                match = abs(run["metrics"][p["metric"]] - original["metrics"][p["metric"]]) <= p[
                    "replication_tolerance"
                ] and all(
                    run["artifacts"][a] == original["artifacts"][a] for a in p["replay_artifacts"]
                )
                replays[key] = {
                    "run_id": run["id"],
                    "record_pin": identity(run),
                    "original_pin": identity(original),
                    "match": match,
                }
                lab.checkpoint(task["id"], task["token"], {"completed_replays": replays})
            result = {
                "replays": replays,
                "all_match": all(x["match"] for x in replays.values()),
                "environment_scope": "CLEAN_DIRECTORY_SAME_HOST_AND_RUNTIME",
            }
        lab.finish(task["id"], task["token"], "succeeded", result, time.perf_counter() - started)
        return result
    except (LabError, OSError, ValueError) as exc:
        try:
            lab.finish(
                task["id"],
                task["token"],
                "failed",
                {"error": str(exc)},
                time.perf_counter() - started,
            )
        except LabError:
            lab.expire()
        return {"error": str(exc)}
    finally:
        stop.set()
        thread.join(timeout=6)


def run_worker(lab, worker_id, *, watch=False, stop=None):
    stop = stop or threading.Event()
    completed = 0
    while not stop.is_set():
        lab.expire()
        task = lab.claim(worker_id)
        if task is None:
            if not watch:
                break
            stop.wait(1)
            continue
        execute_claim(lab, task)
        completed += 1
    return completed


def submit_review(lab, protocol_id, worker_id, receipt):
    """Reject invalid receipts before claiming; retain admission-only rejections."""
    pending = lab.task(protocol_id + ".review")
    validate_completion(lab, pending, receipt)
    task = lab.claim(worker_id, task_id=pending["id"])
    if task is None:
        raise LabError("review dependencies are incomplete or reviewer is not independent")
    try:
        lab.finish(task["id"], task["token"], "succeeded", receipt, 0)
    except (LabError, OSError, ValueError):
        with lab.transaction() as db:
            row = lab._owned(db, task["id"], task["token"])
            lab._settle(db, row, "rejected", {"error": "review admission invalidated"}, 0)
            db.execute("UPDATE tasks SET status='queued' WHERE id=?", (task["id"],))
        raise
    return lab.synthesize(protocol_id)
