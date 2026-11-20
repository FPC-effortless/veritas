"""Prepare a DESIGN-only exact 081 package without launching a worker or self-approving."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys

from forge_data.core import canonical
from forge_data.diagnostics import diagnose
from trainlab.runner import digest
from conductor import runtime, TOKEN_SCHEMA

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DESIGN_SEEDS = (81107, 81131, 81157, 81173, 81199, 81223, 81233, 81239)
BASE_SCOPE = "coglife.core-engineering.v1"
NATIVE = [
    "core/provenance.py", "core/models.py", "world/generator.py",
    "trajectory/models.py", "experience/__init__.py", "experience/models.py", "experience/adapter.py",
    "life/__init__.py", "life/models.py", "life/runtime.py", "life/native_bridge.py",
]

def dump(path, data):
    path.write_bytes(canonical(data))

def plan(bundle: Path, execution: Path):
    bundle.mkdir(parents=True, exist_ok=False, mode=0o700)
    roles = {}
    for label, source, role in (
        ("world_worker.py", HERE / "world_worker.py", "code"),
        ("protocol.md", HERE / "README.md", "protocol"),
        *[(f"investigation_world/{p}", REPO / "src/investigation_world" / p,
           "code") for p in NATIVE],
    ):
        target = bundle / label
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        roles[label] = role
    # Deliberate namespace import of the exact core module, not a modified
    # investigation_world/__init__.py or whole-product smoke test.
    dump(bundle / "world-spec.json", {"schema":"coglife.world-check.v1",
                                     "role":"ENGINEERING_DESIGN","seeds":list(DESIGN_SEEDS)})
    roles["world-spec.json"] = "world_spec"
    eligibility = {
        "schema": "forge.diagnostic-input.v1",
        "feature_fields": ["engineering_seed", "stage"],
        "group_fields": ["outer_world"],
        "rows": [{"id": f"design-{i}", "split": "validation",
                  "groups": {"outer_world": f"engineering/{seed}"},
                  "features": {"engineering_seed": seed, "stage": BASE_SCOPE}}
                 for i, seed in enumerate(DESIGN_SEEDS)],
    }
    forge_src = bundle / "world-design-forge-source.json"
    dump(forge_src, eligibility)
    report = diagnose(forge_src, sha256=digest(forge_src), max_rows=len(DESIGN_SEEDS), max_findings=20)
    dump(bundle / "world-design-forge-receipt.json", report)
    roles["world-design-forge-source.json"] = "world_spec"
    roles["world-design-forge-receipt.json"] = "forge_receipt"
    recipe = {
        "schema": "trainlab.experiment.v1", "execution_purpose": "engineering_diagnostic",
        "name": "cog081-world-check", "description": "Exact replay and authority fixtures; no learned results",
        "command": [str(Path(sys.executable).absolute()), "world_worker.py", "world-check"],
        "source_kind": "CONSTRUCTED", "seed": 810081, "timeout_seconds": 30,
        "split_identity": "ENGINEERING DESIGN only; no TRAIN/CAL/DEV outcomes",
        "metrics": {"lifetimes": "max"}, "budget": {"cpu": 1},
        "inputs": sorted(roles), "artifacts": ["world-check.json"],
    }
    dump(bundle / "recipe.json", recipe)
    draft = {
        "schema": TOKEN_SCHEMA, "decision": "PENDING", "study": "cog081",
        "phase": "world-check", "author": "root", "reviewer": "",
        "recipe_sha256": digest(bundle / "recipe.json"),
        "inputs": {name: digest(bundle / name) for name in roles}, "input_roles": roles,
        "runtime": runtime(), "parent_receipt_sha256": {},
        "execution_root": str(execution.resolve()), "conductor_sha256": digest(HERE / "conductor.py"),
    }
    dump(bundle / "REVIEW_DRAFT.json", draft)
    return draft

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--execution", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(plan(args.bundle, args.execution), sort_keys=True))
if __name__ == "__main__":
    main()
