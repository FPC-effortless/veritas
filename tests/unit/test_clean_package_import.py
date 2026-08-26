from __future__ import annotations

import subprocess
import sys


def test_companyworld_imports_in_fresh_interpreter():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from investigation_world.companyworld import "
                "SequentialCompanyWorldRuntime, SEQUENTIAL_DISTRIBUTION_VERSION; "
                "assert SEQUENTIAL_DISTRIBUTION_VERSION == '0.1.0'; "
                "assert SequentialCompanyWorldRuntime is not None"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
