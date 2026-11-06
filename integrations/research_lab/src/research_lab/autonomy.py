"""Bounded evidence-to-experiment dispatch over frozen, operator-admitted recipes.

The native director selects preregistered branches; an optional trusted director
work order can propose a profile. Neither path can invent commands or certify its
own evidence. One POSIX lock serializes admission, including after process restart.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from trainlab.runner import contained_file, digest, load_config, read_json

from .agents import register_order
from .core import LabError, canonical, identity, name, validate_protocol
from .evidence import put_node, validate_proposal
from .execution import validate_completion

OUTCOMES = {"BOUNDED_CONTRAST_SUPPORTED", "BOUNDED_CONTRAST_NOT_SUPPORTED"}


@contextmanager
def admission_lock(lab):
    import fcntl

    with (lab.root / "autonomy.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def initialize(lab):
    with lab.connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS autonomous_lanes (
                id TEXT PRIMARY KEY, spec TEXT NOT NULL, pin TEXT NOT NULL,
                manifest TEXT NOT NULL, phase TEXT NOT NULL, reason TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS autonomous_rounds (
                lane TEXT NOT NULL REFERENCES autonomous_lanes(id), n INTEGER NOT NULL,
                profile TEXT NOT NULL, protocol TEXT NOT NULL UNIQUE, spec TEXT NOT NULL,
                decision TEXT NOT NULL, PRIMARY KEY(lane,n)
            );
        """)


def _inventory(root):
    return {
        x.relative_to(root).as_posix(): digest(contained_file(root, x.relative_to(root).as_posix()))
        for x in sorted(root.rglob("*"))
        if x.is_file() or x.is_symlink()
    }


def register_lane(lab, spec, recipes_root):
    """Admit a bounded recipe graph once; registration itself launches no process."""
    fields = {"schema", "id", "program", "initial", "profiles", "director", "max_rounds"}
    if (
        not isinstance(spec, dict)
        or set(spec) != fields
        or spec["schema"] != "research_lab.autonomy.v1"
    ):
        raise LabError("unsupported autonomous lane")
    name(spec["id"])
    name(spec["program"])
    name(spec["initial"])
    if (
        len(spec["id"]) > 48
        or type(spec["max_rounds"]) is not int
        or not 1 <= spec["max_rounds"] <= 100
    ):
        raise LabError("invalid lane id or round bound")
    profiles = spec["profiles"]
    if (
        not isinstance(profiles, dict)
        or not 1 <= len(profiles) <= 64
        or spec["initial"] not in profiles
    ):
        raise LabError("lane requires bounded admitted profiles")
    root = Path(recipes_root).resolve()
    files = set()
    for profile, entry in profiles.items():
        name(profile)
        if not isinstance(entry, dict) or set(entry) != {"protocol", "transitions"}:
            raise LabError("invalid profile")
        if (
            not isinstance(entry["transitions"], dict)
            or set(entry["transitions"]) != OUTCOMES
            or any(
                target is not None and target not in profiles
                for target in entry["transitions"].values()
            )
        ):
            raise LabError("both positive and negative outcomes need an explicit route or stop")
        p = read_json(contained_file(root, entry["protocol"]))
        validate_protocol(p)
        if p["program"] != spec["program"]:
            raise LabError("profile crosses program boundary")
        files.add(entry["protocol"])
        configs = []
        for arm in ("candidate", "control"):
            files.add(p[arm])
            cfg = load_config(contained_file(root, p[arm]))
            if cfg["metrics"].get(p["metric"]) != p["direction"] or not set(
                p["replay_artifacts"]
            ) <= set(cfg["artifacts"]):
                raise LabError("profile metric/artifact mismatch")
            configs.append(cfg)
            files.update(cfg["inputs"])
        if configs[0]["split_identity"] != configs[1]["split_identity"]:
            raise LabError("profile splits differ")
        with lab.connect() as db:
            resource = db.execute("SELECT * FROM resources WHERE id=?", (p["resource"],)).fetchone()
            program = db.execute("SELECT * FROM programs WHERE id=?", (p["program"],)).fetchone()
            if not program or not resource or resource["slots"] < p["slots"]:
                raise LabError("missing program or resource")
            if resource["rate_microusd"] and not program["allow_paid"]:
                raise LabError("paid compute requires explicit authorization")
    if spec["director"] is not None:
        order = read_json(contained_file(root, spec["director"]))
        if order.get("role") != "director" or order.get("program") != spec["program"]:
            raise LabError("director must belong to this program")
        cfg = load_config(contained_file(root, order["recipe"]))
        files.update([spec["director"], order["recipe"], *cfg["inputs"]])
    if sum(contained_file(root, f).stat().st_size for f in files) > 128 * 1024 * 1024:
        raise LabError("lane snapshot exceeds 128 MiB")
    manifest = {f: digest(contained_file(root, f)) for f in sorted(files)}
    pin = identity({"spec": spec, "manifest": manifest})
    initialize(lab)
    with admission_lock(lab):
        with lab.connect() as db:
            prior = db.execute(
                "SELECT pin FROM autonomous_lanes WHERE id=?", (spec["id"],)
            ).fetchone()
        if prior:
            if prior[0] != pin:
                raise LabError("autonomous lane is immutable")
            _load(lab, spec["id"])
            return pin
        parent = lab.root / "autonomy"
        parent.mkdir(exist_ok=True)
        destination = parent / spec["id"]
        # Recover only an identical pre-commit orphan; never overwrite changed inputs.
        if destination.exists():
            if _inventory(destination) != manifest:
                raise LabError("orphan lane snapshot changed")
        else:
            with tempfile.TemporaryDirectory(dir=parent) as temporary:
                stage = Path(temporary) / "bundle"
                stage.mkdir()
                for filename in files:
                    target = stage / filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(contained_file(root, filename), target)
                if _inventory(stage) != manifest:
                    raise LabError("lane inputs changed during admission")
                stage.rename(destination)
        with lab.transaction() as db:
            db.execute(
                "INSERT INTO autonomous_lanes VALUES "
                "(?,?,?,?,'ready','registered; awaiting dispatch')",
                (spec["id"], canonical(spec), pin, canonical(manifest)),
            )
            lab._event(db, "autonomy_registered", {"lane": spec["id"], "pin": pin})
    return pin


