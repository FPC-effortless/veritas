"""Evidence-bounded asynchronous research-department council.

Role seats are NOT running agents. Notes are operator-supplied, immutable,
unverified reports. Meeting snapshots never imply live attendance, authority
to spend, a completed experiment, or independently accepted science.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import time

from .core import LabError, canonical, identity, name

# One department and an accountable head ROLE for each frontier research lane.
DEPARTMENTS = {
    "TAC_CORE": "Persistent Backbone Architecture",
    "PSN": "Persistent Selective Memory",
    "PSN2": "Neural Population Communication",
    "DPSL": "Graph and Editable Memory",
    "BOUNDED_FIELD": "Bounded Neural Dynamics",
    "ATLAS_CASSA": "Geometric Transport and State",
    "USEF_X": "Specialized Computation and Routing",
    "NSF_V8_NFD": "Plasticity and Neural Fields",
    "FLOCK_COLLECT": "Corrective and Collective Memory",
    "SSA": "Sparse Structure and Selection",
    "PRS": "Persistent Role-State Routing",
    "SCM_SIE": "Executable Structures and Repair",
    "GEOMETRIC_KAKEYA": "Geometric Representation Research",
    "TOKENIZATION": "Tokenization and Representation",
    "LEARNING_OBJECTIVES": "Learning Objectives and Optimization",
    "GPU_KERNELS": "GPU Kernels and Compute",
    "MEMORY_GOVERNANCE": "Memory Evidence and Governance",
    "TAC_OCR": "OCR and Multimodal Transfer",
}
SCHEMA = "research_lab.department_note.v1"
FIELDS = {
    "schema", "id", "department", "head_role", "reporter_principal",
    "source_pin", "stage", "summary", "negative_results", "blocker",
    "help_requests", "shares", "responses", "next_action",
    "observed_execution_id", "review_receipt",
}
STAGES = {
    "PLAN_ONLY", "SOURCE_RECOVERY", "PREPARED", "EXECUTING_REPORTED",
    "REVIEW_PENDING", "REVIEWED_REPORTED", "BLOCKED", "COMPLETE_REPORTED",
}


def roster():
    return {
        "schema": "research_lab.department_roster.v1",
        "authority": "ROLE_SEATS_ONLY; NO_EXECUTING_HEADS_ATTESTED",
        "departments": [
            {"id": department, "title": title, "head_role": "head." + department}
            for department, title in DEPARTMENTS.items()
        ],
    }


def _bounded(value, label, *, maximum=2000, allow_empty=False):
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or (not allow_empty and not value.strip())
    ):
        raise LabError("invalid council " + label)
    return value


def _items(value, keys, label, maximum=16):
    if not isinstance(value, list) or len(value) > maximum:
        raise LabError("invalid council " + label)
    for item in value:
        if not isinstance(item, dict) or set(item) != keys:
            raise LabError("invalid council " + label + " item")


def validate_note(note):
    if not isinstance(note, dict) or set(note) != FIELDS or note["schema"] != SCHEMA:
        raise LabError("unsupported department note")
    name(note["id"])
    department = note["department"]
    if department not in DEPARTMENTS or note["head_role"] != "head." + department:
        raise LabError("unknown department or mismatched head role")
    name(note["reporter_principal"])  # asserted, not an authenticated agent session
    pin = note["source_pin"]
    if pin != "UNKNOWN" and (
        not isinstance(pin, str) or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", pin) is None
    ):
        raise LabError("source pin must be exact SHA or UNKNOWN")
    if note["stage"] not in STAGES:
        raise LabError("unknown research department stage")
    for key in ("summary", "next_action"):
        _bounded(note[key], key)
    _bounded(note["blocker"], "blocker", allow_empty=True)
    for key in ("observed_execution_id", "review_receipt"):
        _bounded(note[key], key, maximum=240)
    if not isinstance(note["negative_results"], list) or len(note["negative_results"]) > 16:
        raise LabError("invalid negative results")
    for item in note["negative_results"]:
        _bounded(item, "negative result")
    _items(note["help_requests"], {"id", "target", "question", "expected_artifact", "evidence_ref"}, "requests")
    request_ids = set()
    for request in note["help_requests"]:
        name(request["id"])
        if not request["id"].startswith(department + ".") or request["id"] in request_ids:
            raise LabError("request IDs must be unique and department-qualified")
        request_ids.add(request["id"])
        if request["target"] not in DEPARTMENTS or request["target"] == department:
            raise LabError("help request needs a different registered department")
        for key in ("question", "expected_artifact", "evidence_ref"):
            _bounded(request[key], key)
    _items(note["shares"], {"target", "finding", "evidence_ref"}, "shares")
    for shared in note["shares"]:
        if shared["target"] not in (*DEPARTMENTS, "ALL"):
            raise LabError("unknown share recipient")
        _bounded(shared["finding"], "shared finding")
        _bounded(shared["evidence_ref"], "share evidence")
    _items(note["responses"], {"request_id", "response", "evidence_ref"}, "responses")
    for response in note["responses"]:
        name(response["request_id"])
        if "." not in response["request_id"]:
            raise LabError("response request ID must be department-qualified")
        _bounded(response["response"], "help response")
        _bounded(response["evidence_ref"], "response evidence")
    if len(canonical(note).encode("utf-8")) > 32768:
        raise LabError("department note exceeds 32 KiB")
    return note


def initialize(lab):
    with lab.connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS department_notes (
                id TEXT PRIMARY KEY, department TEXT NOT NULL,
                pin TEXT NOT NULL, body TEXT NOT NULL, recorded_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS council_meetings (
                id TEXT PRIMARY KEY, pin TEXT NOT NULL,
                body TEXT NOT NULL, recorded_at REAL NOT NULL
            );
        """)


