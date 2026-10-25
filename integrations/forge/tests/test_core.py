import json
import tempfile
import unittest
from pathlib import Path

from forge_data.core import ForgeError, normalize, point_in_time, release, verify_release

BASE = {
    "dataset_id": "fixture-not-real", "source_id": "fixture/ops",
    "source_version": "v1", "adapter": "operations-jsonl",
    "license_id": "fixture-rights", "provenance_uri": "https://example.invalid/fixture",
    "ai_use_allowed": True, "redistribution_allowed": True,
    "privacy_reviewed": True, "split_salt": "frozen-seed",
}


def operations(subject, step=0, episode=None):
    return {"episode_id": episode or f"ep-{subject}", "subject_id": subject,
            "record_id": f"{subject}-record-{step}-{episode or 'root'}",
            "observed_at": "2026-01-01T10:00:00Z",
            "available_at": "2026-01-01T10:00:01Z",
            "observation": {"temperature": 32},
            "action": {"performed_at": "2026-01-01T10:02:00Z",
                       "available_at": "2026-01-01T10:02:30Z",
                       "payload": {"type": "inspect"}},
            "outcome": {"status": "completed", "verified": False,
                        "available_at": "2026-01-01T10:04:00Z"}}


class ForgeTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.spec = self.root / "spec.json"
        self.data = self.root / "source.jsonl"
        self.spec.write_text(json.dumps(BASE))

    def write(self, rows):
        self.data.write_text("\n".join(json.dumps(x) for x in rows) + "\n")

    def test_deterministic_release_order_and_subject_isolation(self):
        rows = [operations(f"machine-{i}") for i in range(12)]
        rows.append(operations("machine-5", 1, episode="second-episode"))
        self.write(rows)
        first = release(self.data, self.spec, self.root / "first")
        self.write(list(reversed(rows)))
        second = release(self.data, self.spec, self.root / "second")
        self.assertEqual(first["file_sha256"], second["file_sha256"])
        self.assertEqual(verify_release(self.root / "first")["records"], len(rows))
        self.assertGreater(first["groups"]["test"], 0)
        self.assertGreater(first["groups"]["validation"], 0)
        for key in ("train", "validation", "test"):
            self.assertEqual((self.root / "first" / (key + ".jsonl")).read_bytes(),
                             (self.root / "second" / (key + ".jsonl")).read_bytes())
        with self.assertRaisesRegex(ForgeError, "already exists"):
            release(self.data, self.spec, self.root / "first")

    def test_point_in_time_masks_future_observation_action_outcome(self):
        row = normalize(operations("machine-1"), adapter="operations-jsonl", source_id="fixture/ops")
        self.assertIsNone(point_in_time(row, "2026-01-01T10:00:00Z"))
        early = point_in_time(row, "2026-01-01T10:00:01Z")
        self.assertIsNone(early["action"])
        self.assertIsNone(early["outcome"])
        middle = point_in_time(row, "2026-01-01T10:03:00Z")
        self.assertIsNotNone(middle["action"])
        self.assertIsNone(middle["outcome"])
        self.assertEqual(point_in_time(row, "2026-01-01T10:05:00Z")["outcome"]["status"], "completed")

    def test_fractional_timestamp_order_and_delayed_action_visibility(self):
        row = operations("machine-1")
        row["observed_at"] = "2026-01-01T10:00:00.500Z"
        row["available_at"] = "2026-01-01T10:00:00.750Z"
        row["action"]["available_at"] = "2026-01-01T10:03:30.001Z"
        normalized = normalize(row, adapter="operations-jsonl", source_id="fixture/ops")
        self.assertIsNone(point_in_time(normalized, "2026-01-01T10:00:00.500Z"))
        self.assertIsNone(point_in_time(normalized, "2026-01-01T10:03:30.000Z")["action"])
        self.assertIsNotNone(point_in_time(normalized, "2026-01-01T10:03:30.001Z")["action"])

    def test_robot_adapter_preserves_missing_outcome_and_duplicate_sensor_values(self):
        def frame(idx):
            return {"episode_id": "ep-1", "subject_id": "robot-1",
                    "record_id": f"ep-1/{idx}", "frame_index": idx,
                    "time_seconds": float(idx), "available_seconds": float(idx),
                    "observation": {"state": [0.0, 1.0]},
                    "action": None, "outcome": None}
        self.spec.write_text(json.dumps(dict(BASE, adapter="robot-jsonl")))
        self.write([frame(0), frame(1)])
        m = release(self.data, self.spec, self.root / "robot")
        self.assertEqual(m["records"]["train"], 2)
        row = json.loads((self.root / "robot" / "train.jsonl").read_text().splitlines()[0])
        self.assertEqual(row["outcome"]["status"], "unknown")
        self.assertFalse(row["outcome"]["verified"])
        self.assertIsNone(point_in_time(row, 0.0)["outcome"])

    def test_source_rights_and_temporal_fail_closed(self):
        rows = [operations("machine-1")]
        self.write(rows)
        for field in ("ai_use_allowed", "redistribution_allowed", "privacy_reviewed"):
            self.spec.write_text(json.dumps(dict(BASE, **{field: False})))
            with self.assertRaises(ForgeError):
                release(self.data, self.spec, self.root / f"denied-{field}")
        self.spec.write_text(json.dumps(BASE))
        rows[0]["available_at"] = "2025-12-31T09:00:00Z"
        self.write(rows)
        with self.assertRaisesRegex(ForgeError, "cannot precede"):
            release(self.data, self.spec, self.root / "invalid")
        self.assertFalse((self.root / "invalid").exists())

    def test_duplicate_identity_unknown_value_and_tamper(self):
        self.write([operations("machine-1"), operations("machine-1")])
        with self.assertRaisesRegex(ForgeError, "duplicate source record"):
            release(self.data, self.spec, self.root / "duplicate")
        bad = operations("machine-1")
        bad["outcome"] = {"status": "unknown", "verified": False, "value": "guessed"}
        self.write([bad])
        with self.assertRaisesRegex(ForgeError, "unknown outcomes"):
            release(self.data, self.spec, self.root / "invented")
        self.write([operations("machine-1")])
        release(self.data, self.spec, self.root / "ok")
        with (self.root / "ok" / "train.jsonl").open("a") as f:
            f.write("\n")
        with self.assertRaisesRegex(ForgeError, "hash mismatch"):
            verify_release(self.root / "ok")

    def test_malformed_nan_and_missing_timestamp(self):
        row = operations("machine-1")
        row["observed_at"] = "2026-01-01T10:00:00"
        self.write([row])
        with self.assertRaisesRegex(ForgeError, "UTC offset"):
            release(self.data, self.spec, self.root / "bad-time")
        row = operations("machine-1")
        row["observation"]["temperature"] = float("nan")
        self.write([row])
        with self.assertRaisesRegex(ForgeError, "Out of range float values"):
            release(self.data, self.spec, self.root / "bad-number")


if __name__ == "__main__":
    unittest.main()
