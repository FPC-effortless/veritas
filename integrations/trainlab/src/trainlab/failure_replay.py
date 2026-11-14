"""Export bounded, data-only reproductions of pinned state answer mismatches."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from time import monotonic

from .experiment_diagnostics import _number
from .prediction_artifacts import _bytes, _hash, _require
from .runner import LabError, _constant, _pairs, write_json
from .state_diagnostics import _events

_REPRODUCER = "trainlab.state-failure-reproducer.v1"
_ARMS = ("candidate", "reference")
_LIMIT = 1024 * 1024


def _canonical(value):
    # Validate finite, bounded, plain JSON before canonical UTF-8 encoding.
    _bytes(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    except UnicodeError as exc:
        raise LabError("invalid Unicode scalar value in fixture or outcome") from exc


def _hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _case(case):
    _require(
        type(case) is dict
        and set(case) == {"fixture", "events", "query"}
        and type(case["fixture"]) is dict
        and len(case["fixture"]) <= 64,
        "expected bounded state fixture, events and query",
    )
    _events(case["events"])
    encoded = _canonical(case)
    _require(
        len(json.dumps({"case": case}, indent=2, sort_keys=True).encode()) <= _LIMIT - 4096,
        "state case exceeds byte limit",
    )
    return json.loads(encoded)


def _implementations(implementations):
    _require(
        type(implementations) is dict and set(implementations) == set(_ARMS),
        "expected explicitly registered state implementations",
    )
    records = {}
    for arm in _ARMS:
        record = implementations[arm]
        _require(
            type(record) is dict
            and set(record) == {"sha256", "simulate"}
            and _hash(record["sha256"])
            and callable(record["simulate"]),
            "implementation needs declared source digest and simulator",
        )
        records[arm] = dict(record)
    _require(
        records["candidate"]["sha256"] != records["reference"]["sha256"]
        and records["candidate"]["simulate"] is not records["reference"]["simulate"],
        "distinct implementation identities required",
    )
    return records


def _probe(case, implementations):
    outcomes, errors = {}, {}
    for arm, spec in implementations.items():
        try:
            value = spec["simulate"](**copy.deepcopy(case))
            outcomes[arm] = _hash_bytes(_canonical(value))
        except Exception as exc:
            errors[arm] = type(exc).__name__
    state = "INCONCLUSIVE"
    if not errors:
        state = "FAILED" if outcomes["candidate"] != outcomes["reference"] else "TESTED"
    return {"status": state, "outcome_sha256": outcomes, "error_types": errors}


def _deletions(current):
    for index in range(len(current["events"])):
        events = current["events"][:index] + current["events"][index + 1 :]
        yield {**current, "events": events}
    for field in current["fixture"]:
        yield {
            **current,
            "fixture": {key: value for key, value in current["fixture"].items() if key != field},
        }


def _identities(implementations):
    return {arm: records["sha256"] for arm, records in implementations.items()}


def reduce_failure(root, case, implementations, *, max_calls=100, max_seconds=10):
    """Greedy deletion reduction retaining the original pair of output hashes."""
    case = _case(case)
    implementations = _implementations(implementations)
    _require(
        type(max_calls) is int and 1 <= max_calls <= 10000 and _number(max_seconds, 0.001, 3600),
        "bounded reduction budget required",
    )
    root = Path(root).absolute()
    _require(
        not any(p.is_symlink() for p in (root, *root.parents)),
        "reproducer directory may not use symlinks",
    )
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    started = monotonic()
    trials = []

    def probe(value):
        if len(trials) >= max_calls or monotonic() - started >= max_seconds:
            return None
        result = _probe(value, implementations)
        trials.append(
            {
                "case_sha256": _hash_bytes(_canonical(value)),
                "events": len(value["events"]),
                "fixture_fields": len(value["fixture"]),
                **result,
            }
        )
        return result

    current = case
    original = probe(case)
    minimal = False
    status = "INCONCLUSIVE"
    witness = original and original["status"] == "FAILED"
    if original and original["status"] == "TESTED":
        status = "NO_FAILURE"
    elif witness:
        while True:
            unresolved = False
            for trial in _deletions(current):
                observed = probe(trial)
                if observed is None:
                    unresolved = True
                    break
                if observed == original:
                    current = trial
                    break
                unresolved |= observed["status"] == "INCONCLUSIVE"
            else:
                minimal = not unresolved
                break
            if observed is None:
                break
        if minimal:
            status = "TESTED"

    if monotonic() - started >= max_seconds:
        status = "INCONCLUSIVE"

    pin = None
    if witness:
        path = root / "reproducer.json"
        manifest = {
            "schema": _REPRODUCER,
            "class": "STATE_ANSWER_MISMATCH",
            "implementations": _identities(implementations),
            "witness": original["outcome_sha256"],
            "case": current,
        }
        write_json(path, manifest)
        pin = _hash_bytes(path.read_bytes())
    report = {
        "schema": "trainlab.state-failure-reduction.v1",
        "status": status,
        "one_deletion_minimal": status == "TESTED",
        "reproducer_sha256": pin,
        "calls": len(trials),
        "max_calls": max_calls,
        "max_seconds": max_seconds,
        "trials": trials,
        "scientific_qualification": "NOT_QUALIFIED",
    }
    write_json(root / "reduction.json", report)
    return report


def replay(root, sha256, implementations):
    """Read one pinned data-only reproducer and replay via supplied local callbacks."""
    implementations = _implementations(implementations)
    path = Path(root) / "reproducer.json"
    _require(
        _hash(sha256)
        and path.is_file()
        and not any(p.is_symlink() for p in (path, *path.absolute().parents)),
        "expected regular reproducer file and external pin",
    )
    with path.open("rb") as stream:
        raw = stream.read(_LIMIT + 1)
    _require(len(raw) <= _LIMIT and _hash_bytes(raw) == sha256, "reproducer pin or size mismatch")
    try:
        payload = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LabError("invalid reproducer JSON") from exc
    _require(
        type(payload) is dict
        and set(payload) == {"schema", "class", "implementations", "witness", "case"}
        and payload["schema"] == _REPRODUCER
        and payload["class"] == "STATE_ANSWER_MISMATCH",
        "unsupported state reproducer",
    )
    _require(payload["implementations"] == _identities(implementations), "implementation mismatch")
    witness = payload["witness"]
    _require(
        type(witness) is dict
        and set(witness) == set(_ARMS)
        and all(_hash(v) for v in witness.values())
        and witness["candidate"] != witness["reference"],
        "expected distinct witnessed outcome hashes",
    )
    case = _case(payload["case"])
    observed = _probe(case, implementations)
    if observed["status"] == "FAILED" and observed["outcome_sha256"] != witness:
        observed["status"] = "INCONCLUSIVE"
    return {
        **observed,
        "exact_witness": observed["outcome_sha256"] == witness,
        "reproducer_sha256": sha256,
        "events": len(case["events"]),
        "fixture_fields": len(case["fixture"]),
    }
