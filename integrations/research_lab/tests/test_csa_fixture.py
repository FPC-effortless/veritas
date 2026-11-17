"""Deterministic no-fit scientific integrity checks for WIL-TRAIN-001."""
import hashlib
import json
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path

# The public no-fit generator lives in examples; CI discovers this test from tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from csa_fixture import (KINDS, PLACES, SPLITS, cross_query_rows, export, make_split, model_view, public_rows,
                         replay, validate)


class NoFitFixtureTests(unittest.TestCase):
    def setUp(self):
        self.panels = {s: make_split(s, 71407 + i * 1_000_003, 120)
                       for i, s in enumerate(SPLITS)}

    def test_sizes_balance_and_opposite_pairs(self):
        for panel in self.panels.values():
            counts = validate(panel)
            self.assertEqual(counts["pair_count"], 120)
            self.assertEqual(counts["row_count"], 240)
            self.assertEqual(counts["by_kind"], {k: 40 for k in KINDS})
            self.assertEqual(counts["opposite_answer_pairs"], 80)
            self.assertEqual(counts["same_answer_pairs"], 40)

    def test_minimal_edits_same_query_suffix_prefix(self):
        for panel in self.panels.values():
            for p in panel:
                self.assertEqual(p.a["query"], p.b["query"])
                self.assertEqual(p.a["history"].splitlines()[-1], p.b["history"].splitlines()[-1])
                self.assertEqual(p.a["history"].splitlines()[:-2], p.b["history"].splitlines()[:-2])
                self.assertNotEqual(p.events_a[-1], p.events_b[-1])
                self.assertEqual(p.events_a[:-1], p.events_b[:-1])

    def test_semantic_updates_and_erasures(self):
        for panel in self.panels.values():
            for p in panel:
                for row, events in ((p.a, p.events_a), (p.b, p.events_b)):
                    predicted = replay(list(events)).get(p.key)
                    self.assertEqual(row["answer"], predicted or "UNKNOWN")
                if p.kind == "retraction":
                    self.assertEqual(sum(x["answer"] == "UNKNOWN" for x in (p.a, p.b)), 1)

    def test_no_history_conflicting_pair_upper_bound(self):
        # This bound is conditional on each pair and applies only to opposing
        # labels. There is no global 50% claim for arbitrary class priors.
        for panel in self.panels.values():
            for p in panel:
                if p.kind != "irrelevant_edit":
                    self.assertNotEqual(p.a["answer"], p.b["answer"])
                    self.assertEqual(max(sum(x["answer"] == y for x in (p.a, p.b))
                                         for y in (p.a["answer"], p.b["answer"])), 1)

    def test_model_view_cannot_see_oracle_and_answer(self):
        for panel in self.panels.values():
            for row in public_rows(panel):
                self.assertEqual(set(model_view(row)), {"history", "query"})
                self.assertNotIn("answer", model_view(row))
                self.assertNotIn("kind", model_view(row))
                self.assertNotIn("arm", model_view(row))

    def test_disjoint_syntax_family(self):
        same_syntax = self.panels["train"][0].a["history"]
        new_syntax = self.panels["dev_ood_syntax"][0].a["history"]
        self.assertIn("Record", same_syntax)
        self.assertIn("Log", new_syntax)
        self.assertNotIn("Record", new_syntax)
        for p in self.panels["dev_ood_syntax"]:
            self.assertIn("Identify", p.a["query"])

    def test_seed_replay_and_export_hash(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a, b = export(Path(d1), 71407, 120), export(Path(d2), 71407, 120)
            self.assertEqual(a, b)
            for split in SPLITS:
                blob = (Path(d1) / a["splits"][split]["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(blob).hexdigest(), a["splits"][split]["sha256"])
                rows = [json.loads(x) for x in blob.splitlines()]
                self.assertEqual(len(rows), 240)
                probe_blob = (Path(d1) / a["splits"][split]["cross_probe_file"]).read_bytes()
                self.assertEqual(hashlib.sha256(probe_blob).hexdigest(),
                                 a["splits"][split]["cross_probe_sha256"])
                self.assertEqual(len(probe_blob.splitlines()), 80)

    def test_query_relative_not_global_invariance(self):
        for panel in self.panels.values():
            probes = cross_query_rows(panel)
            self.assertEqual(len(probes), 80)
            for i in range(0, len(probes), 2):
                a, b = probes[i:i+2]
                self.assertEqual(a["history"].splitlines()[:-2], b["history"].splitlines()[:-2])
                self.assertEqual(a["query"], b["query"])
                self.assertNotEqual(a["answer"], b["answer"])
                self.assertNotIn("answer", model_view(a))

    def test_tampered_label_detected(self):
        panel = self.panels["train"]
        victim = panel[0]
        saved = victim.a["answer"]
        try:
            victim.a["answer"] = "TAMPERED"
            with self.assertRaises(ValueError):
                validate(panel)
        finally:
            victim.a["answer"] = saved

    def test_validation_is_not_removed_by_python_optimized_mode(self):
        script = ("from csa_fixture import make_split,validate; "
                  "cases=make_split('train',71407,3); "
                  "cases[0].a['answer']='TAMPER'; validate(cases)")
        result = subprocess.run([sys.executable, "-O", "-c", script],
                                env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "examples")},
                                capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ValueError", result.stderr)

    def test_invalid_split_and_sizes_rejected(self):
        with self.assertRaises(ValueError):
            make_split("sealed_test", 1, 12)
        with self.assertRaises(ValueError):
            make_split("train", 1, 11)


# Additional grammar-aware/control qualification tests (not neural training).
from csa_diagnostics import evaluate, naive_recency, strong_symbolic


class NonNeuralComparators(unittest.TestCase):
    def test_symbolic_parser_and_recency_controls(self):
        report = evaluate()
        for split, data in report["splits"].items():
            self.assertEqual(data["examples"], 240, split)
            self.assertEqual(data["symbolic_accuracy"], 1.0, split)
            self.assertEqual(data["recency_accuracy"], 0.5, split)
            self.assertEqual(data["by_kind"]["irrelevant_edit"]["recency_correct"], 0)
            self.assertEqual(data["by_kind"]["retraction"]["recency_correct"], 40)
            self.assertEqual(data["cross_relevance"]["n"], 80)
            self.assertEqual(data["cross_relevance"]["symbolic_correct"], 80)
            self.assertEqual(data["cross_relevance"]["recency_correct"], 80)
            self.assertEqual(data["cross_relevance"]["ignore_latest_edit_correct"], 0)

    def test_symbols_use_model_input_only(self):
        p = make_split("train", 10, 3)[0]
        for row in (p.a, p.b):
            inp = model_view(row)
            self.assertEqual(strong_symbolic(inp), row["answer"])
            self.assertIn(naive_recency(inp), ("UNKNOWN", *PLACES))

if __name__ == "__main__":
    unittest.main()
