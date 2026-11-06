"""TrainLab developer evidence tests use constructed claims only, never actual science."""

import json
import tempfile
import unittest
from pathlib import Path

from forge_data.core import ForgeError
from forge_data.evidence_receipt import (
    MAX_RECEIPT_BYTES,
    validate_evidence,
    validate_evidence_file,
)


def constructed_receipt():
    return {
        "schema": "trainlab.developer_evidence.v0.1",
        "experiment_id": "CONSTRUCTED-no-fit",
        "track": "TAC_100K",
        "qualification": "NOT_QUALIFIED",
        "source": {
            "kind": "CONSTRUCTED_FIXTURE",
            "dataset_id": "constructed-quickstart-not-real",
            "publisher_id": None,
            "original_sha256": None,
            "release_manifest_sha256": None,
            "rights_review": "NOT_VERIFIED",
            "point_in_time_review": "CONSTRUCTED_CHECK",
            "split_review": "CONSTRUCTED_CHECK",
        },
        "training": {
            "status": "NOT_RUN",
            "model_commit": None,
            "learned_parameters": None,
            "checkpoint_sha256": None,
            "optimizer_rng_replay_sha256": None,
            "data_split_identity": None,
            "train_tokens": None,
            "train_updates": None,
            "tuning_budget": None,
            "baselines": [],
        },
        "device": {
            "status": "NOT_RUN",
            "model": None,
            "os": None,
            "export_format": None,
            "operator_support": None,
            "numerical_max_abs_error": None,
            "p50_ms": None,
            "p95_ms": None,
            "peak_ram_mb": None,
            "energy_mj": None,
            "airplane_mode": None,
            "network_trace_sha256": None,
            "state_replay": None,
            "delivery_sha256": None,
            "local_stages": None,
            "remote_fallback": None,
        },
        "veritas": {
            "status": "NOT_RUN",
            "report_sha256": None,
            "protected_test_authorized": False,
            "independent_review": False,
        },
    }


def internal_candidate():
    r = constructed_receipt()
    r["source"].update(
        kind="AUTHENTIC_CANDIDATE",
        publisher_id="publisher:NOT_VERIFIED",
        original_sha256="a" * 64,
        rights_review="REVIEW_PENDING",
        point_in_time_review="INTERNAL_CHECK",
        split_review="INTERNAL_CHECK",
    )
    r["training"].update(
        status="INTERNAL_MEASURED",
        model_commit="abc123abc123",
        learned_parameters=100_000,
        checkpoint_sha256="b" * 64,
        optimizer_rng_replay_sha256="c" * 64,
        data_split_identity="candidate-split-1",
        train_tokens=1000,
        train_updates=100,
        tuning_budget=0,
        baselines=[
            {
                "name": "GRU-fixture",
                "learned_parameters": 100_500,
                "data_split_identity": "candidate-split-1",
                "train_tokens": 1000,
                "train_updates": 100,
                "tuning_budget": 0,
            }
        ],
    )
    r["device"].update(
        status="INTERNAL_PHYSICAL_MEASURED",
        model="CONSTRUCTED_Samsung A07",
        os="Android 16",
        export_format="ONNX",
        operator_support=True,
        numerical_max_abs_error=0.001,
        p50_ms=10.0,
        p95_ms=20.0,
        peak_ram_mb=64,
        energy_mj=2.3,
        airplane_mode=True,
        network_trace_sha256="d" * 64,
        state_replay=True,
        delivery_sha256="e" * 64,
        local_stages={
            key: True
            for key in (
                "input",
                "preprocessing",
                "embeddings",
                "inference",
                "persistent_state",
                "output",
                "speech_if_used",
            )
        },
        remote_fallback=False,
    )
    r["veritas"]["status"] = "REVIEW_PENDING"
    return r


