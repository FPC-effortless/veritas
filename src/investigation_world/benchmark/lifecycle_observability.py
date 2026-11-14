"""Bounded development-only counterfactual audit, never scientific admission.

Deleting an event is represented by NOP, preserving all COPY time boundaries.
Final-map sensitivity and a preserved absence snapshot are distinct diagnostics.
"""

from __future__ import annotations

from itertools import combinations


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(memory):
    _require(isinstance(memory, dict) and set(memory) == {
        "schema", "keys", "events", "composed_keys"
    } and memory["schema"] == "woyengi.lifecycle.v1", "unsupported lifecycle schema")
    keys, events, probes = (memory[k] for k in ("keys", "events", "composed_keys"))
    def text(value):
        return isinstance(value, str) and 0 < len(value) <= 256 and "\0" not in value
    _require(isinstance(keys, list) and 1 <= len(keys) <= 64
             and all(map(text, keys)) and len(set(keys)) == len(keys), "invalid keys")
    _require(isinstance(probes, list) and all(text(k) and k in keys for k in probes)
             and len(set(probes)) == len(probes), "invalid composed keys")
    _require(isinstance(events, list) and len(events) <= 256, "bounded event list required")
    shapes = {"set": {"op", "key", "value"}, "delete": {"op", "key"},
              "copy": {"op", "key", "source"}, "link": {"op", "key", "source"},
              "nop": {"op"}}
    for event in events:
        _require(isinstance(event, dict) and isinstance(event.get("op"), str)
                 and event["op"] in shapes and set(event) == shapes[event["op"]],
                 "invalid event")
        if event["op"] == "nop":
            continue
        _require(text(event["key"]) and event["key"] in keys, "undeclared destination")
        if event["op"] in {"copy", "link"}:
            _require(text(event["source"]) and event["source"] in keys, "undeclared source")
        if event["op"] == "set":
            _require(text(event["value"]), "invalid value")


def _resolve(records, key):
    path = []
    while key not in path:
        path.append(key)
        cell = records.get(key)
        if cell is None:
            return None, path, "missing"
        kind, value = cell
        if kind == "value":
            return value, path, "value"
        key = value
    return None, path, "cycle"


def _replay(memory, omitted):
    records, copies = {}, {}
    for index, event in enumerate(memory["events"]):
        op = "nop" if index in omitted else event["op"]
        if op == "nop":
            continue
        key = event["key"]
        if op == "set":
            records[key] = ("value", event["value"])
        elif op == "link":
            records[key] = ("link", event["source"])
        elif op == "delete":
            records.pop(key, None)
        else:
            value, path, reason = _resolve(records, event["source"])
            copies[index] = {"value": value, "path": path, "reason": reason}
            if value is None:
                records.pop(key, None)
            else:
                records[key] = ("value", value)
    return {key: _resolve(records, key)[0] for key in memory["keys"]}, copies


def replay(memory, omitted=()):
    """Return a full map after replacing selected DELETE events with NOP."""
    validate(memory)
    _require(isinstance(omitted, (list, tuple, set, frozenset))
             and all(type(i) is int and 0 <= i < len(memory["events"])
                     and memory["events"][i]["op"] == "delete" for i in omitted),
             "only DELETE ablations are supported")
    return _replay(memory, set(omitted))[0]


def audit_pair(left, right, stratum):
    """Report semantics of one controlled COPY/LINK pair, without admission."""
    validate(left)
    validate(right)
    _require(stratum in {"overwrite", "delete_recreate"}, "invalid stratum")
    _require(left["keys"] == right["keys"]
             and left["composed_keys"] == right["composed_keys"]
             and len(left["events"]) == len(right["events"]), "pair shape mismatch")
    differences = [(i, a, b) for i, (a, b) in enumerate(zip(left["events"], right["events"]))
                   if a != b]
    _require(len(differences) == 1, "pair must differ at one focal opcode")
    focal, a, b = differences[0]
    _require({a["op"], b["op"]} == {"copy", "link"}
             and (a["key"], a["source"]) == (b["key"], b["source"])
             and a["key"] in left["composed_keys"], "invalid focal contrast")
    source, destination = a["source"], a["key"]
    _require(not any(e.get("key") == destination for e in left["events"][focal + 1:]),
             "focal destination must retain its original COPY/LINK binding")
    tail = [(i, e["op"]) for i, e in enumerate(left["events"])
            if i > focal and e.get("key") == source]
    deletes = [i for i, op in tail if op == "delete"]
    _require(len(deletes) <= 4, "at most four focal-source deletes are auditable")
    _require(bool(deletes) == (stratum == "delete_recreate")
             and any(op == "set" for _, op in tail), "stratum lacks declared transition")
    if deletes:
        _require(all(any(j > i and op == "set" for j, op in tail) for i in deletes),
                 "source deletion lacks subsequent recreation")
    strict = [op for _, op in tail] == (
        ["set"] if stratum == "overwrite" else ["delete", "set"]
    )
    baselines = [_replay(memory, set()) for memory in (left, right)]
    _require(baselines[0][0][destination] != baselines[1][0][destination],
             "focal final answer must distinguish COPY from LINK")
    subsets = [list(c) for n in range(1, len(deletes) + 1) for c in combinations(deletes, n)]
    rows = []
    for memory, (reference, copies) in zip((left, right), baselines):
        interventions = []
        for omitted in subsets:
            changed, alternative_copies = _replay(memory, set(omitted))
            affected = sorted(k for k in memory["keys"] if reference[k] != changed[k])
            witnesses = []
            for index, observation in copies.items():
                if index <= focal or observation["reason"] != "missing":
                    continue
                path = observation["path"]
                if (destination not in path or path[-1] != source
                        or alternative_copies[index]["value"] is None):
                    continue
                # A real focal-source DELETE must precede this COPY, and no
                # subsequent source write may have ended that absence interval.
                previous = [(i, op) for i, op in tail if i < index]
                if not previous or previous[-1][1] != "delete":
                    continue
                saved = memory["events"][index]["key"]
                witnesses.append({
                    "copy_index": index, "saved_key": saved,
                    "preserved_at_own_final_query": reference[saved] is None
                    and changed[saved] is not None
                    and not any(e.get("key") == saved
                                for e in memory["events"][index + 1:]),
                })
            interventions.append({
                "omitted_delete_indices": omitted, "changed_keys": affected,
                "changed_composed_keys": sorted(set(affected) & set(memory["composed_keys"])),
                "absence_snapshots": witnesses,
            })
        rows.append({"focal_op": memory["events"][focal]["op"], "interventions": interventions})
    return {"schema": "veritas.lifecycle-observability.v1", "stratum": stratum,
            "focal_index": focal, "strict_primary_transition": strict,
            "focal_source_delete_count": len(deletes), "rows": rows,
            "scope": "FINAL_QUERY_SENSITIVITY_NOT_CAUSAL_DIVERSITY_OR_ADMISSION"}
