from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_identity_script_passes() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/verify_release_identity.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["status"] == "release_identity_consistent"
    assert payload["version"] == "0.11.0"
    assert payload["tag"] == "v0.11.0"
    assert payload["license"] == "Apache-2.0"


def test_pyproject_packages_root_license() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    assert project["version"] == "0.11.0"
    assert project["license"] == {"file": "LICENSE"}
    assert (ROOT / "LICENSE").exists()


def test_release_portability_identities_are_complete() -> None:
    payload = json.loads(
        (ROOT / "release/0.11.0/PORTABILITY_IDENTITIES.json").read_text(encoding="utf-8")
    )
    assert payload["veritas_version"] == "0.11.0"
    assert payload["release_tag"] == "v0.11.0"
    assert payload["portable_manifest_id"].startswith("PENV-")
    assert payload["portable_qualification_evidence_id"].startswith("PEVID-")
    assert payload["hud_package_id"].startswith("PPKG-")
    assert payload["prime_package_id"].startswith("PPKG-")
    assert payload["sre_release"]["private_task_count"] == 30
    assert payload["proof_assertions"]["canonical_reward_parity"] is True
    assert payload["proof_assertions"]["same_task_seed_same_state"] is True
