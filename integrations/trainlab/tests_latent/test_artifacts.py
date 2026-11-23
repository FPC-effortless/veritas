import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from trainlab.latent.artifacts import (
    decode_result,
    encode_result,
    freeze,
    load_inputs,
    plan_identity,
    resolve,
    seal_bundle,
    validate_plan,
    verify_bundle,
)
from trainlab.runner import LabError


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        np.save(self.root / "input.npy", np.arange(12).reshape(4, 3))
        self.plan = {
            "schema": "trainlab.latent-plan.v1",
            "title": "constructed",
            "identities": {key: "a" * 64 for key in ("model", "dataset", "code", "configuration")},
            "artifacts": {"vectors": {"path": "input.npy", "sha256": "a" * 64, "kind": "npy"}},
            "jobs": [
                {
                    "id": "geometry",
                    "operation": "geometry.latent_geometry",
                    "args": [{"artifact": "vectors"}],
                }
            ],
            "budget": {"max_calls": 10, "max_seconds": 30},
        }

    def test_freeze_and_stale_input_falsifier(self):
        plan = freeze(self.plan, self.root, self.root / "plan.json")
        self.assertEqual(load_inputs(plan, self.root)["vectors"].shape, (4, 3))
        np.save(self.root / "input.npy", np.zeros((4, 3)))
        with self.assertRaisesRegex(LabError, "hash"):
            load_inputs(plan, self.root)

    def test_plan_change_requires_new_identity(self):
        plan = freeze(self.plan, self.root, self.root / "plan.json")
        plan["jobs"][0]["operation"] = "geometry.tsne_projection"
        with self.assertRaisesRegex(LabError, "configuration"):
            validate_plan(plan)

    def test_forward_dependency_and_duplicate_job_rejected(self):
        self.plan["jobs"][0]["args"] = [{"result": "later"}]
        self.plan["identities"]["configuration"] = plan_identity(self.plan)
        with self.assertRaisesRegex(LabError, "earlier"):
            validate_plan(self.plan)
        self.plan["jobs"][0]["args"] = []
        self.plan["jobs"] *= 2
        self.plan["identities"]["configuration"] = plan_identity(self.plan)
        with self.assertRaisesRegex(LabError, "duplicate"):
            validate_plan(self.plan)

    def test_object_arrays_and_symlink_inputs_rejected(self):
        np.save(self.root / "input.npy", np.array([{"secret": 1}], dtype=object))
        plan = freeze(self.plan, self.root, self.root / "plan.json")
        with self.assertRaises(ValueError):
            load_inputs(plan, self.root)
        (self.root / "link.npy").symlink_to(self.root / "input.npy")
        self.plan["artifacts"]["vectors"]["path"] = "link.npy"
        with self.assertRaisesRegex(LabError, "symlink"):
            freeze(self.plan, self.root, self.root / "another.json")

    def test_result_roundtrip_and_tamper_falsifiers(self):
        value = ({"metric": 0.125}, {"coordinates": np.arange(6).reshape(3, 2)})
        encoded = encode_result(value, self.root, "result")
        decoded = decode_result(encoded, self.root)
        np.testing.assert_array_equal(decoded[1]["coordinates"], value[1]["coordinates"])
        pin = seal_bundle(self.root, plan_sha256="a" * 64, implementation={}, state="COMPLETE")
        self.assertEqual(verify_bundle(self.root, pin)["state"], "COMPLETE")
        (self.root / "unexpected.txt").write_text("unbound")
        with self.assertRaisesRegex(LabError, "inventory"):
            verify_bundle(self.root, pin)
        (self.root / "unexpected.txt").unlink()
        (self.root / "SHA256SUMS").write_text("wrong")
        with self.assertRaisesRegex(LabError, "checksum"):
            verify_bundle(self.root, pin)

    def test_nonfinite_results_rejected(self):
        for value in (float("nan"), np.array([float("inf")])):
            with self.assertRaises(LabError):
                encode_result(value, self.root, "nonfinite")

    def test_multiple_array_capture_reencoding_is_independent_of_dictionary_order(self):
        value = {"z": np.arange(3), "a": {"second": np.arange(5), "first": np.arange(2)}}
        encoded = encode_result(value, self.root, "capture")
        reloaded = json.loads(json.dumps(encoded, sort_keys=True))
        target = self.root / "replay"
        target.mkdir()
        repeated = encode_result(decode_result(reloaded, self.root), target, "capture")
        self.assertEqual(repeated, encoded)
        for path in target.glob("*.npy"):
            self.assertEqual(path.read_bytes(), (self.root / path.name).read_bytes())

    def test_reference_shaped_result_metadata_remains_ordinary_data(self):
        metadata = {
            "$array": "display label",
            "$bytes": "not encoded bytes",
            "$mapping": {"$bytes": "literal nested value"},
            "numbers": np.arange(3),
        }
        encoded = encode_result(metadata, self.root, "metadata")
        recovered = decode_result(encoded, self.root)
        self.assertEqual(recovered["$mapping"], metadata["$mapping"])
        self.assertEqual(recovered["$array"], "display label")
        np.testing.assert_array_equal(recovered["numbers"], np.arange(3))

    def test_numpy_parser_uses_the_same_bytes_that_were_authenticated(self):
        plan = freeze(self.plan, self.root, self.root / "plan.json")
        path = self.root / "input.npy"
        original = path.read_bytes()
        original_load = np.load

        def replace_path_during_parse(source, **kwargs):
            np.save(path, np.full((4, 3), 99))
            try:
                return original_load(source, **kwargs)
            finally:
                path.write_bytes(original)

        with patch("trainlab.latent.artifacts.np.load", side_effect=replace_path_during_parse):
            actual = load_inputs(plan, self.root)["vectors"]
        np.testing.assert_array_equal(actual, np.arange(12).reshape(4, 3))

    def test_json_parser_uses_authenticated_bytes_and_rejects_duplicate_keys(self):
        path = self.root / "input.json"
        path.write_text('{"measurement":1}')
        self.plan["artifacts"]["vectors"].update(path="input.json", kind="json")
        plan = freeze(self.plan, self.root, self.root / "plan.json")
        original = path.read_bytes()
        original_loads = json.loads

        def replace_path_during_parse(payload, **kwargs):
            path.write_text('{"measurement":99}')
            try:
                return original_loads(payload, **kwargs)
            finally:
                path.write_bytes(original)

        with patch("trainlab.latent.artifacts.json.loads", side_effect=replace_path_during_parse):
            self.assertEqual(load_inputs(plan, self.root)["vectors"], {"measurement": 1})
        path.write_text('{"measurement":1,"measurement":99}')
        other = freeze(self.plan, self.root, self.root / "other.json")
        with self.assertRaisesRegex(LabError, "invalid JSON"):
            load_inputs(other, self.root)

    def test_byte_and_literal_arguments_keep_reference_shaped_metadata_literal(self):
        args = [{"bytes_hex": "4142"}, {"literal": {"result": "not_a_job", "capability": "data"}}]
        self.plan["jobs"][0]["args"] = args
        plan = freeze(self.plan, self.root, self.root / "plan.json")
        self.assertEqual(resolve(plan["jobs"][0]["args"], {}, {}), [b"AB", args[1]["literal"]])
        encoded = encode_result(b"AB", self.root, "bytes")
        self.assertEqual(decode_result(encoded, self.root), b"AB")

    def test_oversized_array_header_rejected_before_numpy_load(self):
        payload = io.BytesIO()
        np.lib.format.write_array_header_1_0(
            payload, {"shape": (100_000_000,), "fortran_order": False, "descr": "<f8"}
        )
        (self.root / "input.npy").write_bytes(payload.getvalue())
        plan = freeze(self.plan, self.root, self.root / "plan.json")
        with patch(
            "trainlab.latent.artifacts.np.load", side_effect=AssertionError("unbounded load")
        ):
            with self.assertRaisesRegex(LabError, "oversized"):
                load_inputs(plan, self.root)


if __name__ == "__main__":
    unittest.main()
