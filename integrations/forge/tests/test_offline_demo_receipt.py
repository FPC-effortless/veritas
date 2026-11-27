"""Adversarial tests for untrusted Forge offline-demo receipts."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from forge_data.core import ForgeError
from forge_data.offline_demo_receipt import (
    LIMIT_MS,
    validate_offline_demo,
    validate_offline_demo_files,
)

COMMIT = "a" * 40


def valid_pair():
    receipt = {
        "schema": "forge.offline-demo-measurement.v1",
        "result": "PASS",
        "commit": COMMIT,
        "measurement": {
            "elapsed_ms": 108,
            "limit_ms": LIMIT_MS,
            "within_ten_minutes": True,
            "timer": (
                "time.perf_counter_ns around child interpreter startup, imports and quickstart"
            ),
            "scope": "excludes checkout, runner provisioning and container-image acquisition",
        },
        "environment": {
            "child_environment_keys": [
                "PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED", "PYTHONNOUSERSITE",
                "PYTHONPATH", "TMPDIR",
            ],
            "secret_environment_forwarding": "DISABLED_BY_ALLOWLIST",
        },
        "network": {
            "enforcement": "EXTERNAL_SANDBOX_REQUIRED",
            "note": (
                "This measurer does not disable OS networking; the CI workflow runs it in a "
                "Docker --network=none container."
            ),
        },
        "child_exit_code": 0,
        "failure_reason": None,
        "quickstart": {
            "demo": "CONSTRUCTED_ONLY",
            "records": 12,
            "subject_split_isolation": "PASS_CONSTRUCTED",
            "point_in_time_masking": "PASS_CONSTRUCTED",
            "rights": "FIXTURE_DECLARATIONS_NOT_VERIFIED",
            "authentic_dataset": "NOT_USED",
            "scientific_qualification": "NOT_PERFORMED",
            "model_training": "NOT_PERFORMED",
            "outcomes": "UNKNOWN_UNVERIFIED_ONLY",
            "hidden_labels": "NOT_USED",
            "physical_offline_inference": "NOT_RUN",
            "trainlab_receipt_structural": "PASS",
            "trainlab_receipt_science": "NOT_QUALIFIED",
            "trainlab_receipt_device": "NOT_QUALIFIED",
        },
        "qualification": {
            "scientific": "NOT_QUALIFIED",
            "source_rights": "NOT_VERIFIED",
            "physical_device": "NOT_RUN",
            "commercial_release": "NOT_AUTHORIZED",
        },
    }
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    execution = {
        "schema": "forge.offline-demo-ci-execution.v1",
        "run_id": "123456789",
        "source_commit": COMMIT,
        "container_image": "python:3.13-slim",
        "container_image_id": "sha256:" + "b" * 64,
        "network_mode": "none",
        "container_root_filesystem": "read-only",
        "checkout_mount": "read-only",
        "temporary_storage": "isolated tmpfs and receipt mount",
        "secrets_passed_to_container": False,
        "model_training": "NOT_PERFORMED",
        "hidden_labels": "NOT_USED",
        "demo_elapsed_ms": 108,
        "demo_limit_ms": LIMIT_MS,
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "scientific_qualification": "NOT_PERFORMED",
        "physical_offline_inference": "NOT_RUN",
    }
    execution_bytes = (json.dumps(execution, sort_keys=True, indent=2) + "\n").encode()
    return receipt, execution, receipt_bytes, execution_bytes


class OfflineDemoReceiptTest(unittest.TestCase):
    def verify(self, mutate_receipt=None, mutate_execution=None):
        receipt, execution, raw, execution_raw = valid_pair()
        if mutate_receipt:
            mutate_receipt(receipt)
            raw = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
            execution["receipt_sha256"] = hashlib.sha256(raw).hexdigest()
            execution["demo_elapsed_ms"] = receipt["measurement"]["elapsed_ms"]
            execution_raw = (json.dumps(execution, sort_keys=True, indent=2) + "\n").encode()
        if mutate_execution:
            mutate_execution(execution)
            execution_raw = (json.dumps(execution, sort_keys=True, indent=2) + "\n").encode()
        return validate_offline_demo(raw, execution_raw, COMMIT)

    def test_valid_pair_is_only_a_redacted_nonqualifying_structural_pass(self):
        result = self.verify()
        self.assertEqual(result["structural_validation"], "PASS")
        self.assertEqual(result["scientific_qualification"], "NOT_QUALIFIED")
        self.assertEqual(result["source_rights"], "NOT_VERIFIED")
        self.assertEqual(result["physical_device"], "NOT_RUN")
        self.assertEqual(result["external_developer_acceptance"], "NOT_ESTABLISHED")
        self.assertEqual(result["commercial_release"], "NOT_AUTHORIZED")
        self.assertNotIn("run_id", result)

    def test_wrong_expected_commit_rejected(self):
        receipt, execution, raw, execution_raw = valid_pair()
        with self.assertRaisesRegex(ForgeError, "expected source commit"):
            validate_offline_demo(raw, execution_raw, "c" * 40)

    def test_elapsed_time_over_limit_rejected(self):
        with self.assertRaisesRegex(ForgeError, "ten-minute limit"):
            self.verify(lambda r: r["measurement"].update(
                elapsed_ms=LIMIT_MS + 1, within_ten_minutes=True
            ))

    def test_secret_environment_key_rejected(self):
        with self.assertRaisesRegex(ForgeError, "safe allowlist"):
            self.verify(lambda r: r["environment"]["child_environment_keys"].append(
                "GITHUB_TOKEN"
            ))

    def test_network_mode_must_be_none(self):
        with self.assertRaisesRegex(ForgeError, "network_mode"):
            self.verify(mutate_execution=lambda e: e.update(network_mode="bridge"))

    def test_root_and_checkout_must_be_read_only(self):
        for key in ("container_root_filesystem", "checkout_mount"):
            with self.subTest(key=key):
                with self.assertRaises(ForgeError):
                    self.verify(mutate_execution=lambda e, k=key: e.update({k: "read-write"}))

    def test_secrets_cannot_be_passed_to_container(self):
        with self.assertRaisesRegex(ForgeError, "secrets_passed_to_container"):
            self.verify(mutate_execution=lambda e: e.update(secrets_passed_to_container=True))

    def test_training_or_hidden_labels_cannot_be_claimed(self):
        for key, value in (("model_training", "PERFORMED"), ("hidden_labels", "USED")):
            with self.subTest(key=key):
                with self.assertRaises(ForgeError):
                    self.verify(mutate_execution=lambda e, k=key, v=value: e.update({k: v}))

    def test_receipt_hash_binding_rejects_tampering(self):
        with self.assertRaisesRegex(ForgeError, "byte binding mismatch"):
            self.verify(mutate_execution=lambda e: e.update(receipt_sha256="0" * 64))

    def test_measurement_cannot_self_promote_qualification(self):
        with self.assertRaisesRegex(ForgeError, "NOT_QUALIFIED"):
            self.verify(lambda r: r["qualification"].update(
                scientific="INDEPENDENTLY_QUALIFIED"
            ))

    def test_exact_schema_rejects_unknown_or_missing_fields(self):
        with self.assertRaisesRegex(ForgeError, "required-only fields mismatch"):
            self.verify(lambda r: r.update(extra="not allowed"))

    def test_file_loader_rejects_duplicate_keys_and_nonfinite_values(self):
        _, _, _, execution_raw = valid_pair()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rp, ep = root / "receipt.json", root / "execution.json"
            ep.write_bytes(execution_raw)
            rp.write_text(
                '{"schema":"forge.offline-demo-measurement.v1","schema":"forged"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ForgeError, "duplicate JSON"):
                validate_offline_demo_files(rp, ep, COMMIT)
            rp.write_text('{"x":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ForgeError, "non-finite"):
                validate_offline_demo_files(rp, ep, COMMIT)

    def test_file_loader_rejects_oversized_receipt(self):
        _, _, _, execution_raw = valid_pair()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rp, ep = root / "receipt.json", root / "execution.json"
            rp.write_bytes(b" " * (256 * 1024 + 1))
            ep.write_bytes(execution_raw)
            with self.assertRaisesRegex(ForgeError, "exceeds size limit"):
                validate_offline_demo_files(rp, ep, COMMIT)

    def test_cli_emits_redacted_verdict(self):
        _, _, receipt_raw, execution_raw = valid_pair()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rp, ep = root / "receipt.json", root / "execution.json"
            rp.write_bytes(receipt_raw)
            ep.write_bytes(execution_raw)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            result = subprocess.run(
                [sys.executable, "-m", "forge_data", "verify-offline-demo",
                 "--receipt", str(rp), "--execution", str(ep), "--commit", COMMIT],
                env=env, capture_output=True, text=True, check=True, timeout=15,
            )
            output = json.loads(result.stdout)
            self.assertEqual(output["structural_validation"], "PASS")
            self.assertEqual(output["commercial_release"], "NOT_AUTHORIZED")
            self.assertNotIn("run_id", output)


if __name__ == "__main__":
    unittest.main()
