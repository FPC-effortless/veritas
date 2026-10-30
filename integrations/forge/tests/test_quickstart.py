"""Constructed-only developer quickstart regression; not model or source qualification."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class QuickstartTests(unittest.TestCase):
    def test_local_quickstart_preserves_scientific_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        source = str(root / "src")
        env["PYTHONPATH"] = source + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        result = subprocess.run(
            [sys.executable, str(root / "examples" / "offline_quickstart.py")],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        output = json.loads(result.stdout)
        self.assertEqual(output["demo"], "CONSTRUCTED_ONLY")
        self.assertEqual(output["records"], 12)
        self.assertEqual(output["subject_split_isolation"], "PASS_CONSTRUCTED")
        self.assertEqual(output["point_in_time_masking"], "PASS_CONSTRUCTED")
        self.assertEqual(output["rights"], "FIXTURE_DECLARATIONS_NOT_VERIFIED")
        self.assertEqual(output["scientific_qualification"], "NOT_PERFORMED")
        self.assertEqual(output["model_training"], "NOT_PERFORMED")
        self.assertEqual(output["physical_offline_inference"], "NOT_RUN")
        self.assertEqual(output["trainlab_receipt_structural"], "PASS")
        self.assertEqual(output["trainlab_receipt_science"], "NOT_QUALIFIED")
        self.assertEqual(output["trainlab_receipt_device"], "NOT_QUALIFIED")


if __name__ == "__main__":
    unittest.main()
