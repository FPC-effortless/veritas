"""Measure complete-map reliability and CPU cost in three constructed controls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from diagnose_competence import target


def main(root):
    from trainlab.competence_panels import _sha, freeze_panel
    from trainlab.prediction_artifacts import make_request
    from trainlab.reliability_cost import compare_at_reliability, run_panel_session
    from trainlab.runner import LabError, digest, write_json

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
    kinds = ["correct", "snapshot-link", "value-deficient"]
    repeats = [0, 1, 2]
    state = {
        "mode": "stateless",
        "initial_state_sha256": _sha({}),
        "persists": "Within each replayed input history",
        "query_mutates": False,
        "reset": "Empty state before each query history",
    }
    source = Path(__file__).resolve()
    identities = {
        "dataset": _sha(inputs),
        "configuration": _sha("reliability-demo-v1"),
        "code": _sha(
            [
                digest(source),
                digest(source.with_name("diagnose_competence.py")),
                digest(source.with_name("diagnose_assessment.py")),
            ]
        ),
    }
    panels = {}
    for kind in kinds:
        request = make_request(
            {**identities, "model": _sha(kind)},
            inputs,
            task={"name": "lifecycle-panel", "output_schema": "finite-json-v1"},
            state=state,
        )
        panels[kind] = freeze_panel(
            request,
            cases,
            required_seeds=[0],
            required_templates=["primitive", "copy", "link"],
            query_mode="fresh_replay",
            thresholds={"query_accuracy": 0.95, "map_accuracy": 0.95},
        )
    order = [
        {"arm": kinds[(r + i) % len(kinds)], "repeat": r}
        for r in repeats
        for i in range(len(kinds))
    ]
    write_json(
        root / "plan.json",
        {
            "panels": panels,
            "order": order,
            "required_arms": kinds,
            "required_repeats": repeats,
            "metric": "map_accuracy",
            "quality_floor": 0.95,
        },
    )
    records = []
    for item in order:
        kind, repeat = item["arm"], item["repeat"]
        session_root = root / f"{kind}-{repeat}"
        session = run_panel_session(
            [sys.executable, str(source), "--target", kind, "{inputs}", "{predictions}"],
            session_root,
            cwd=root,
            **panels[kind],
            inputs=inputs,
            operations="set-copy-link-v1",
            limits={
                "wall_seconds": 5,
                "cpu_seconds": 2,
                "address_space_bytes": 256 * 1024**2,
                "file_bytes": 1024**2,
            },
        )
        records.append(
            {**item, "root": str(session_root), "manifest_sha256": session["manifest_sha256"]}
        )
    # Replays every pinned session without invoking the target again.
    report = compare_at_reliability(
        records,
        required_arms=kinds,
        required_repeats=repeats,
        metric="map_accuracy",
        quality_floor=0.95,
    )
    write_json(root / "records.json", records)
    write_json(
        root / "report.json",
        {
            "kind": "CONSTRUCTED_ENGINEERING_ACCEPTANCE",
            "target_sessions": 9,
            "model_fits": 0,
            "offline_target_invocations": 0,
            "comparison": report,
        },
    )
    if report["status"] != "TESTED" or report["eligible_arms"] != ["correct"]:
        raise LabError("unexpected reliability acceptance outcome")
    print(
        json.dumps(
            {
                "report": str(root / "report.json"),
                "eligible_arms": report["eligible_arms"],
                "arms": {
                    k: {
                        "median_seconds": v["median_seconds"],
                        "metrics": v["runs"][0]["metrics"],
                        "competence_status": v["runs"][0]["competence_status"],
                    }
                    for k, v in report["arms"].items()
                },
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