def post_note(lab, note):
    """Append-only. Reusing an ID with changed source/content fails closed."""
    validate_note(note)
    initialize(lab)
    pin = identity(note)
    with lab.transaction() as db:
        prior = db.execute("SELECT pin FROM department_notes WHERE id=?", (note["id"],)).fetchone()
        if prior:
            if prior["pin"] != pin:
                raise LabError("department note is immutable; use a new ID")
            return {"id": note["id"], "pin": pin, "created": False,
                    "qualification": "AUTHOR_REPORTED_UNVERIFIED"}
        db.execute(
            "INSERT INTO department_notes VALUES (?,?,?,?,?)",
            (note["id"], note["department"], pin, canonical(note), time.time()),
        )
        lab._event(db, "council_department_note", {
            "department": note["department"], "id": note["id"], "pin": pin,
        })
    return {"id": note["id"], "pin": pin, "created": True,
            "qualification": "AUTHOR_REPORTED_UNVERIFIED"}


def _latest_notes(db):
    notes = {}
    for row in db.execute("SELECT department,id,pin,body,recorded_at FROM department_notes ORDER BY rowid"):
        notes[row["department"]] = {
            "id": row["id"], "pin": row["pin"], "body": json.loads(row["body"]),
            "recorded_at": row["recorded_at"],
        }
    return notes


def _build_minutes(meeting_id, latest, *, as_of):
    requests = {}
    responses = []
    shares = []
    departments = []
    fresh_count = 0
    for department, title in DEPARTMENTS.items():
        record = latest.get(department)
        is_fresh = bool(record and 0 <= as_of - record["recorded_at"] <= 7 * 86400)
        fresh_count += int(is_fresh)
        departments.append({
            "id": department, "title": title, "head_role": "head." + department,
            "report": (
                "AUTHOR_REPORTED_UNVERIFIED" if is_fresh
                else "STALE_NOTE_NOT_CURRENT_SUBMISSION" if record else "NO_SUBMISSION"
            ),
            "note_id": record["id"] if record else None,
            "note_pin": record["pin"] if record else None,
            "stage": record["body"]["stage"] if record else None,
            "source_pin": record["body"]["source_pin"] if record else None,
        })
        if record:
            for item in record["body"]["help_requests"]:
                requests[item["id"]] = {"origin": department, **item}
            for item in record["body"]["responses"]:
                responses.append({"by": department, **item})
            for item in record["body"]["shares"]:
                shares.append({"by": department, **item, "note_pin": record["pin"]})

    exchanges = []
    acknowledged = set()
    for request_id, item in sorted(requests.items()):
        answers = [
            response for response in responses
            if response["request_id"] == request_id and response["by"] == item["target"]
        ]
        acknowledged.update((answer["by"], answer["request_id"]) for answer in answers)
        exchanges.append({
            **item,
            "status": "RESPONSE_REPORTED_UNVERIFIED" if answers else "AWAITING_TARGET_REPORT",
            "responses": answers,
            "authority": "NO_WORK_OR_COMPUTE_AUTHORIZED",
        })
    unmatched = [
        answer for answer in responses
        if (answer["by"], answer["request_id"]) not in acknowledged
    ]
    return {
        "schema": "research_lab.council_minutes.v1",
        "id": meeting_id,
        "meeting_type": "ASYNCHRONOUS_NOTE_ASSEMBLY_NOT_LIVE_HEAD_MEETING",
        "attendance": "NO_INDEPENDENT_HEAD_SESSION_ATTESTATION",
        "qualification": "AUTHOR_NOTES_UNVERIFIED",
        "departments": departments,
        "reported_departments": sum(bool(latest.get(dep)) for dep in DEPARTMENTS),
        "freshly_reporting_departments": fresh_count,
        "expected_departments": len(DEPARTMENTS),
        "help_exchanges": exchanges,
        "shared_findings": shares,
        "unmatched_responses": unmatched,
        "disposition": "PROPOSALS_ONLY; SCIENTIFIC_AND_COMPUTE_GATES_UNCHANGED",
    }


def convene(lab, meeting_id):
    """Freeze latest submitted notes as minutes; create no work and no workers."""
    name(meeting_id)
    initialize(lab)
    with lab.transaction() as db:
        prior = db.execute("SELECT body FROM council_meetings WHERE id=?", (meeting_id,)).fetchone()
        if prior:
            return json.loads(prior["body"])
        now = time.time()
        minutes = _build_minutes(meeting_id, _latest_notes(db), as_of=now)
        minutes["assembled_at_utc"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
        pin = identity(minutes)
        minutes["pin"] = pin
        db.execute(
            "INSERT INTO council_meetings VALUES (?,?,?,?)",
            (meeting_id, pin, canonical(minutes), time.time()),
        )
        lab._event(db, "council_minutes_assembled", {
            "id": meeting_id, "pin": pin,
            "reported_departments": minutes["reported_departments"],
            "new_execution_authority": False,
        })
    return minutes


def latest_minutes(lab):
    initialize(lab)
    with lab.connect() as db:
        row = db.execute("SELECT body FROM council_meetings ORDER BY rowid DESC LIMIT 1").fetchone()
    return json.loads(row["body"]) if row else {
        "schema": "research_lab.council_minutes.v1",
        "status": "NO_ASSEMBLED_MEETING",
        "authority": "NO_HEADS_OR_WORKERS_ATTESTED",
    }
