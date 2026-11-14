import copy
import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from trainlab.diagnostic_bundle import create, export, verify
from trainlab.runner import LabError


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = {"status": "FAILED", "observations": {"bad_example": "row-1"}}
        self.raw = json.dumps(self.report).encode()
        (self.root / "report.json").write_bytes(self.raw)
        self.spec = {
            "schema": "trainlab.diagnostic-bundle-spec.v1",
            "title": "Diagnosis",
            "data_classification": "CONSTRUCTED_PUBLIC",
            "packs": [
                {
                    "id": "p",
                    "version": "1",
                    "applicability": "constructed records",
                    "dependencies": [],
                    "cost": "bounded",
                    "evidence_requirements": ["report"],
                    "limitations": ["not scientific qualification"],
                }
            ],
            "findings": [
                {
                    "id": "fault",
                    "pack_id": "p",
                    "kind": "observation",
                    "summary": "Known fault",
                    "status": "FAILED",
                    "evidence": {"path": "report.json", "sha256": sha(self.raw), "pointer": []},
                    "reviews": [],
                }
            ],
        }

    def build(self):
        raw = json.dumps(self.spec).encode()
        path = self.root / "spec.json"
        path.write_bytes(raw)
        out = self.root / "bundle"
        return out, create(path, sha(raw), out)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_fifo_specification_is_rejected_without_opening(self):
        path = self.root / "pipe"
        os.mkfifo(path)
        with self.assertRaises(LabError):
            create(path, "a" * 64, self.root / "bundle")

    def test_escaped_output_budget_is_checked_before_writing(self):
        item = self.spec["findings"][0]
        item["reviews"] = [
            {"reviewer": "&" * 2000, "note": "&" * 2000, "report_sha256": sha(self.raw)}
            for _ in range(8)
        ]
        self.spec["findings"] = [{**copy.deepcopy(item), "id": str(i)} for i in range(200)]
        with self.assertRaises(LabError):
            self.build()
        self.assertFalse((self.root / "bundle").exists())

    def test_typed_list_pointer(self):
        raw = json.dumps({"checks": [self.report]}).encode()
        (self.root / "report.json").write_bytes(raw)
        self.spec["findings"][0]["evidence"].update(sha256=sha(raw), pointer=["checks", True])
        with self.assertRaises(LabError):
            self.build()
        self.spec["findings"][0]["evidence"]["pointer"] = ["checks", 0]
        root, pin = self.build()
        self.assertTrue(verify(root, pin)["valid"])

    def test_roundtrip_and_zip(self):
        root, pin = self.build()
        self.assertTrue(verify(root, pin)["valid"])
        out = export(root, pin, self.root / "bundle.zip")
        with zipfile.ZipFile(out["path"]) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"index.html", "bundle.json", "manifest.json", "evidence/000.json"},
            )
            self.assertEqual(archive.read("evidence/000.json"), self.raw)
        self.assertEqual(sha(Path(out["path"]).read_bytes()), out["sha256"])

    def test_status_is_not_promoted(self):
        self.spec["findings"][0]["status"] = "TESTED"
        with self.assertRaises(LabError):
            self.build()
        self.assertFalse((self.root / "bundle").exists())

    def test_missing_and_unsupported_remain_visible(self):
        for status in ("UNSUPPORTED", "NOT_RUN"):
            self.spec["findings"].append(
                {
                    "id": status,
                    "pack_id": "p",
                    "kind": "observation",
                    "summary": "No access",
                    "status": status,
                    "evidence": None,
                    "reviews": [],
                }
            )
        root, pin = self.build()
        self.assertTrue(verify(root, pin)["valid"])
        document = json.loads((root / "bundle.json").read_text())
        self.assertEqual(
            [f["status"] for f in document["findings"]], ["FAILED", "UNSUPPORTED", "NOT_RUN"]
        )

    def test_tested_without_evidence_rejected(self):
        self.spec["findings"][0].update(status="TESTED", evidence=None)
        with self.assertRaises(LabError):
            self.build()

    def test_html_is_escaped_and_no_imported_script(self):
        hostile = '</script><img src="https://evil.example" onerror="alert(1)">'
        self.spec["title"] = hostile
        self.spec["findings"][0]["summary"] = hostile
        self.spec["findings"][0]["reviews"] = [
            {"reviewer": hostile, "note": hostile, "report_sha256": sha(self.raw)}
        ]
        root, _ = self.build()
        html = (root / "index.html").read_text()
        self.assertNotIn(hostile, html)
        self.assertIn("&lt;/script&gt;", html)
        self.assertEqual(html.count("<script>"), 1)
        self.assertIn("default-src 'none'", html)

    def test_tampering_and_extra_files(self):
        root, pin = self.build()
        (root / "extra.json").write_text("{}")
        with self.assertRaises(LabError):
            verify(root, pin)
        (root / "extra.json").unlink()
        (root / "evidence/000.json").write_text("{}")
        with self.assertRaises(LabError):
            verify(root, pin)
        with self.assertRaises(LabError):
            export(root, pin, self.root / "bad.zip")
        self.assertFalse((self.root / "bad.zip").exists())

    def test_changed_manifest_requires_new_external_pin(self):
        root, pin = self.build()
        (root / "manifest.json").write_text("{}")
        with self.assertRaises(LabError):
            verify(root, pin)

    def test_unsafe_paths(self):
        for path in (
            "../report.json",
            "/report.json",
            "a/../../report.json",
            "./report.json",
            "a//b",
            "report.json?x",
            "https://example.com",
            "C:\\report.json",
        ):
            self.spec["findings"][0]["evidence"]["path"] = path
            with self.subTest(path=path), self.assertRaises(LabError):
                self.build()

    def test_symlink_source_and_bundle_rejected(self):
        (self.root / "link.json").symlink_to(self.root / "report.json")
        self.spec["findings"][0]["evidence"]["path"] = "link.json"
        with self.assertRaises(LabError):
            self.build()
        self.spec["findings"][0]["evidence"]["path"] = "report.json"
        root, pin = self.build()
        p = root / "evidence/000.json"
        p.unlink()
        p.symlink_to(self.root / "report.json")
        with self.assertRaises(LabError):
            verify(root, pin)

    def test_stale_review_rejected(self):
        self.spec["findings"][0]["reviews"] = [
            {"reviewer": "reviewer", "note": "Reviewed", "report_sha256": "a" * 64}
        ]
        with self.assertRaises(LabError):
            self.build()

    def test_duplicate_ids_and_private_declaration(self):
        base = copy.deepcopy(self.spec)
        for mutate in (
            lambda s: s["findings"].append(copy.deepcopy(s["findings"][0])),
            lambda s: s.update(data_classification="PRIVATE"),
            lambda s: s["packs"].append(copy.deepcopy(s["packs"][0])),
        ):
            self.spec = copy.deepcopy(base)
            mutate(self.spec)
            with self.assertRaises(LabError):
                self.build()

    def test_pointer_and_source_hash_are_checked(self):
        self.spec["findings"][0]["evidence"]["pointer"] = ["absent"]
        with self.assertRaises(LabError):
            self.build()
        self.spec["findings"][0]["evidence"].update(pointer=[], sha256="a" * 64)
        with self.assertRaises(LabError):
            self.build()

    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        for raw in (
            b'{"status":"FAILED","status":"TESTED"}',
            b'{"status":"FAILED","x":NaN}',
            b"[" * 40 + b"0" + b"]" * 40,
        ):
            (self.root / "report.json").write_bytes(raw)
            self.spec["findings"][0]["evidence"]["sha256"] = sha(raw)
            with self.assertRaises(LabError):
                self.build()

    def test_no_overwrite_and_export_outside_bundle(self):
        root, pin = self.build()
        with self.assertRaises(FileExistsError):
            self.build()
        with self.assertRaises(LabError):
            export(root, pin, root / "export.zip")
        export(root, pin, self.root / "out.zip")
        with self.assertRaises(FileExistsError):
            export(root, pin, self.root / "out.zip")

    def test_manifest_boolean_size_rejected(self):
        root, _ = self.build()
        manifest = json.loads((root / "manifest.json").read_text())
        manifest["files"][0]["bytes"] = True
        raw = json.dumps(manifest).encode()
        (root / "manifest.json").write_bytes(raw)
        with self.assertRaises(LabError):
            verify(root, sha(raw))

    def test_missing_source_prevents_any_bundle_creation(self):
        (self.root / "report.json").unlink()
        with self.assertRaises(LabError):
            self.build()
        self.assertFalse((self.root / "bundle").exists())


if __name__ == "__main__":
    unittest.main()
