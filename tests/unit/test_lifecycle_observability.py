"""Invented development examples; no private benchmark data."""
import copy
import unittest

from investigation_world.benchmark.lifecycle_observability import audit_pair, replay


def pair(gap=(), after=(), before=(), repeated=False):
    events = [
        {"op": "set", "key": "a", "value": "old"},
        *before,
        {"op": "copy", "key": "f", "source": "a"},
        {"op": "delete", "key": "a"},
        *([{"op": "delete", "key": "a"}] if repeated else []),
        *gap,
        {"op": "set", "key": "a", "value": "new"},
        *after,
    ]
    left = {"schema": "woyengi.lifecycle.v1", "keys": ["a", "f", "q", "u"],
            "events": events, "composed_keys": ["f", "q"]}
    right = copy.deepcopy(left)
    right["events"][1 + len(before)]["op"] = "link"
    return left, right


SNAPSHOT = {"op": "copy", "key": "q", "source": "f"}


class ObservabilityTests(unittest.TestCase):
    def test_unobserved_gap(self):
        result = audit_pair(*pair(), "delete_recreate")
        self.assertTrue(result["strict_primary_transition"])
        self.assertEqual([r["interventions"][0]["changed_keys"] for r in result["rows"]], [[], []])

    def test_observed_gap_preserved(self):
        result = audit_pair(*pair([SNAPSHOT]), "delete_recreate")
        left, right = result["rows"]
        self.assertEqual(left["interventions"][0]["changed_keys"], [])
        intervention = right["interventions"][0]
        self.assertEqual(intervention["changed_keys"], ["q"])
        self.assertEqual(intervention["changed_composed_keys"], ["q"])
        self.assertTrue(intervention["absence_snapshots"][0]["preserved_at_own_final_query"])

    def test_failed_copy_clears_old_destination(self):
        left, right = pair([SNAPSHOT], before=[{"op": "set", "key": "q", "value": "occupied"}])
        self.assertIsNone(replay(right)["q"])
        self.assertEqual(replay(left)["q"], "old")
        self.assertTrue(audit_pair(left, right, "delete_recreate")["rows"][1]
                        ["interventions"][0]["absence_snapshots"][0]["preserved_at_own_final_query"])

    def test_overwritten_snapshot_is_only_transient(self):
        result = audit_pair(*pair([SNAPSHOT], [{"op": "set", "key": "q", "value": "new"}]),
                            "delete_recreate")
        intervention = result["rows"][1]["interventions"][0]
        self.assertEqual(intervention["changed_keys"], [])
        self.assertFalse(intervention["absence_snapshots"][0]["preserved_at_own_final_query"])

    def test_later_snapshot_not_credited_to_earlier_one(self):
        result = audit_pair(*pair([SNAPSHOT, SNAPSHOT]), "delete_recreate")
        witnesses = result["rows"][1]["interventions"][0]["absence_snapshots"]
        self.assertEqual([w["preserved_at_own_final_query"] for w in witnesses], [False, True])

    def test_redundant_deletes_need_joint_ablation(self):
        result = audit_pair(*pair([SNAPSHOT], repeated=True), "delete_recreate")
        self.assertFalse(result["strict_primary_transition"])
        tests = result["rows"][1]["interventions"]
        self.assertEqual([t["changed_keys"] for t in tests], [[], [], ["q"]])

    def test_cycle_is_not_missing_source(self):
        left, right = pair([
            {"op": "link", "key": "q", "source": "q"},
            {"op": "copy", "key": "u", "source": "q"},
        ])
        result = audit_pair(left, right, "delete_recreate")
        self.assertIsNone(replay(right)["q"])
        self.assertEqual(result["rows"][1]["interventions"][0]["absence_snapshots"], [])

    def test_different_missing_root_is_not_witness(self):
        result = audit_pair(*pair([{"op": "copy", "key": "q", "source": "u"}]),
                            "delete_recreate")
        self.assertEqual(result["rows"][1]["interventions"][0]["absence_snapshots"], [])

    def test_self_copy_resolves_before_write(self):
        memory = pair()[0]
        memory["events"] = [{"op": "set", "key": "q", "value": "old"},
                            {"op": "copy", "key": "q", "source": "q"}]
        self.assertEqual(replay(memory)["q"], "old")
        memory["events"] = [{"op": "link", "key": "q", "source": "u"},
                            {"op": "copy", "key": "q", "source": "q"},
                            {"op": "set", "key": "u", "value": "new"}]
        self.assertIsNone(replay(memory)["q"])

    def test_full_and_composed_effects_are_separate(self):
        left, right = pair([SNAPSHOT])
        left["composed_keys"] = right["composed_keys"] = ["f"]
        test = audit_pair(left, right, "delete_recreate")["rows"][1]["interventions"][0]
        self.assertEqual(test["changed_keys"], ["q"])
        self.assertEqual(test["changed_composed_keys"], [])

    def test_rejects_uncontrolled_pair_and_unbounded_ablation(self):
        left, right = pair()
        right["events"][-1]["value"] = "different"
        with self.assertRaises(ValueError):
            audit_pair(left, right, "delete_recreate")
        left, right = pair(gap=[{"op": "delete", "key": "a"}] * 4)
        with self.assertRaises(ValueError):
            audit_pair(left, right, "delete_recreate")

    def test_validates_input_and_omitted_event(self):
        left, right = pair()
        with self.assertRaises(ValueError):
            replay(left, [0])
        with self.assertRaises(ValueError):
            replay(left, [True])
        right["events"][0]["value"] = None
        with self.assertRaises(ValueError):
            replay(right)

    def test_pair_order_and_input_purity(self):
        left, right = pair([SNAPSHOT])
        before = copy.deepcopy([left, right])
        forward = audit_pair(left, right, "delete_recreate")
        reverse = audit_pair(right, left, "delete_recreate")
        self.assertEqual(forward["rows"], list(reversed(reverse["rows"])))
        self.assertEqual([left, right], before)

    def test_renaming_and_nop_do_not_create_sensitivity(self):
        left, right = pair([SNAPSHOT])
        original = audit_pair(left, right, "delete_recreate")
        for memory in (left, right):
            memory["keys"] = ["renamed-" + k for k in memory["keys"]]
            memory["composed_keys"] = ["renamed-" + k for k in memory["composed_keys"]]
            for event in memory["events"]:
                for field in ("key", "source"):
                    if field in event:
                        event[field] = "renamed-" + event[field]
            memory["events"].insert(0, {"op": "nop"})
        renamed = audit_pair(left, right, "delete_recreate")
        self.assertEqual(original["focal_index"] + 1, renamed["focal_index"])
        self.assertEqual(renamed["rows"][1]["interventions"][0]["changed_keys"], ["renamed-q"])

    def test_none_is_not_a_payload_token(self):
        left, right = pair([SNAPSHOT])
        for memory in (left, right):
            memory["events"][0]["value"] = "UNKNOWN"
        self.assertEqual(replay(left)["q"], "UNKNOWN")
        self.assertIsNone(replay(right)["q"])
        self.assertTrue(audit_pair(left, right, "delete_recreate")["rows"][1]
                        ["interventions"][0]["absence_snapshots"][0]["preserved_at_own_final_query"])

    def test_rejects_replaced_focal_binding(self):
        # Preserve the original difference elsewhere, observe a replacement live
        # edge in both arms, then restore the difference. This is not the focal
        # COPY protection contrast this narrow diagnostic supports.
        left, right = pair([
            {"op": "copy", "key": "q", "source": "f"},
            {"op": "link", "key": "f", "source": "a"},
            {"op": "copy", "key": "u", "source": "f"},
        ], [{"op": "copy", "key": "f", "source": "q"}])
        with self.assertRaises(ValueError):
            audit_pair(left, right, "delete_recreate")


if __name__ == "__main__":
    unittest.main()
