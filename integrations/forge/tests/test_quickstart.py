"""Constructed-only developer quickstart regression; not model or source qualification."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class QuickstartTests(unittest.TestCase):
    def test_local_quickstart_preserves_scientific_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        source = str(root / "src")
        env["PYTHONPATH"] = source + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
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
        self.assertEqual(output["outcomes"], "UNKNOWN_UNVERIFIED_ONLY")
        self.assertEqual(output["hidden_labels"], "NOT_USED")
        self.assertEqual(output["physical_offline_inference"], "NOT_RUN")
        self.assertEqual(output["trainlab_receipt_structural"], "PASS")
        self.assertEqual(output["trainlab_receipt_science"], "NOT_QUALIFIED")
        self.assertEqual(output["trainlab_receipt_device"], "NOT_QUALIFIED")


    def test_measured_demo_receipt_bounds_time_and_does_not_forward_secrets(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="forge-demo-receipt-") as temporary:
            receipt_path = Path(temporary) / "receipt.json"
            env = dict(os.environ)
            env["GITHUB_TOKEN"] = "constructed-test-value-not-a-secret"
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "examples" / "measure_offline_quickstart.py"),
                    "--receipt",
                    str(receipt_path),
                    "--commit",
                    "a" * 40,
                ],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            receipt = json.loads(result.stdout)
            self.assertEqual(json.loads(receipt_path.read_text(encoding="utf-8")), receipt)
            self.assertEqual(receipt["schema"], "forge.offline-demo-measurement.v1")
            self.assertEqual(receipt["result"], "PASS")
            self.assertEqual(receipt["commit"], "a" * 40)
            self.assertGreaterEqual(receipt["measurement"]["elapsed_ms"], 0)
            self.assertLessEqual(receipt["measurement"]["elapsed_ms"], 600_000)
            self.assertTrue(receipt["measurement"]["within_ten_minutes"])
            self.assertEqual(
                receipt["environment"]["secret_environment_forwarding"],
                "DISABLED_BY_ALLOWLIST",
            )
            self.assertNotIn("GITHUB_TOKEN", receipt["environment"]["child_environment_keys"])
            self.assertIn("PYTHONNOUSERSITE", receipt["environment"]["child_environment_keys"])
            self.assertEqual(
                receipt["network"]["enforcement"],
                "EXTERNAL_SANDBOX_REQUIRED",
            )
            self.assertEqual(receipt["quickstart"]["model_training"], "NOT_PERFORMED")
            self.assertEqual(receipt["quickstart"]["outcomes"], "UNKNOWN_UNVERIFIED_ONLY")
            self.assertEqual(receipt["quickstart"]["hidden_labels"], "NOT_USED")
            self.assertEqual(receipt["quickstart"]["scientific_qualification"], "NOT_PERFORMED")
            self.assertEqual(receipt["quickstart"]["physical_offline_inference"], "NOT_RUN")



if __name__ == "__main__":
    unittest.main()
