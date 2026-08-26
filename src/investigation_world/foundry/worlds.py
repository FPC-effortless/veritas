from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from investigation_world.foundry.models import DistributionSplit, stable_hash


class CompanyWorldBuildSpec(BaseModel):
    split: DistributionSplit
    seed: int
    output_root: Path
    company_id: str = "ORG-000001"
    profile: str = "base"
    overrides: dict[str, int | float | str] = Field(default_factory=dict)


class CompanyWorldBuildPlan(BaseModel):
    generator_path: Path
    builds: list[CompanyWorldBuildSpec]

    @model_validator(mode="after")
    def validate_unique(self):
        seeds = [item.seed for item in self.builds]
        roots = [str(item.output_root.resolve()) for item in self.builds]
        splits = [item.split for item in self.builds]
        if len(seeds) != len(set(seeds)):
            raise ValueError("CompanyWorld foundry builds require disjoint seeds")
        if len(roots) != len(set(roots)):
            raise ValueError("CompanyWorld foundry builds require disjoint output roots")
        if len(splits) != len(set(splits)):
            raise ValueError("CompanyWorld foundry build plan allows one world per split")
        return self


_DEFAULT_ASSIGNMENTS = {
    "SEED", "COMPANY_ID", "N_EMP", "N_CUSTOMERS", "N_SUPPLIERS",
    "N_PRODUCTS", "N_SALES_ORDERS", "TARGET_REVENUE",
}


class _AssignmentRewriter(ast.NodeTransformer):
    def __init__(self, replacements: dict[str, Any], output_root: Path):
        self.replacements = replacements
        self.output_root = output_root
        self.seen: set[str] = set()

    def visit_Assign(self, node: ast.Assign):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return self.generic_visit(node)
        name = node.targets[0].id
        if name in self.replacements:
            self.seen.add(name)
            return ast.copy_location(ast.Assign(targets=node.targets, value=ast.Constant(value=self.replacements[name])), node)
        if name == "root":
            self.seen.add("root")
            return ast.copy_location(
                ast.Assign(
                    targets=node.targets,
                    value=ast.Call(func=ast.Name(id="Path", ctx=ast.Load()), args=[ast.Constant(value=str(self.output_root))], keywords=[]),
                ),
                node,
            )
        if name == "zip_path":
            self.seen.add("zip_path")
            return ast.copy_location(ast.Assign(targets=node.targets, value=ast.Constant(value=str(self.output_root.with_suffix(".zip")))), node)
        return self.generic_visit(node)


def patched_generator_source(source: str, spec: CompanyWorldBuildSpec) -> str:
    tree = ast.parse(source)
    replacements: dict[str, Any] = {"SEED": spec.seed, "COMPANY_ID": spec.company_id, **spec.overrides}
    unknown = set(spec.overrides) - _DEFAULT_ASSIGNMENTS
    if unknown:
        raise ValueError(f"unsupported CompanyWorld generator overrides: {sorted(unknown)}")
    rewriter = _AssignmentRewriter(replacements, spec.output_root)
    tree = rewriter.visit(tree)
    ast.fix_missing_locations(tree)
    required = {"SEED", "COMPANY_ID", "root"}
    missing = required - rewriter.seen
    if missing:
        raise ValueError(f"generator is missing required assignments: {sorted(missing)}")
    return ast.unparse(tree) + "\n"


def default_companyworld_build_plan(generator_path: str | Path, output_dir: str | Path) -> CompanyWorldBuildPlan:
    output = Path(output_dir)
    return CompanyWorldBuildPlan(
        generator_path=Path(generator_path),
        builds=[
            CompanyWorldBuildSpec(split=DistributionSplit.TRAIN, seed=42, output_root=output / "train", profile="base"),
            CompanyWorldBuildSpec(split=DistributionSplit.IID_TEST, seed=43, output_root=output / "iid_test", profile="base"),
            CompanyWorldBuildSpec(
                split=DistributionSplit.OOD, seed=142, output_root=output / "ood",
                company_id="ORG-OOD-000001", profile="scale_shift",
                overrides={
                    "N_EMP": 3200, "N_CUSTOMERS": 26000, "N_SUPPLIERS": 1500,
                    "N_PRODUCTS": 90000, "N_SALES_ORDERS": 65000,
                    "TARGET_REVENUE": 6_000_000_000.0,
                },
            ),
            CompanyWorldBuildSpec(
                split=DistributionSplit.ADVERSARIAL, seed=242,
                output_root=output / "adversarial", company_id="ORG-ADV-000001",
                profile="adversarial_base",
            ),
        ],
    )


def materialize_companyworld_build_plan(plan: CompanyWorldBuildPlan, *, execute: bool = False) -> dict[str, Any]:
    source = plan.generator_path.read_text(encoding="utf-8")
    generator_hash = hashlib.sha256(source.encode()).hexdigest()
    builds: list[dict[str, Any]] = []
    for spec in plan.builds:
        patched = patched_generator_source(source, spec)
        patched_hash = hashlib.sha256(patched.encode()).hexdigest()
        item: dict[str, Any] = {
            "split": spec.split.value,
            "seed": spec.seed,
            "profile": spec.profile,
            "company_id": spec.company_id,
            "output_root": str(spec.output_root),
            "overrides": spec.overrides,
            "patched_generator_sha256": patched_hash,
            "executed": False,
        }
        if execute:
            spec.output_root.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
                handle.write(patched)
                temp_path = Path(handle.name)
            try:
                subprocess.run([sys.executable, str(temp_path)], check=True)
            finally:
                temp_path.unlink(missing_ok=True)
            item["executed"] = True
            validation = spec.output_root / "validation" / "validation_report.json"
            if validation.exists():
                item["validation_sha256"] = hashlib.sha256(validation.read_bytes()).hexdigest()
        builds.append(item)
    manifest = {
        "format": "veritas-companyworld-foundry-worlds-v1",
        "generator_path": str(plan.generator_path),
        "generator_sha256": generator_hash,
        "builds": builds,
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    return manifest


def write_companyworld_world_manifest(plan: CompanyWorldBuildPlan, output: str | Path, *, execute: bool = False) -> dict[str, Any]:
    manifest = materialize_companyworld_build_plan(plan, execute=execute)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest
