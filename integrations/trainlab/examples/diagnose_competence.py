"""Run constructed value/composition controls and reuse their saved predictions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def target(kind, source, destination):
    from diagnose_assessment import target as lifecycle_target

    lifecycle_target("snapshot-link" if kind == "snapshot-link" else "correct", source, destination)
    if kind == "value-deficient":
        rows = json.loads(destination.read_text())
        for row in rows:
            row["answer"] = 0
        destination.write_text(json.dumps(rows))


def main(root):
    from trainlab.assessment_diagnostics import measured_quality_session
    from trainlab.competence_panels import _sha, freeze_panel, score_artifact, score_panel
    from trainlab.experiment_diagnostics import comparison_ledger, quality_cost
    from trainlab.prediction_artifacts import make_request, read_predictions, write_predictions
    from trainlab.runner import LabError, digest, read_json, write_json

    root.mkdir(parents=True, exist_ok=False)
    inputs, cases = [], []
    for template in ("primitive", "copy", "link"):
        for value in (1, 2, 3):
            map_id = f"{template}-{value}"
            events = [["set", "a", value]]
            if template == "primitive":
                events += [["set", "b", value + 1]]
                answers = {"a": value, "b": value + 1}
            else:
                events += [[template, "b", "a"], ["set", "a", value + 10]]
                answers = {"a": value + 10, "b": value if template == "copy" else value + 10}
            for query in ("a", "b"):
                rid = f"{map_id}:{query}"
                inputs.append({"id": rid, "input": {"events": events, "query": query}})
                cases.append(
                    {
                        "id": rid,
                        "seed": 0,
                        "map_id": map_id,
                        "group": str(value),
                        "template": template,
                        "payload": str(value),
                        "query_id": query,
                        "expected": answers[query],
                    }
                )
    expected = [{"id": c["id"], "answer": c["expected"]} for c in cases]
    state = {
        "mode": "stateless",
        "initial_state_sha256": _sha({}),
        "persists": "Only within each replayed input history",
        "query_mutates": False,
        "reset": "Empty state before every query history",
    }
    identities = {
        "model": _sha("constructed"),
        "dataset": _sha(inputs),
        "code": _sha(
            [digest(Path(__file__)), digest(Path(__file__).with_name("diagnose_assessment.py"))]
        ),
        "configuration": _sha("competence-example-v1"),
    }
    reports, sessions, ledger_arms = {}, {}, []
    for kind in ("correct", "snapshot-link", "value-deficient"):
        bound = {**identities, "model": _sha(kind)}
        request = make_request(
            bound,
            inputs,
            task={"name": "lifecycle-panel", "output_schema": "finite-json-v1"},
            state=state,
        )
        panel = freeze_panel(
            request,
            cases,
            required_seeds=[0],
            required_templates=["primitive", "copy", "link"],
            query_mode="fresh_replay",
            thresholds={"query_accuracy": 0.95, "map_accuracy": 0.95},
        )
        # Persist the plan before the first target invocation; no fit or tuning occurs.
        write_json(root / f"{kind}-panel.json", panel)
        session = measured_quality_session(
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
            identities=bound,
            inputs=inputs,
            expected=expected,
            semantics={"query_mode": "fresh_replay", "operations": "set-copy-link-v1"},
            limits={
                "wall_seconds": 5,
                "cpu_seconds": 2,
                "address_space_bytes": 256 * 1024**2,
                "file_bytes": 1024**2,
            },
        )
        sessions[kind] = session
        if session["point"] is None:
            raise LabError("incomplete target; inspect preserved session")
        path = root / kind / "run/predictions.json"
        if digest(path) != session["predictions_sha256"]:
            raise LabError("session outputs changed before import")
        outputs = [{"id": r["id"], "output": r["answer"]} for r in read_json(path)]
        artifact = root / kind / "bound-predictions.json"
        pin = write_predictions(artifact, request, outputs)
        reports[kind] = score_artifact(
            artifact, pin, panel["panel"], panel_sha256=panel["panel_sha256"]
        )
        # Independent offline recount from the exact artifact; zero new target invocations.
        reused = read_predictions(artifact, pin, request)
        query_correct = sum(_sha(r["output"]) == _sha(c["expected"]) for r, c in zip(reused, cases))
        if query_correct != reports[kind]["report"]["overall"]["correct"]:
            raise LabError("independent query recount disagrees")
        write_json(root / f"{kind}-report.json", reports[kind])
        ledger_arms.append(
            {
                "id": kind,
                "attributes": {"panel": _sha(cases), "trained": False},
                "seeds": [{"seed": 0, "status": "succeeded"}],
                "competence": reports[kind]["competence_reference"],
                "selection": {
                    "split": "validation",
                    "trials": 1,
                    "rule": "fixed constructed control; no model selection",
                },
            }
        )
    clean_panel = read_json(root / "correct-panel.json")
    partial = score_panel(
        clean_panel["panel"],
        [{"id": c["id"], "status": "observed", "value": c["expected"]} for c in cases[:-1]],
        panel_sha256=clean_panel["panel_sha256"],
    )
    report = {
        "kind": "CONSTRUCTED_ENGINEERING_ACCEPTANCE",
        "target_sessions": 3,
        "model_fits": 0,
        "reports": reports,
        "sessions": sessions,
        "partial": partial,
        "ledger": comparison_ledger(
            ledger_arms, required_seeds=[0], matched_fields=["panel", "trained"]
        ),
        "quality_cost": quality_cost([s["point"] for s in sessions.values()]),
        "offline_recount_target_invocations": 0,
    }
    write_json(root / "report.json", report)
    if [reports[k]["report"]["status"] for k in reports] != [
        "TESTED",
        "FAILED",
        "FAILED",
    ] or partial["report"]["status"] != "INCONCLUSIVE":
        raise LabError("unexpected acceptance result")
    print(
        json.dumps(
            {
                "report": str(root / "report.json"),
                "results": {
                    k: {
                        "query_accuracy": v["report"]["overall"]["query_accuracy"],
                        "map_accuracy": v["report"]["overall"]["map_accuracy"],
                        "status": v["report"]["status"],
                    }
                    for k, v in reports.items()
                },
                "partial": partial["report"]["status"],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--target", choices=("correct", "snapshot-link", "value-deficient"))
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    if args.target:
        target(args.target, *args.paths)
    elif args.root:
        main(args.root.resolve())
    else:
        parser.error("--root required")
