import io
import struct
import tempfile
import unittest
import wave
import zlib
from pathlib import Path

from forge_data.core import ForgeError, canonical, hash_bytes
from forge_data.semantic_audit import audit


def png(scanline=b"\x00\x80"):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scanline))
        + chunk(b"IEND", b"")
    )


class SemanticAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.asset = self.root / "assets"
        self.asset.mkdir()
        audio = io.BytesIO()
        with wave.open(audio, "wb") as writer:
            writer.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            writer.writeframes(b"\x00\x00" * 4)
        media = {
            "txt": ("utf8", b"a valid text sample"),
            "json": ("json", b'{"value":7}'),
            "csv": ("csv", b"feature,label\n1,a\n"),
            "png": ("png", png()),
            "wav": ("wav", audio.getvalue()),
        }
        features = {"distance": 2, "unit": "m", "category": "north", "available": True}
        self.rules = {
            "distance": {
                "type": "number",
                "min": 0,
                "max": 10,
                "unit": {"field": "unit", "symbol": "m"},
            },
            "category": {"type": "string", "enum": ["north", "south"]},
            "available": {"type": "boolean"},
        }
        for name, (kind, raw) in media.items():
            features[name] = self.file(name, raw)
            self.rules[name] = {"type": "file", "format": kind}
        self.rows = [
            {"id": name, "split": split, "features": dict(features)}
            for name, split in (("first", "train"), ("second", "validation"))
        ]

    def file(self, name, raw):
        (self.asset / name).write_bytes(raw)
        return {"path": name, "sha256": hash_bytes(raw)}

    def run_audit(self, **kwargs):
        view = {
            "schema": "forge.diagnostic-input.v1",
            "feature_fields": ["unit", *self.rules],
            "group_fields": [],
            "rows": self.rows,
        }
        raw = canonical(view)
        path = self.root / "view.json"
        path.write_bytes(raw)
        rule_bytes = canonical({"schema": "forge.semantic-rules.v1", "fields": self.rules})
        rules = self.root / "rules.json"
        rules.write_bytes(rule_bytes)
        pins = {"sha256": hash_bytes(raw), "rules_sha256": hash_bytes(rule_bytes)}
        return audit(path, rules, **(pins | kwargs))

    def test_clean_metadata_and_five_real_media_types(self):
        report = self.run_audit(media_root=self.asset)
        self.assertEqual(report["status"], "TESTED")
        self.assertEqual(report["findings_total"], 0)
        self.assertEqual(report["media"]["unique_checks"], 5)
        self.assertEqual(report["coverage"]["distance"]["checks"]["unit"]["checked"], 2)

    def test_missing_capability_and_partial_do_not_pass(self):
        self.assertEqual(self.run_audit()["status"], "INCONCLUSIVE")
        self.assertEqual(
            self.run_audit(media_root=self.asset, max_rows=1)["status"], "INCONCLUSIVE"
        )
        self.assertEqual(self.run_audit(media_root=self.asset, max_rows=0)["status"], "NOT_RUN")
        report = self.run_audit(media_root=self.asset, max_media_bytes=0)
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual(report["media"]["bytes_read"], 0)

    def test_known_faults_are_localized_even_when_output_truncated(self):
        self.rows[0]["features"].update(
            distance=-1,
            unit="cm",
            category="east",
            available=1,
            txt={"path": "../view.json", "sha256": "a" * 64},
        )
        self.rows[1]["features"].pop("distance")
        report = self.run_audit(media_root=self.asset, max_findings=4)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["findings_total"], 6)
        self.assertEqual(report["findings_omitted"], 2)
        self.assertTrue(all(row["row"]["id"] == "first" for row in report["findings"]))

    def test_content_and_pins_are_checked(self):
        self.rows[0]["features"].update(
            png=self.file("bad.png", png(b"\x05\x80")),
            csv=self.file("bad.csv", b"a,b\n1\n"),
            json=self.file("bad.json", b'{"x":NaN}'),
            wav=self.file("bad.wav", b"RIFF"),
            txt=self.file("bad.txt", b"\xff"),
        )
        (self.asset / "png").write_bytes(b"changed")
        report = self.run_audit(media_root=self.asset)
        reasons = {f["reason"] for f in report["findings"]}
        self.assertEqual(reasons, {"MEDIA_FORMAT", "MEDIA_HASH"})
        self.assertEqual(report["findings_total"], 6)

    def test_symlinks_and_incorrect_pins_rejected(self):
        (self.asset / "linked").symlink_to(self.asset / "json")
        self.rows[0]["features"]["json"] = {"path": "linked", "sha256": "a" * 64}
        self.assertEqual(
            self.run_audit(media_root=self.asset)["findings"][0]["reason"], "MEDIA_PATH"
        )
        with self.assertRaises(ForgeError):
            self.run_audit(rules_sha256="b" * 64)
        self.rows[1]["split"] = "test"
        with self.assertRaises(ForgeError):
            self.run_audit(max_rows=1)

    def test_incompatible_rules_and_booleans_in_numeric_bounds_rejected(self):
        for rule in (
            {"type": "string", "min": 1},
            {"type": "number", "min": True},
            {"type": "integer", "min": 2, "max": 1},
            {"type": "file"},
        ):
            self.rules["distance"] = rule
            with self.subTest(rule=rule), self.assertRaises(ForgeError):
                self.run_audit()
