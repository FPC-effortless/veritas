from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "integrations" / "prime" / "veritas-sre-open"
MODULE_ROOT = PACKAGE_ROOT / "veritas_sre_open"
ALLOWED_CLASSES = {"regression", "infrastructure", "capacity", "transient"}
FORBIDDEN_RELEASE_MARKERS = {
    "SRE-CAND-92A84929AD1E82E24357",
    "EVID-2C69B48DCDD5F2232EABDC9B",
    "QREPORT-C585121E94D91766BB6664E3",
    "QPANEL-AFF065BA4C2FD75BE9BB3EBE",
    "PRIVREL-036192DA63716D331C929C0C",
    "531d1358883ec399add640c3519c31a36f6c93981796d7a3e8b37e2a7ace0d2a",
    "private_tasks.json",
}


def _load_scoring_module():
    path = MODULE_ROOT / "scoring.py"
    spec = importlib.util.spec_from_file_location("veritas_sre_open_scoring", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prime_public_package_has_hub_metadata_and_balanced_synthetic_tasks() -> None:
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["name"] == "veritas-sre-open"
    assert pyproject["project"]["version"] == "0.11.0"
    assert pyproject["project"]["license"] == {"file": "LICENSE"}
    assert "Apache License" in (PACKAGE_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert any(dep.startswith("verifiers") for dep in pyproject["project"]["dependencies"])
    assert pyproject["tool"]["verifiers"]["eval"] == {
        "num_examples": 12,
        "rollouts_per_example": 1,
    }

    records = json.loads((MODULE_ROOT / "public_tasks.json").read_text(encoding="utf-8"))
    assert len(records) == 12
    assert Counter(record["expected_causal_class"] for record in records) == Counter(
        {label: 3 for label in ALLOWED_CLASSES}
    )
    assert len({record["task_id"] for record in records}) == len(records)
    assert all(record["task_id"].startswith("VOPEN-") for record in records)
    assert all(record["source"] == "project-authored-synthetic" for record in records)


def test_prime_public_package_contains_no_sealed_release_or_private_task_markers() -> None:
    text_paths = [
        path
        for path in PACKAGE_ROOT.rglob("*")
        if path.is_file() and path.suffix in {".py", ".json", ".md", ".toml"}
    ]
    assert text_paths
    joined = "\n".join(path.read_text(encoding="utf-8") for path in text_paths)
    for marker in FORBIDDEN_RELEASE_MARKERS:
        assert marker not in joined
    assert "not the qualified SRE v4 private benchmark" in joined


def test_prime_public_scoring_is_exact_and_format_tolerant_without_reward_stuffing() -> None:
    scoring = _load_scoring_module()
    assert scoring.score_prediction('{"causal_class":"capacity"}', "capacity") == 1.0
    assert scoring.score_prediction("capacity", "capacity") == 1.0
    assert scoring.score_prediction("The answer is capacity", "capacity") == 0.0
    assert scoring.score_prediction('{"causal_class":"capacity","extra":"regression"}', "capacity") == 1.0
    assert scoring.score_prediction('{"causal_class":"regression"}', "capacity") == 0.0
    assert scoring.score_prediction("capacity regression infrastructure transient", "capacity") == 0.0


def test_prime_public_python_sources_compile() -> None:
    for path in MODULE_ROOT.glob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
