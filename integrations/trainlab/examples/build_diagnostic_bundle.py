"""Package explicitly pinned public diagnostic reports for offline inspection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trainlab.diagnostic_bundle import STATUSES, _parse, _read, _sha, create, export, verify
from trainlab.runner import LabError


def nodes(value, pointer=()):
    if type(value) is dict:
        if value.get("status") in STATUSES:
            yield pointer, value
        for key, child in value.items():
            yield from nodes(child, (*pointer, key))
    elif type(value) is list:
        for i, child in enumerate(value):
            yield from nodes(child, (*pointer, i))


def run(root, reports):
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    inputs = root / "inputs"
    inputs.mkdir()
    packs, findings = [], []
    for i, (filename, pin) in enumerate(reports):
        source = Path(filename)
        if source.is_symlink():
            raise LabError("source symlink unsupported")
        raw = _read(source, pin)
        document = _parse(raw)
        found = list(nodes(document))
        if not found:
            raise LabError("report has no supported status nodes")
        name, pack = f"source-{i:03}.json", f"import-{i:03}"
        (inputs / name).write_bytes(raw)
        packs.append(
            {
                "id": pack,
                "version": "bounded-json-import-v1",
                "applicability": "Dictionary status nodes from the pinned public report",
                "dependencies": ["source report; exact SHA256"],
                "cost": "Offline inspection only; original diagnostic cost not inferred",
                "evidence_requirements": [pin],
                "limitations": [
                    "Import preserves supplied evidence, not truth attestation",
                    "Source diagnostic schema/limits remain inside raw JSON",
                    "No source code executed or third-party integration claimed",
                ],
            }
        )
        for pointer, node in found:
            findings.append(
                {
                    "id": f"{pack}/" + ("/".join(map(str, pointer)) or "root"),
                    "pack_id": pack,
                    "kind": "observation",
                    "summary": f"Imported source check at {'/'.join(map(str, pointer)) or 'root'}; "
                    "inspect evidence for scope and affected examples.",
                    "status": node["status"],
                    "evidence": {"path": name, "sha256": pin, "pointer": list(pointer)},
                    "reviews": [],
                }
            )
    packs.append(
        {
            "id": "coverage",
            "version": "1",
            "applicability": "This example only",
            "dependencies": [],
            "cost": "Not run",
            "evidence_requirements": ["Separate native-model and device acceptance"],
            "limitations": ["Does not enumerate every possible diagnostic"],
        }
    )
    for name, status in (
        ("GPU accounting", "UNSUPPORTED"),
        ("Native learned-state acceptance", "NOT_RUN"),
        ("Research productivity study", "NOT_RUN"),
    ):
        findings.append(
            {
                "id": name,
                "pack_id": "coverage",
                "kind": "observation",
                "summary": "No such measurement is supplied by this bundle.",
                "status": status,
                "evidence": None,
                "reviews": [],
            }
        )
    spec = {
        "schema": "trainlab.diagnostic-bundle-spec.v1",
        "title": "Research diagnostics — executed engineering controls",
        "data_classification": "CONSTRUCTED_PUBLIC",
        "packs": packs,
        "findings": findings,
    }
    raw = json.dumps(spec, indent=2).encode()
    path = inputs / "spec.json"
    path.write_bytes(raw)
    pin = create(path, _sha(raw), root / "bundle")
    verification = verify(root / "bundle", pin)
    archive = export(root / "bundle", pin, root / "diagnostics.zip")
    summary = {
        "manifest_sha256": pin,
        "archive": archive,
        "verification": verification,
        "source_reports": len(reports),
        "findings": len(findings),
        "model_fits": 0,
        "scientific_qualification": "NOT_QUALIFIED",
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--report",
        action="append",
        nargs=2,
        metavar=("PATH", "SHA256"),
        required=True,
        help="Explicitly authorized public constructed report",
    )
    args = parser.parse_args()
    if len(args.report) > 32:
        parser.error("at most 32 reports")
    run(args.root, args.report)
