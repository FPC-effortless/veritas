from __future__ import annotations

import base64
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge_data.core import canonical
from forge_data.workbench import ForgeWorkspace


def fixture():
    spec = {
        "dataset_id": "Constructed operations",
        "source_id": "fixture/machines",
        "source_version": "v1",
        "adapter": "operations-jsonl",
        "license_id": "fixture-only",
        "provenance_uri": "https://example.invalid/constructed",
        "ai_use_allowed": True,
        "redistribution_allowed": True,
        "privacy_reviewed": True,
        "split_salt": "gui-frozen-v1",
    }
    rows = [
        {
            "episode_id": f"ep-{i}",
            "subject_id": f"machine-{i}",
            "record_id": f"row-{i}",
            "observed_at": "2026-01-01T10:00:00Z",
            "available_at": "2026-01-01T10:00:01Z",
            "observation": {"temperature": i, "tag": " =2+2"},
            "action": {
                "performed_at": "2026-01-01T10:00:00Z",
                "available_at": "2026-01-01T10:00:01Z",
                "payload": {"do_not_export": "secret-action"},
            },
            "outcome": {
                "status": "constructed",
                "verified": False,
                "available_at": "2026-01-02T10:00:00Z",
                "value": i * 2 + 1,
            },
        }
        for i in range(30)
    ]
    return {
        "source_name": "constructed.jsonl",
        "source_jsonl": "".join(canonical(row).decode() for row in rows),
        "spec": spec,
    }


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = ForgeWorkspace(self.root / "forge", None)
        self.addCleanup(self.app.close)

    def request(self, route, body=None, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-TrainLab-Token"] = self.app.token
        return self.app.dispatch(
            "GET" if body is None else "POST",
            "/api/forge/" + route,
            headers,
            b"" if body is None else canonical(body),
        )

    def create(self, payload=None):
        status, job, _ = self.request("releases", fixture() if payload is None else payload)
        self.assertEqual(status, 202, job)
        self.app.active.result(timeout=10)
        status, state, _ = self.request("state")
        self.assertEqual(status, 200)
        self.assertEqual(state["jobs"][0]["status"], "succeeded", state["jobs"][0])
        return next(row for row in state["releases"] if row["id"] == job["release_id"])

    def projection(self, record, **changes):
        value = {
            "id": record["id"],
            "split": "train",
            "fields": ["temperature"],
            "cutoff": "2026-01-01T10:00:01Z",
            "target_cutoff": None,
            "offset": 0,
            "limit": 10,
        }
        return {**value, **changes}

    def test_create_persists_release_and_reopens_with_same_pin(self):
        record = self.create()
        self.assertEqual(record["records"], 30)
        self.assertEqual(record["split_records"], {"train": 24, "validation": 3, "test": 3})
        status, detail, _ = self.request("detail?id=" + record["id"])
        self.assertEqual(status, 200)
        self.assertEqual(detail["manifest_sha256"], record["manifest_sha256"])
        self.assertEqual(set(detail["profile"]["fields"]), {"temperature", "tag"})
        self.app.close()
        reopened = ForgeWorkspace(self.root / "forge", None)
        self.addCleanup(reopened.close)
        _, state, _ = reopened.dispatch("GET", "/api/forge/state", {})
        self.assertEqual(state["releases"][0]["manifest_sha256"], record["manifest_sha256"])

    def test_preview_applies_both_clocks_feature_selection_and_withholds_test(self):
        record = self.create()
        status, page, _ = self.request("preview", self.projection(record))
        self.assertEqual(status, 200, page)
        self.assertEqual(len(page["rows"]), 10)
        self.assertEqual(page["total"], 24)
        self.assertTrue(all(row["target"] is None for row in page["rows"]))
        status, page, _ = self.request(
            "preview", self.projection(record, target_cutoff="2026-01-02T10:00:00Z")
        )
        self.assertEqual(status, 200)
        self.assertTrue(all(row["target"]["verified"] is False for row in page["rows"]))
        self.assertTrue(
            all(
                set(row["features"]) == {"temperature"} and "action" not in row
                for row in page["rows"]
            )
        )
        self.assertEqual(self.request("preview", self.projection(record, split="test"))[0], 400)
        status, page, _ = self.request(
            "preview", self.projection(record, cutoff="2026-01-01T10:00:00Z")
        )
        self.assertEqual(status, 200)
        self.assertEqual(page["total"], 0)

    def test_export_uses_projection_and_escapes_csv_formula_values(self):
        record = self.create()
        request = {**self.projection(record, fields=["tag"]), "format": "csv"}
        status, data, mime = self.request("export", request)
        self.assertEqual(status, 200)
        rows = list(csv.DictReader(io.StringIO(data.decode())))
        self.assertEqual(len(rows), 24)
        self.assertEqual(rows[0]["feature.tag"], "' =2+2")
        self.assertNotIn("secret-action", data.decode())
        request["format"] = "jsonl"
        status, data, _ = self.request("export", request)
        self.assertEqual(status, 200)
        self.assertEqual(len(data.splitlines()), 24)
        self.assertTrue(all(json.loads(line)["target"] is None for line in data.splitlines()))

    def test_missing_rights_invalid_spec_and_paths_do_not_create_a_release(self):
        for field, value in [
            ("ai_use_allowed", False),
            ("privacy_reviewed", False),
            ("source_id", ""),
        ]:
            with self.subTest(field=field):
                payload = fixture()
                payload["spec"][field] = value
                self.assertEqual(self.request("releases", payload)[0], 400)
        payload = fixture()
        payload["source_name"] = "../outside.jsonl"
        self.assertEqual(self.request("releases", payload)[0], 400)
        self.assertEqual(self.request("detail?id=../outside")[0], 400)
        self.assertFalse(list((self.root / "forge/releases").iterdir()))

    def test_invalid_rows_are_failed_jobs_and_source_does_not_become_release(self):
        payload = fixture()
        payload["source_jsonl"] = "{invalid json}\n"
        status, job, _ = self.request("releases", payload)
        self.assertEqual(status, 202)
        self.app.active.result(timeout=10)
        _, state, _ = self.request("state")
        self.assertEqual(state["jobs"][0]["status"], "failed")
        self.assertTrue(state["jobs"][0]["error"])
        self.assertEqual(state["releases"], [])

    def test_tampering_is_detected_and_verification_failure_persists(self):
        record = self.create()
        file = self.root / "forge/releases" / record["id"] / "train.jsonl"
        file.write_bytes(file.read_bytes() + b" ")
        self.assertEqual(self.request("preview", self.projection(record))[0], 400)
        status, _, _ = self.request("verify", {"id": record["id"]})
        self.assertEqual(status, 202)
        self.app.active.result(timeout=10)
        _, state, _ = self.request("state")
        self.assertEqual(state["releases"][0]["integrity"], "failed")
        self.assertEqual(state["jobs"][0]["status"], "failed")

    def test_mutations_require_token_and_bounded_declared_payload(self):
        self.assertEqual(self.request("releases", fixture(), token=False)[0], 403)
        payload = fixture()
        payload["command"] = ["touch", "/tmp/not-allowed"]
        self.assertEqual(self.request("releases", payload)[0], 400)
        payload = fixture()
        payload["source_jsonl"] = "x" * (8 * 1024 * 1024 + 1)
        self.assertEqual(self.request("releases", payload)[0], 400)

    def test_compare_validates_distinct_releases_and_reports_differences(self):
        first = self.create()
        payload = fixture()
        payload["spec"]["source_version"] = "v2"
        second = self.create(payload)
        status, value, _ = self.request("compare", {"ids": [first["id"], second["id"]]})
        self.assertEqual(status, 200)
        self.assertIn("source_version", value["differences"])
        self.assertEqual(len(value["releases"]), 2)
        self.assertEqual(self.request("compare", {"ids": [first["id"], first["id"]]})[0], 400)

    def test_static_assets_and_health_do_not_expose_filesystem_or_source(self):
        for path in ("/forge/", "/forge/app.js", "/forge/style.css", "/forge/shared.css"):
            self.assertEqual(self.app.dispatch("GET", path, {})[0], 200, path)
        self.assertEqual(self.app.dispatch("GET", "/forge/../../source.jsonl", {})[0], 404)
        status, health, _ = self.app.dispatch("GET", "/healthz", {})
        self.assertEqual(status, 200)
        self.assertNotIn("token", health)
        self.assertNotIn("source_jsonl", json.dumps(health))

    def test_duplicate_keys_and_excessive_nesting_are_retained_failed_jobs(self):
        duplicate = fixture()["source_jsonl"].replace(
            '"episode_id":"ep-0"', '"episode_id":"ep-0","episode_id":"ep-0"', 1
        )
        for source in (duplicate, "[" * 1200 + "0" + "]" * 1200):
            with self.subTest(source=source[:30]):
                payload = fixture()
                payload["source_jsonl"] = source
                status, job, _ = self.request("releases", payload)
                self.assertEqual(status, 202)
                self.app.active.result(timeout=10)
                _, state, _ = self.request("state")
                saved = next(item for item in state["jobs"] if item["id"] == job["id"])
                self.assertEqual(saved["status"], "failed")

    def test_robot_clock_profile_and_numeric_guard(self):
        payload = fixture()
        payload["spec"]["adapter"] = "robot-jsonl"
        rows = [
            {
                "episode_id": f"ep-{i}",
                "subject_id": f"robot-{i}",
                "record_id": f"frame-{i}",
                "time_seconds": 0,
                "available_seconds": 1,
                "frame_index": i,
                "observation": {"joint_angle": i / 10},
                "action": None,
                "outcome": None,
            }
            for i in range(12)
        ]
        payload["source_jsonl"] = "".join(canonical(row).decode() for row in rows)
        record = self.create(payload)
        _, detail, _ = self.request("detail?id=" + record["id"])
        self.assertEqual(detail["profile"]["temporal_basis"], "relative_seconds")
        request = self.projection(record, fields=["joint_angle"], cutoff="1")
        self.assertEqual(self.request("preview", request)[0], 200)
        request["cutoff"] = True
        self.assertEqual(self.request("preview", request)[0], 400)

    def test_explorer_field_list_is_bounded(self):
        payload = fixture()
        rows = [json.loads(line) for line in payload["source_jsonl"].splitlines()]
        for row in rows:
            row["observation"] = {f"feature_{i}": i for i in range(150)}
        payload["source_jsonl"] = "".join(canonical(row).decode() for row in rows)
        record = self.create(payload)
        _, detail, _ = self.request("detail?id=" + record["id"])
        self.assertEqual(len(detail["profile"]["fields"]), 128)
        self.assertTrue(detail["profile"]["fields_truncated"])

    def test_unavailable_workspace_reports_degraded_health(self):
        self.create()
        with patch("forge_data.workbench.MAX_RELEASES", 0):
            self.assertEqual(self.app.dispatch("GET", "/healthz", {})[0], 503)

    def test_corrupt_activity_record_is_isolated_and_unfinished_jobs_are_not_live(self):
        identity = "a" * 32
        (self.root / "forge/jobs" / f"{identity}.json").write_text(
            json.dumps({"id": identity, "status": "failed", "name": "bad record"})
        )
        status, state, _ = self.request("state")
        self.assertEqual(status, 200)
        self.assertIn("invalid", state["jobs"][0]["error"])
        path = self.root / "forge/jobs" / f"{identity}.json"
        path.write_text(
            json.dumps(
                {
                    "id": identity,
                    "name": "Old unfinished operation",
                    "release_id": "b" * 32,
                    "status": "running",
                    "created_at": "2026-01-01T00:00:00Z",
                    "finished_at": None,
                    "error": None,
                }
            )
        )
        _, state, _ = self.request("state")
        self.assertFalse(state["jobs"][0]["active"])

    def test_base64_upload_preserves_escape_heavy_original_bytes_within_transport_bound(self):
        payload = fixture()
        row = json.loads(payload.pop("source_jsonl").splitlines()[0])
        row["observation"] = {"blob": "\\" * 3_300_000}
        source = canonical(row)
        self.assertLess(len(source), 8 * 1024 * 1024)
        payload["source_base64"] = base64.b64encode(source).decode()
        self.assertLess(len(canonical(payload)), self.app.body_limit)
        record = self.create(payload)
        status, detail, _ = self.request("detail?id=" + record["id"])
        self.assertEqual(status, 200)
        from forge_data.core import hash_bytes

        self.assertEqual(detail["manifest"]["source_sha256"], hash_bytes(source))

    def test_excessively_nested_http_json_is_a_controlled_client_error(self):
        status, _, _ = self.app.dispatch(
            "POST",
            "/api/forge/releases",
            {"Content-Type": "application/json", "X-TrainLab-Token": self.app.token},
            b"[" * 20_000 + b"0" + b"]" * 20_000,
        )
        self.assertEqual(status, 400)

    def test_atomic_write_staging_files_do_not_count_as_library_corruption(self):
        self.create()
        (self.root / "forge/metadata/.metadata-staged-write").write_text("pending")
        with patch("forge_data.workbench.MAX_RELEASES", 1):
            status, state, _ = self.request("state")
            self.assertEqual(status, 200)
            self.assertEqual(state["workspace_errors"], 0)
            self.assertEqual(len(state["releases"]), 1)


if __name__ == "__main__":
    unittest.main()
