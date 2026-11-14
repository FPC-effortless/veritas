import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trainlab.research_diagnostics import Adapter, Diagnostic, Workbench
from trainlab.runner import LabError
from trainlab.state_diagnostics import (
    lifecycle,
    minimize_failure,
    restore_isolation,
    verify_repair,
    write_intervention,
)


class Store:
    def __init__(self, fault=None):
        self.data = {}
        self.fault = fault

    def reset(self):
        self.data = {}

    def update(self, event):
        if event["op"] == "set":
            self.data[event["key"]] = event["value"]
        elif event["op"] == "delete" and self.fault != "stale":
            self.data.pop(event["key"], None)
        if self.fault == "collateral":
            self.data.pop("b", None)

    def query(self, key):
        return self.data.get(key)

    def snapshot(self):
        return self.data if self.fault == "alias" else copy.deepcopy(self.data)

    def restore(self, snapshot):
        self.data = snapshot if self.fault == "alias" else copy.deepcopy(snapshot)


INITIAL = [{"op": "set", "key": "a", "value": 1}, {"op": "set", "key": "b", "value": 2}]
QUERIES = [{"id": "a", "input": "a"}, {"id": "b", "input": "b"}]
STEPS = [
    {
        "id": "delete",
        "event": {"op": "delete", "key": "a"},
        "expected": {"a": None, "b": 2},
        "touched": ["a"],
    }
]


def panel(value=1, *, group="fresh"):
    return [
        {
            "id": group + "-1",
            "group": group,
            "expected": 1,
            "before": {"status": "observed", "value": value},
            "after": {"status": "observed", "value": 1},
        }
    ]


def repair_inputs():
    return {
        "panels": {"fresh": panel(0), "regression": panel(group="regression")},
        "required_ids": {"fresh": ["fresh-1"], "regression": ["regression-1"]},
        "freshness": {
            "evaluation_sha256": "a" * 64,
            "frozen_before_evaluation": True,
            "used_for_selection": False,
        },
        "selection_groups": ["train"],
        "hypotheses": [{"id": "h", "description": "stale delete"}],
        "interventions": [
            {
                "hypothesis_id": "h",
                "observation": "write omitted changed answer",
                "evidence_sha256": "b" * 64,
            }
        ],
    }


