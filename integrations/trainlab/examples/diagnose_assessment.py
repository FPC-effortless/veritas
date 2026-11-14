"""Constructed lifecycle controls; no learned models or scientific admission."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def target(kind, source, destination):
    rows = json.loads(source.read_text())
    predictions = []
    for row in rows:
        memory = {}

        def read(key):
            seen = set()
            while key in memory and memory[key][0] == "link":
                if key in seen:
                    return None
                seen.add(key)
                key = memory[key][1]
            return memory[key][1] if key in memory else None

        for op, key, value in row["input"]["events"]:
            if op == "set":
                memory[key] = ("value", value)
            elif op == "copy":
                memory[key] = ("value", read(value))
            elif op == "link":
                memory[key] = ("value", read(value)) if kind == "snapshot-link" else ("link", value)
            elif op == "delete":
                memory.pop(key, None)
            else:
                raise ValueError("unsupported operation")
        predictions.append({"id": row["id"], "answer": read(row["input"]["query"])})
    destination.write_text(json.dumps(predictions))


def main(root):
    from trainlab.assessment_diagnostics import (
        _sha,
        generalization_audit,
        measured_quality_session,
        paired_slices,
        training_order_audit,
    )
    from trainlab.experiment_diagnostics import quality_cost
    from trainlab.runner import LabError, digest, read_json, write_json
    from trainlab.state_diagnostics import verify_repair

    root.mkdir(parents=True, exist_ok=False)
    inputs, expected, descriptors = [], [], []
    # Expected answers follow declared operation semantics; target outputs are not reused.
    for payload in (1, 2, 3):
        for prefix in ("known-", "renamed-"):
            a, b = prefix + "a", prefix + "b"
            for template in (
                "copy-overwrite",
                "link-overwrite",
                "alias-overwrite",
                "delete-source",
            ):
                events = [["set", a, payload]]
                if template == "copy-overwrite":
                    events += [["copy", b, a], ["set", a, payload + 10]]
                    answer = payload
                elif template == "link-overwrite":
                    events += [["link", b, a], ["set", a, payload + 10]]
                    answer = payload + 10
                elif template == "alias-overwrite":
                    events += [["link", b, a], ["set", b, payload + 20]]
                    answer = payload + 20
                else:
                    events += [["link", b, a], ["delete", a, None]]
                    answer = None
                identity = f"{prefix}{payload}-{template}"
                inputs.append({"id": identity, "input": {"events": events, "query": b}})
                expected.append({"id": identity, "answer": answer})
                descriptors.append(
                    {
                        "id": identity,
                        "group": f"role-{prefix}{payload}",
                        "axes": {"template": template, "payload": str(payload), "identity": prefix},
                        "scales": {"active_records": 2, "link_depth": 1},
                    }
                )
    identities = {
        "model": _sha("constructed"),
        "dataset": _sha(inputs),
        "code": digest(Path(__file__)),
        "configuration": _sha("assessment-demo-v1"),
    }
    sessions = {}
    for kind in ("correct", "snapshot-link"):
        sessions[kind] = measured_quality_session(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--target",
                kind,
                "{inputs}",
                "{predictions}",
            ],
            root / kind,
            cwd=root,
            identities={**identities, "model": _sha(kind)},
            inputs=inputs,
            expected=expected,
            semantics={"query_mode": "fresh_replay", "operations": "copy-link-set-delete-v1"},
            limits={
                "wall_seconds": 5,
                "cpu_seconds": 2,
                "address_space_bytes": 256 * 1024**2,
                "file_bytes": 1024**2,
            },
        )
    if any(r["point"] is None for r in sessions.values()):
        raise LabError("acceptance session incomplete; inspect preserved receipts")
    correct, faulty = [
        read_json(root / kind / "run/predictions.json") for kind in ("correct", "snapshot-link")
    ]
    pairs = [
        {
            "id": e["id"],
            "seed": 0,
            "group": d["group"],
            "payload": d["axes"]["payload"],
            "template": d["axes"]["template"],
            "candidate": _sha(c["answer"]) == _sha(e["answer"]),
            "baseline": _sha(b["answer"]) == _sha(e["answer"]),
        }
        for e, d, c, b in zip(expected, descriptors, correct, faulty)
    ]
    exposure = [
        {"example_sha256": _sha(r), "supervision_sha256": _sha(e)} for r, e in zip(inputs, expected)
    ]
    joint = {
        "id": "joint",
        "initialization_sha256": _sha("same-initialization"),
        "optimizer_sha256": _sha("same-optimizer"),
        "updates": [[x] for x in exposure],
    }
    staged = {**joint, "id": "staged", "updates": joint["updates"][::-1]}
    unequal = {**staged, "id": "unequal", "updates": staged["updates"][:-1]}
    # Same generator throughout: novelty in declared strings is not generalization proof.
    training = [descriptors[0]]
    audit = generalization_audit(training, descriptors[1:])
    panels = {}
    for name, indices in (("fresh", range(12, 24)), ("regression", range(12))):
        panels[name] = [
            {
                "id": expected[i]["id"],
                "group": name,
                "expected": expected[i]["answer"],
                "before": {"status": "observed", "value": correct[i]["answer"]},
                "after": {"status": "observed", "value": faulty[i]["answer"]},
            }
            for i in indices
        ]
    repair = verify_repair(
        panels,
        required_ids={k: [r["id"] for r in v] for k, v in panels.items()},
        freshness={
            "evaluation_sha256": _sha(panels),
            "frozen_before_evaluation": True,
            "used_for_selection": False,
        },
        selection_groups=[],
        hypotheses=[
            {"id": "representation", "description": "Internal improvement may help behavior"}
        ],
        interventions=[
            {
                "hypothesis_id": "representation",
                "observation": "Constructed internal discrepancy decreases 99%; not measured.",
                "evidence_sha256": _sha("constructed internal metric"),
            }
        ],
    )
    report = {
        "kind": "CONSTRUCTED_ENGINEERING_ACCEPTANCE",
        "model_fits": 0,
        "sessions": sessions,
        "generalization": audit,
        "paired": paired_slices(
            pairs, required_ids=[r["id"] for r in expected], required_seeds=[0]
        ),
        "quality_cost": quality_cost([r["point"] for r in sessions.values()]),
        "training_order": training_order_audit([joint, staged]),
        "unequal_training": training_order_audit([joint, unequal]),
        "failed_repair": repair,
    }
    write_json(root / "report.json", report)
    if (
        sessions["correct"]["quality"] != 1
        or sessions["snapshot-link"]["quality"] != 0.5
        or report["training_order"]["status"] != "TESTED"
        or report["unequal_training"]["status"] != "FAILED"
        or repair["status"] != "FAILED"
    ):
        raise LabError("constructed acceptance mismatch")
    print(
        json.dumps(
            {
                "report": str(root / "report.json"),
                "correct": 1,
                "snapshot_link": 0.5,
                "failed_repair": repair["status"],
                "model_fits": 0,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--target", choices=("correct", "snapshot-link"))
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    if args.target:
        target(args.target, *args.paths)
    elif args.root:
        main(args.root.resolve())
    else:
        parser.error("--root required")
