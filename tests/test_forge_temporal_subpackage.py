"""Run isolated Forge package tests through the existing Veritas Python CI."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_forge_temporal_isolated_suite() -> None:
    repo = Path(__file__).resolve().parents[1]
    package_dir = repo / "integrations" / "forge"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(package_dir / "src")
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(package_dir / "tests"), "-v"],
        cwd=repo,
        env=env,
        check=True,
        timeout=30,
    )