def _load(lab, lane):
    with lab.connect() as db:
        row = db.execute("SELECT * FROM autonomous_lanes WHERE id=?", (lane,)).fetchone()
    if not row:
        raise LabError("unknown autonomous lane")
    root = lab.root / "autonomy" / lane
    manifest = json.loads(row["manifest"])
    spec = json.loads(row["spec"])
    if _inventory(root) != manifest or identity({"spec": spec, "manifest": manifest}) != row["pin"]:
        raise LabError("admitted lane inputs changed")
    return spec, root


def _phase(lab, lane, phase, reason):
    with lab.transaction() as db:
        prior = db.execute(
            "SELECT phase,reason FROM autonomous_lanes WHERE id=?", (lane,)
        ).fetchone()
        if tuple(prior) != (phase, reason):
            db.execute(
                "UPDATE autonomous_lanes SET phase=?,reason=? WHERE id=?", (phase, reason, lane)
            )
            lab._event(db, "autonomy_state", {"lane": lane, "phase": phase, "reason": reason})
    return {"lane": lane, "phase": phase, "reason": reason}


def _prepare(lab, spec, root, profile, n, decision, proposal=None, author=None):
    p = read_json(contained_file(root, spec["profiles"][profile]["protocol"]))
    if author is not None:
        p["author"] = author
    if proposal is not None:
        validate_proposal(proposal)
        if proposal.get("execution") != {"profile": profile}:
            raise LabError("director proposal requires one admitted profile")
        if (
            proposal["seeds"] != p["seeds"]
            or proposal["primary_metric"] != p["metric"]
            or proposal["direction"] != p["direction"]
            or proposal["minimum_effect"] < p["minimum_effect"]
        ):
            raise LabError("director cannot weaken frozen seeds, metric or effect threshold")
        p.update(
            question=proposal["question"],
            hypothesis=proposal["hypothesis"],
            alternatives=proposal["competing_explanations"],
            predictions=proposal["predictions"],
            next_test=proposal["next_discriminating_test"],
            minimum_effect=proposal["minimum_effect"],
        )
        for key in ("controls", "ablations", "limitations"):
            p[key] = list(dict.fromkeys([*p[key], *proposal[key]]))
    p["id"] = f"{spec['id']}-r{n:03}"
    validate_protocol(p)
    decision = {**decision, "profile": profile, "protocol_pin": identity(p)}
    with lab.transaction() as db:
        db.execute(
            "INSERT INTO autonomous_rounds VALUES (?,?,?,?,?,?)",
            (
                spec["id"],
                n,
                profile,
                p["id"],
                canonical(p),
                canonical(decision),
            ),
        )
        lab._event(db, "autonomy_decision", {"lane": spec["id"], "round": n, **decision})


def _affordable(lab, p, root):
    # Admission reserves no money; require enough remaining envelope for all primary,
    # replay and review work before creating another generation of tasks.
    seconds = (
        2
        * len(p["seeds"])
        * sum(
            load_config(contained_file(root, p[a]))["timeout_seconds"]
            for a in ("candidate", "control")
        )
        + 30
    )
    seconds *= p["slots"]
    with lab.connect() as db:
        program = db.execute("SELECT * FROM programs WHERE id=?", (p["program"],)).fetchone()
        resource = db.execute("SELECT * FROM resources WHERE id=?", (p["resource"],)).fetchone()
    import math

    return (
        program["charged_seconds"] + program["reserved_seconds"] + seconds <= program["cap_seconds"]
        and program["charged_microusd"]
        + program["reserved_microusd"]
        + math.ceil(seconds * resource["rate_microusd"])
        <= program["cap_microusd"]
    )