class StateTests(unittest.TestCase):
    def test_partial_query_failure_retains_observed_wrong_answer(self):
        for failure_at in (2, 4):

            class BrokenQuery(Store):
                calls = 0

                def query(self, key):
                    self.calls += 1
                    if self.calls == failure_at:
                        raise RuntimeError("query failed")
                    return 9 if self.calls == failure_at - 1 else super().query(key)

            result, _ = self.execute(self.lifecycle, store=BrokenQuery())
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["observations"]["interruption"], "RuntimeError")
            self.assertTrue(result["observations"]["errors"])
            if failure_at == 2:
                self.assertEqual(result["observations"]["baseline"], {"a": 9})
            else:
                self.assertEqual(result["observations"]["records"][0]["after"], {"a": 9})
                self.assertIsNone(result["observations"]["records"][0]["conditional_damage_rate"])

    def test_null_expected_map_rejected_before_operations(self):
        for initial_expected, steps in [
            (None, STEPS),
            ({"a": 1, "b": 2}, [{**STEPS[0], "expected": None}]),
        ]:

            def probe(ctx):
                with self.assertRaises(LabError):
                    lifecycle(
                        ctx,
                        initial=INITIAL,
                        initial_expected=initial_expected,
                        queries=QUERIES,
                        steps=steps,
                        supported_ops=["set", "delete"],
                    )
                return {"status": "TESTED"}

            _, report = self.execute(probe)
            self.assertEqual(report["attempts"], [])

    def test_final_query_overrun_is_inconclusive(self):
        for function, count in [
            (self.lifecycle, 4),
            (self.restore, 18),
            (
                lambda ctx: write_intervention(
                    ctx, initial=INITIAL, event=STEPS[0]["event"], queries=QUERIES
                ),
                4,
            ),
        ]:
            clock, calls = [0], [0]

            class Slow(Store):
                def query(self, key):
                    calls[0] += 1
                    if calls[0] == count:
                        clock[0] = 31_000_000_000
                    return super().query(key)

            with patch(
                "trainlab.research_diagnostics.perf_counter_ns", side_effect=lambda: clock[0]
            ):
                result, report = self.execute(function, store=Slow(), peer=Slow())
            self.assertEqual(result["status"], "INCONCLUSIVE")
            self.assertEqual(report["session"]["budget_exhausted"], "WALL_TIME")

    def test_noop_peer_mutation_rejected(self):
        def probe(ctx):
            with self.assertRaises(LabError):
                restore_isolation(
                    ctx,
                    initial=INITIAL,
                    queries=QUERIES,
                    expected={"a": 1, "b": 2},
                    mutation={"op": "set", "key": "a", "value": 3},
                    mutated_expected={"a": 3, "b": 2},
                    peer_mutation={"op": "set", "key": "a", "value": 1},
                    peer_mutated_expected={"a": 1, "b": 2},
                )
            return {"status": "TESTED"}

        _, report = self.execute(probe)
        self.assertEqual(report["attempts"], [])

    def test_fresh_and_regression_cannot_reuse_row_identity(self):
        data = repair_inputs()
        data["panels"]["regression"][0]["id"] = "fresh-1"
        data["required_ids"]["regression"] = ["fresh-1"]
        result = verify_repair(**data)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["observations"]["overlapping_panel_ids"], ["fresh-1"])

    def execute(self, fn, *, store=None, peer=None, calls=200, missing=(), mutates=False):
        store, peer = store or Store(), peer or Store()
        operations = {
            name: getattr(store, name) for name in ("reset", "update", "query", "snapshot")
        }
        operations.update(
            {
                "peer_" + name: getattr(peer, name)
                for name in ("reset", "update", "query", "restore")
            }
        )
        for name in missing:
            operations.pop(name)
        adapter = Adapter(
            "store", operations, {"persists": "dict", "query_mutates": mutates, "reset": "empty"}
        )
        result = {}

        def check(ctx):
            result.update(fn(ctx))
            return {"status": result["status"], "summary": "state probe", "metrics": {}}

        with tempfile.TemporaryDirectory() as tmp:
            workbench = Workbench(
                adapter,
                {k: "a" * 64 for k in ("model", "dataset", "code", "configuration")},
                Path(tmp) / "report",
                max_calls=calls,
                required_phases=("answer",),
            )
            workbench.run([Diagnostic("state", "1", (), check, "test")])
            return result, workbench.report

    def lifecycle(self, ctx):
        return lifecycle(
            ctx,
            initial=INITIAL,
            initial_expected={"a": 1, "b": 2},
            queries=QUERIES,
            steps=STEPS,
            supported_ops=["set", "delete"],
        )

    def restore(self, ctx):
        return restore_isolation(
            ctx,
            initial=INITIAL,
            queries=QUERIES,
            expected={"a": 1, "b": 2},
            mutation={"op": "set", "key": "a", "value": 3},
            mutated_expected={"a": 3, "b": 2},
            peer_mutation={"op": "set", "key": "b", "value": 4},
            peer_mutated_expected={"a": 1, "b": 4},
        )

    def test_lifecycle_clean_and_stale_delete(self):
        clean, _ = self.execute(self.lifecycle)
        self.assertEqual(clean["status"], "TESTED")
        bad, _ = self.execute(self.lifecycle, store=Store("stale"))
        self.assertEqual(bad["status"], "FAILED")
        self.assertEqual(bad["observations"]["records"][0]["wrong"], ["a"])

    def test_collateral_is_conditioned_on_previously_correct(self):
        class Damage(Store):
            def update(self, event):
                super().update(event)
                if event["op"] == "delete":
                    self.data["b"] = 7

        bad, _ = self.execute(self.lifecycle, store=Damage())
        row = bad["observations"]["records"][0]
        self.assertEqual(row["previously_correct_untouched"], ["b"])
        self.assertEqual(row["newly_damaged"], ["b"])
        self.assertEqual(row["conditional_damage_rate"], 1)
        old_wrong, _ = self.execute(self.lifecycle, store=Store("collateral"))
        self.assertIsNone(old_wrong["observations"]["records"][0]["conditional_damage_rate"])

    def test_budget_does_not_produce_clean_state(self):
        result, _ = self.execute(self.lifecycle, calls=2)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["observations"]["completed_steps"], 0)

    def test_missing_capabilities_and_mutating_queries_unsupported(self):
        for kwargs in ({"missing": ["query"]}, {"mutates": True}):
            result, report = self.execute(self.lifecycle, **kwargs)
            self.assertEqual(result["status"], "UNSUPPORTED")
            self.assertEqual(report["attempts"], [])

    def test_expected_change_outside_touched_rejected(self):
        bad = copy.deepcopy(STEPS)
        bad[0]["touched"] = []

        def probe(ctx):
            with self.assertRaises(LabError):
                lifecycle(
                    ctx,
                    initial=INITIAL,
                    initial_expected={"a": 1, "b": 2},
                    queries=QUERIES,
                    steps=bad,
                    supported_ops=["set", "delete"],
                )
            return {"status": "TESTED"}

        _, report = self.execute(probe)
        self.assertEqual(report["attempts"], [])

    def test_write_omission_retains_pairs_and_replay_cost(self):
        result, report = self.execute(
            lambda ctx: write_intervention(
                ctx, initial=INITIAL, event=STEPS[0]["event"], queries=QUERIES
            )
        )
        self.assertEqual(result["observations"]["changed_query_ids"], ["a"])
        self.assertEqual(len(report["attempts"]), 11)

    def test_interrupted_write_pair_is_not_complete(self):
        result, _ = self.execute(
            lambda ctx: write_intervention(
                ctx, initial=INITIAL, event=STEPS[0]["event"], queries=QUERIES
            ),
            calls=7,
        )
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertIsNone(result["observations"]["changed_query_ids"])

    def test_restore_and_source_peer_aliases(self):
        good, _ = self.execute(self.restore)
        self.assertEqual(good["status"], "TESTED")
        bad, _ = self.execute(self.restore, store=Store("alias"), peer=Store("alias"))
        self.assertEqual(bad["status"], "FAILED")
        self.assertIn("peer_after_source_mutation", bad["observations"]["failures"])

    def test_restore_mutation_of_source_is_checked_after_both_restores(self):
        source = Store()

        class Corrupt(Store):
            def restore(self, snapshot):
                super().restore(snapshot)
                source.data.clear()

        result, _ = self.execute(self.restore, store=source, peer=Corrupt())
        self.assertIn("source_after_restore", result["observations"]["failures"])

    def test_missing_snapshot_is_unsupported(self):
        result, _ = self.execute(self.restore, missing=["snapshot"])
        self.assertEqual(result["status"], "UNSUPPORTED")

    def test_reducer_minimizes_and_preserves_failure(self):
        events = [{"op": "noise"}, {"op": "set"}, {"op": "noise"}, {"op": "delete"}]

        def predicate(rows):
            return [r["op"] for r in rows if r["op"] != "noise"] == ["set", "delete"]

        result = minimize_failure(events, predicate)
        self.assertEqual(result["observations"]["candidate"], [{"op": "set"}, {"op": "delete"}])
        self.assertTrue(result["observations"]["one_deletion_minimal"])

    def test_reducer_budget_retains_last_confirmed_failure(self):
        result = minimize_failure(INITIAL, lambda rows: bool(rows), max_calls=1)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["observations"]["candidate"], INITIAL)
        self.assertFalse(result["observations"]["one_deletion_minimal"])

    def test_reducer_unknown_exception_and_nonfailing_initial(self):
        for predicate in (lambda rows: None, lambda rows: 1, lambda rows: 1 / 0):
            result = minimize_failure(INITIAL, predicate)
            self.assertEqual(result["status"], "INCONCLUSIVE")
            self.assertIsNone(result["observations"]["candidate"])
        self.assertEqual(minimize_failure(INITIAL, lambda rows: False)["status"], "FAILED")

    def test_reducer_copies_mutable_inputs(self):
        events = copy.deepcopy(INITIAL)

        def predicate(rows):
            rows.clear()
            return True

        result = minimize_failure(events, predicate)
        self.assertEqual(events, INITIAL)
        self.assertEqual(result["observations"]["candidate"], [])

    def test_repair_requires_gain_and_regression_panel(self):
        self.assertEqual(verify_repair(**repair_inputs())["status"], "TESTED")
        data = repair_inputs()
        data["panels"]["fresh"] = panel(1)
        self.assertEqual(verify_repair(**data)["status"], "FAILED")
        data = repair_inputs()
        data["panels"]["regression"][0]["after"]["value"] = 0
        self.assertEqual(verify_repair(**data)["status"], "FAILED")

    def test_repair_missing_unknown_failed_and_group_overlap(self):
        for status in ("failed", "missing"):
            data = repair_inputs()
            data["panels"]["fresh"][0]["after"]["status"] = status
            self.assertEqual(verify_repair(**data)["status"], "INCONCLUSIVE")
        data = repair_inputs()
        data["panels"]["fresh"] = []
        self.assertEqual(verify_repair(**data)["status"], "INCONCLUSIVE")
        data = repair_inputs()
        data["selection_groups"] = ["fresh"]
        self.assertEqual(verify_repair(**data)["status"], "FAILED")

    def test_repair_unknown_freshness_and_no_correct_regressions(self):
        data = repair_inputs()
        data["freshness"]["frozen_before_evaluation"] = None
        self.assertEqual(verify_repair(**data)["status"], "INCONCLUSIVE")
        data = repair_inputs()
        data["panels"]["regression"][0]["before"]["value"] = 0
        self.assertEqual(verify_repair(**data)["status"], "INCONCLUSIVE")

    def test_repair_duplicate_and_unexpected_identity_rejected(self):
        for id_ in ("duplicate", "unexpected"):
            data = repair_inputs()
            row = copy.deepcopy(data["panels"]["fresh"][0])
            if id_ == "unexpected":
                row["id"] = "other"
            data["panels"]["fresh"].append(row)
            with self.assertRaises(LabError):
                verify_repair(**data)


if __name__ == "__main__":
    unittest.main()
