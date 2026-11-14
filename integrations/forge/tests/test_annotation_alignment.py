import io
import tempfile
import unittest
import wave
from pathlib import Path

from forge_data.annotation_alignment import audit
from forge_data.core import ForgeError, canonical, hash_bytes
from test_semantic_audit import png


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        audio = io.BytesIO()
        with wave.open(audio, "wb") as output:
            output.setparams((2, 2, 8000, 0, "NONE", "not compressed"))
            output.writeframes(b"\0" * 16)
        self.features = {
            "picture": self.media("p.png", png()),
            "boxes": [[0, 0, 1, 1]],
            "audio": self.media("a.wav", audio.getvalue()),
            "segments": [[0, 2], [2, 4]],
        }
        self.rules = [
            {"media": "picture", "annotations": "boxes", "format": "png"},
            {"media": "audio", "annotations": "segments", "format": "wav"},
        ]

    def media(self, name, data):
        (self.assets / name).write_bytes(data)
        return {"path": name, "sha256": hash_bytes(data)}

    def run_audit(self, *, split="validation", **kwargs):
        view = {
            "schema": "forge.diagnostic-input.v1",
            "feature_fields": list(self.features),
            "group_fields": [],
            "rows": [{"id": "test-row", "split": split, "features": self.features}],
        }
        spec = {"schema": "forge.annotation-alignment-rules.v1", "rules": self.rules}
        view_bytes, spec_bytes = canonical(view), canonical(spec)
        path, rules_path = self.root / "view.json", self.root / "rules.json"
        path.write_bytes(view_bytes)
        rules_path.write_bytes(spec_bytes)
        return audit(
            path,
            rules_path,
            **{
                "sha256": hash_bytes(view_bytes),
                "rules_sha256": hash_bytes(spec_bytes),
                "media_root": self.assets,
                **kwargs,
            },
        )

    def test_valid_edges_and_stereo_frame_count(self):
        result = self.run_audit()
        self.assertEqual(result["status"], "TESTED")
        self.assertEqual(result["coverage"]["boxes"]["annotation_count"], 1)
        self.assertEqual(result["coverage"]["segments"]["annotation_count"], 2)
        self.assertEqual(result["findings"], [])

    def test_rejects_malformed_or_outside_annotations_without_copying_data(self):
        self.features["boxes"] = [[False, 0, 1, 1], [0, 0, 1, 2]]
        self.features["segments"] = [[3, 3], [0, 5]]
        result = self.run_audit(max_findings=3)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["findings_total"], 4)
        self.assertEqual(result["findings_omitted"], 1)
        self.assertEqual(
            [f["reason"] for f in result["findings"]],
            ["INVALID_COORDINATES", "OUTSIDE_MEDIA", "INVALID_COORDINATES"],
        )
        self.assertNotIn("coordinates", result["findings"][0])

    def test_partial_budget_never_masks_a_failed_row(self):
        result = self.run_audit(max_media_bytes=0)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["unavailable"], {"MEDIA_BUDGET": 2})
        self.features["boxes"] = [[1, 0, 0, 1]]
        failed = self.run_audit(max_media_bytes=0)
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(failed["findings"][0]["reason"], "INVALID_COORDINATES")

    def test_changed_media_pin_or_test_rows_are_rejected(self):
        (self.assets / "p.png").write_bytes(b"changed")
        result = self.run_audit()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["findings"][0]["reason"], "MEDIA_HASH")
        with self.assertRaisesRegex(ForgeError, "train/validation"):
            self.run_audit(split="test", max_rows=0)
        with self.assertRaisesRegex(ForgeError, "rule"):
            self.run_audit(rules_sha256="a" * 64)
