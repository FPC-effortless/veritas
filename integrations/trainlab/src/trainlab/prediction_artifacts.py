"""Bound finite-JSON predictions and scoped deterministic adapter checks.

Hashes bind caller declarations, not truthful execution or scientific validity.
Trusted callbacks and operator-authorized data only; no private-data sanitizer.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .research_diagnostics import BudgetExceeded, Diagnostic
from .runner import LabError, _constant, _finite, _pairs

MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 10000


def _require(condition, message):
    if not condition:
        raise LabError(message)


def _json(value, depth=0):
    _require(depth <= 32, "JSON nesting exceeds supported depth")
    if value is None or type(value) in (str, bool):
        return
    if type(value) in (int, float):
        _require(_finite(value), "finite JSON number required")
    elif type(value) is list:
        for item in value:
            _json(item, depth + 1)
    elif type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str, "JSON keys must be strings")
            _json(item, depth + 1)
    else:
        raise LabError("plain JSON values required")


def _bytes(value):
    _json(value)
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise LabError("invalid finite JSON") from exc
    _require(len(data) <= MAX_BYTES, "prediction document exceeds size limit")
    return data


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _text(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 2000 and "\0" not in value


def _rows(rows, value_key, limit=MAX_ROWS):
    _require(type(rows) is list and 1 <= len(rows) <= limit, "bounded nonempty rows required")
    ids = []
    for row in rows:
        _require(type(row) is dict and set(row) == {"id", value_key}
                 and _text(row["id"]), "invalid row fields or identity")
        ids.append(row["id"])
    _require(len(set(ids)) == len(ids), "duplicate row identity")
    _bytes(rows)
    return ids


def _request(request):
    _require(type(request) is dict and set(request) == {
        "schema", "identities", "task", "state", "rows"}
        and request["schema"] == "trainlab.prediction-request.v1", "invalid request schema")
    identities, task, state = request["identities"], request["task"], request["state"]
    _require(type(identities) is dict
             and set(identities) == {"model", "dataset", "code", "configuration"}
             and all(_hash(v) for v in identities.values()), "four SHA256 identities required")
    _require(type(task) is dict and set(task) == {"name", "output_schema"}
             and _text(task["name"]) and task["output_schema"] == "finite-json-v1",
             "explicit task and supported output schema required")
    _require(type(state) is dict and set(state) == {
        "mode", "initial_state_sha256", "persists", "query_mutates", "reset"}
        and state["mode"] in ("stateless", "sequential")
        and _hash(state["initial_state_sha256"]) and _text(state["persists"])
        and _text(state["reset"]) and type(state["query_mutates"]) is bool,
        "explicit state and initial-state identity required")
    _require(state["mode"] != "stateless" or not state["query_mutates"],
             "stateless queries cannot declare mutable state")
    _rows(request["rows"], "input_sha256")
    _require(all(_hash(r["input_sha256"]) for r in request["rows"]), "input hashes required")
    _bytes(request)


def make_request(identities, rows, *, task, state):
    """Freeze ordered public/authorized inputs; bind task/seed/precision via config hash."""
    _rows(rows, "input")
    result = {"schema": "trainlab.prediction-request.v1", "identities": identities,
              "task": task, "state": state,
              "rows": [{"id": r["id"],
                        "input_sha256": hashlib.sha256(_bytes(r["input"])).hexdigest()}
                       for r in rows]}
    _request(result)
    return copy.deepcopy(result)


def _predictions(predictions, rows):
    ids = _rows(predictions, "output")
    _require(ids == [r["id"] for r in rows], "prediction identity/order mismatch")


def write_predictions(path, request, predictions):
    """Atomically publish once; return a hash to preserve in an external receipt."""
    _request(request)
    _predictions(predictions, request["rows"])
    data = _bytes({"schema": "trainlab.predictions.v1", "request": request,
                   "predictions": predictions})
    path = Path(path)
    # ponytail: one local bounded JSON file; no distributed eviction/cache service.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".predictions-", delete=False
        ) as f:
            temporary = Path(f.name)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.link(temporary, path)  # Atomic publication which cannot replace an existing file.
        if os.name == "posix":
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return hashlib.sha256(data).hexdigest()


def read_predictions(path, sha256, request):
    """Read exactly the hashed bytes, validate bindings, return a fresh consumer copy."""
    _request(request)
    _require(_hash(sha256), "external artifact SHA256 required")
    with Path(path).open("rb") as f:
        data = f.read(MAX_BYTES + 1)
    _require(len(data) <= MAX_BYTES and hashlib.sha256(data).hexdigest() == sha256,
             "prediction artifact size/hash mismatch")
    try:
        document = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LabError("invalid prediction JSON") from exc
    _require(type(document) is dict and set(document) == {"schema", "request", "predictions"}
             and document["schema"] == "trainlab.predictions.v1", "invalid prediction schema")
    _request(document["request"])
    _require(_bytes(document["request"]) == _bytes(request), "stale prediction request")
    _predictions(document["predictions"], request["rows"])
    _bytes(document)
    return document["predictions"]


def conformance_checks(rows, *, mode):
    """Exact deterministic replay/batch probes on 2..128 rows, no semantic label oracle.

    predict_rows receives [{id,input}], returns [{id,output}] in the same order.
    Sequential reset must restore the caller's declared initial state before each
    fresh run; splitting must preserve state between batches. Stateless adapters
    additionally undergo reverse-order equivalence. Checks consume model calls.
    """
    _rows(rows, "input", limit=128)
    _require(len(rows) >= 2 and mode in ("stateless", "sequential"),
             "conformance needs two rows and deterministic state mode")
    frozen = copy.deepcopy(rows)
    required = ("predict_rows", "reset") if mode == "sequential" else ("predict_rows",)

    def run(ctx, batches):
        if mode == "sequential":
            ctx.invoke("reset", phase="update")
        outputs = []
        for batch in batches:
            result = ctx.invoke("predict_rows", copy.deepcopy(batch), phase="answer")
            _predictions(result, batch)
            outputs.extend(copy.deepcopy(result))
        return outputs

    def check(ctx, variant):
        try:
            baseline = run(ctx, [frozen])
            batches = [frozen[:1], frozen[1:]] if variant == "batching" else [
                frozen[::-1] if variant == "permutation" else frozen]
            compared = run(ctx, batches)
            if variant == "permutation":
                compared.reverse()
            ok = _bytes(baseline) == _bytes(compared)
        except LabError as exc:
            # BudgetExceeded is a LabError and must retain INCONCLUSIVE semantics.
            if isinstance(exc, BudgetExceeded):
                raise
            return {"status": "FAILED", "summary": "Adapter violated the row/output contract.",
                    "metrics": {"rows": len(frozen)}}
        return {"status": "TESTED" if ok else "FAILED",
                "summary": "Exact deterministic " + variant + " agreement on declared probes.",
                "metrics": {"rows": len(frozen), "agreement": int(ok)}}

    variants = ("replay", "batching", "permutation") if mode == "stateless" else (
        "replay", "batching")
    return [Diagnostic("adapter_" + variant, "1", required,
                       lambda ctx, variant=variant: check(ctx, variant),
                       mode + "; exact JSON; declared probe rows only") for variant in variants]