def _tick_lane(lab, lane):
    spec, root = _load(lab, lane)
    with lab.connect() as db:
        rounds = [
            dict(r)
            for r in db.execute("SELECT * FROM autonomous_rounds WHERE lane=? ORDER BY n", (lane,))
        ]
    if not rounds:
        _prepare(lab, spec, root, spec["initial"], 1, {"basis": "PREREGISTERED_INITIAL_EXPERIMENT"})
        return _phase(lab, lane, "ready", "initial decision preserved; dispatch on next tick")
    row = rounds[-1]
    p = json.loads(row["spec"])
    with lab.connect() as db:
        exists = db.execute("SELECT id FROM protocols WHERE id=?", (p["id"],)).fetchone()
    if not exists and not _affordable(lab, p, root):
        return _phase(
            lab,
            lane,
            "budget_exhausted",
            "remaining program envelope cannot cover primary, replay and review",
        )
    lab.register(p, root)  # Immutable registration makes a post-enqueue restart idempotent.
    tasks = [t for t in lab.status()["tasks"] if t["protocol"] == p["id"]]
    bad = [t for t in tasks if t["status"] in {"failed", "lost", "blocked"}]
    if bad:
        return _phase(
            lab,
            lane,
            "blocked",
            "; ".join(f"{t['id']}: {t['status']} {t['result'].get('error', '')}" for t in bad),
        )
    if any(t["status"] != "succeeded" for t in tasks):
        pending = sorted({t["role"] for t in tasks if t["status"] != "succeeded"})
        return _phase(lab, lane, "waiting", "awaiting " + ", ".join(pending))
    summary = lab.synthesize(p["id"])
    if summary["conclusion"] not in OUTCOMES:
        return _phase(lab, lane, "blocked", summary["conclusion"])
    node = f"result.{p['id']}"
    put_node(lab, node, "evidence", summary)
    if row["n"] >= spec["max_rounds"]:
        return _phase(lab, lane, "complete", "round bound reached; final result preserved")
    proposal = None
    author = None
    decision = {
        "basis": "PREREGISTERED_EVIDENCE_BRANCH",
        "evidence_pin": summary["evidence_pin"],
        "conclusion": summary["conclusion"],
    }
    if spec["director"] is None:
        profile = spec["profiles"][row["profile"]]["transitions"][summary["conclusion"]]
    else:
        order = read_json(contained_file(root, spec["director"]))
        order["id"] = f"{lane}-director{row['n']:03}"
        menu_id = f"menu.{order['id']}"
        menu = {
            k: read_json(contained_file(root, v["protocol"])) for k, v in spec["profiles"].items()
        }
        put_node(
            lab,
            menu_id,
            "next_test",
            {
                "profiles": menu,
                "output_contract": (
                    "zero proposals to stop, or exactly one proposal with execution.profile"
                ),
            },
        )
        order["context_nodes"] = list(dict.fromkeys([*order["context_nodes"], node, menu_id]))
        order["dependencies"] = [t["id"] for t in tasks]
        register_order(lab, order, root)
        task = lab.task(order["id"] + ".agent")
        if task["status"] != "succeeded":
            phase = "blocked" if task["status"] in {"failed", "blocked", "lost"} else "waiting"
            return _phase(lab, lane, phase, f"director {task['id']}: {task['status']}")
        validate_completion(lab, task, task["result"])
        output = read_json(
            lab.root / "runs" / task["result"]["run_id"] / "output" / "agent_result.json"
        )
        if len(output["proposals"]) > 1:
            raise LabError("director must select at most one executable proposal per lane round")
        proposal = output["proposals"][0] if output["proposals"] else None
        profile = proposal.get("execution", {}).get("profile") if proposal else None
        if proposal and profile not in spec["profiles"]:
            raise LabError("director selected an unadmitted profile")
        author = task["owner"]
        decision.update(
            basis="VALIDATED_DIRECTOR_PROPOSAL", director_receipt=task["result"], author=author
        )
    if profile is None:
        return _phase(
            lab, lane, "complete", "director or preregistered branch stopped after reviewed result"
        )
    _prepare(lab, spec, root, profile, row["n"] + 1, decision, proposal, author)
    return _phase(
        lab, lane, "ready", "next experiment selected from reviewed evidence and preserved"
    )


def tick(lab):
    initialize(lab)
    with admission_lock(lab):
        with lab.connect() as db:
            lanes = [r[0] for r in db.execute("SELECT id FROM autonomous_lanes ORDER BY id")]
        result = []
        for lane in lanes:
            try:
                result.append(_tick_lane(lab, lane))
            except (LabError, OSError, ValueError, KeyError, TypeError) as exc:
                result.append(_phase(lab, lane, "blocked", str(exc)))
        return result