class ReceiptTest(unittest.TestCase):
    def test_constructed_receipt_does_not_promote(self):
        result = validate_evidence(constructed_receipt())
        self.assertEqual(result["structural_validation"], "PASS")
        self.assertEqual(result["training_claim"], "NOT_RUN")
        self.assertEqual(result["scientific_qualification"], "NOT_QUALIFIED")
        self.assertEqual(result["hardware_qualification"], "NOT_QUALIFIED")
        self.assertEqual(result["commercial_release"], "NOT_AUTHORIZED")
        self.assertNotIn("experiment_id", result)

    def test_claimed_internal_measurements_remain_unverified(self):
        result = validate_evidence(internal_candidate())
        self.assertEqual(result["training_claim"], "INTERNAL_MEASURED")
        self.assertEqual(result["device_claim"], "INTERNAL_PHYSICAL_MEASURED")
        self.assertEqual(result["source_rights"], "NOT_INDEPENDENTLY_VERIFIED")
        self.assertEqual(result["scientific_qualification"], "NOT_QUALIFIED")
        self.assertEqual(result["hardware_qualification"], "NOT_QUALIFIED")

    def test_constructed_cannot_claim_authentic_measurement(self):
        r = constructed_receipt()
        r["training"] = internal_candidate()["training"]
        with self.assertRaises(ForgeError):
            validate_evidence(r)

    def test_cannot_promote_by_changing_qualification(self):
        for status in ("INDEPENDENTLY_QUALIFIED", "PASS", "READY", True):
            with self.subTest(status=status):
                r = constructed_receipt()
                r["qualification"] = status
                with self.assertRaises(ForgeError):
                    validate_evidence(r)

    def test_cannot_claim_veritas_independence_from_json(self):
        for key, value in (
            ("status", "INDEPENDENTLY_QUALIFIED"),
            ("protected_test_authorized", True),
            ("independent_review", True),
            ("report_sha256", "a" * 64),
        ):
            with self.subTest(key=key):
                r = constructed_receipt()
                r["veritas"][key] = value
                with self.assertRaises(ForgeError):
                    validate_evidence(r)

    def test_rejects_orphaned_not_run_evidence(self):
        for section, key, value in (
            ("training", "checkpoint_sha256", "a" * 64),
            ("training", "learned_parameters", 100_000),
            ("device", "p95_ms", 10),
            ("device", "airplane_mode", True),
        ):
            with self.subTest(section=section, key=key):
                r = constructed_receipt()
                r[section][key] = value
                with self.assertRaises(ForgeError):
                    validate_evidence(r)

    def test_authentic_candidate_needs_original_source_metadata(self):
        r = internal_candidate()
        r["source"]["original_sha256"] = None
        with self.assertRaises(ForgeError):
            validate_evidence(r)

    def test_constructed_source_cannot_forge_rights(self):
        r = constructed_receipt()
        r["source"]["rights_review"] = "INDEPENDENTLY_REVIEWED"
        with self.assertRaises(ForgeError):
            validate_evidence(r)

    def test_baseline_parameter_and_budget_matching(self):
        for key, value in (
            ("learned_parameters", 102000),
            ("data_split_identity", "different"),
            ("train_tokens", 999),
            ("train_updates", 101),
            ("tuning_budget", 1),
        ):
            with self.subTest(key=key):
                r = internal_candidate()
                r["training"]["baselines"][0][key] = value
                with self.assertRaises(ForgeError):
                    validate_evidence(r)

    def test_tac_100k_internal_claim_requires_explicit_baseline(self):
        r = internal_candidate()
        r["training"]["baselines"] = []
        with self.assertRaisesRegex(ForgeError, "baseline controls"):
            validate_evidence(r)

    def test_research_100k_budget(self):
        for bad in (94999, 105001, True, 100000.5):
            with self.subTest(bad=bad):
                r = internal_candidate()
                r["training"]["learned_parameters"] = bad
                r["training"]["baselines"] = []
                with self.assertRaises(ForgeError):
                    validate_evidence(r)

    def test_measured_device_requires_complete_local_pipeline(self):
        for key in (
            "input",
            "preprocessing",
            "embeddings",
            "inference",
            "persistent_state",
            "output",
            "speech_if_used",
        ):
            with self.subTest(stage=key):
                r = internal_candidate()
                r["device"]["local_stages"][key] = False
                with self.assertRaises(ForgeError):
                    validate_evidence(r)

    def test_fallback_and_airplane_mode_fail_closed(self):
        for field, value in (
            ("remote_fallback", True),
            ("remote_fallback", None),
            ("airplane_mode", False),
            ("state_replay", False),
            ("network_trace_sha256", None),
            ("energy_mj", None),
            ("operator_support", False),
            ("numerical_max_abs_error", float("nan")),
            ("p95_ms", 1.0),
        ):
            with self.subTest(field=field):
                r = internal_candidate()
                r["device"][field] = value
                with self.assertRaises(ForgeError):
                    validate_evidence(r)

    def test_strict_top_level_and_unknown_fields(self):
        r = constructed_receipt()
        r["verified"] = True
        with self.assertRaises(ForgeError):
            validate_evidence(r)

    def test_file_rejects_duplicate_keys_and_nonfinite_numbers(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "receipt.json"
            for body in ('{"schema":"x","schema":"y"}', '{"bad": NaN}'):
                p.write_text(body)
                with self.assertRaises(ForgeError):
                    validate_evidence_file(p)

    def test_file_rejects_oversize_and_returns_redacted_result(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "receipt.json"
            p.write_bytes(b" " * (MAX_RECEIPT_BYTES + 1))
            with self.assertRaises(ForgeError):
                validate_evidence_file(p)
            p.write_text(json.dumps(constructed_receipt()), encoding="utf-8")
            result = validate_evidence_file(p)
            self.assertNotIn("constructed-quickstart-not-real", json.dumps(result))
            self.assertEqual(result["source_classification"], "CONSTRUCTED_FIXTURE")


if __name__ == "__main__":
    unittest.main()
