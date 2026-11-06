"""Scientific invariant regressions for WIL-TRAIN-002, no model training."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"examples"))
from csa_v02 import (SPLITS,LENGTHS,PROJECTS,PEOPLE,KINDS,generate,validate_pair,
                      labeled_rows,cross_rows,model_view,assigned_pair_allowed,emit)

class ScientificChecks(unittest.TestCase):
    def test_balanced_paired_labels_and_cross_query(self):
        for split in SPLITS:
            for length in LENGTHS:
                pairs = generate(split,length,40,12345)
                self.assertEqual(len(pairs),40)
                self.assertEqual({k:sum(p.kind==k for p in pairs) for k in KINDS},dict.fromkeys(KINDS,10))
                self.assertEqual(len(labeled_rows(pairs)),80)
                self.assertEqual(len(cross_rows(pairs)),20)
                for p in pairs:
                    validate_pair(p)
                    self.assertEqual(set(model_view(p.a)),{"history","query"})
                    self.assertEqual(set(model_view(p.b)),{"history","query"})
                    if p.kind=="irrelevant_relocate":
                        self.assertEqual(p.a["answer"],p.b["answer"])
                    else:
                        self.assertNotEqual(p.a["answer"],p.b["answer"])

    def test_holdout_relations_disjoint_not_vocab(self):
        # Compositional holdout is over PROJECT+PERSON assignments, not token vocabulary.
        train = generate("train",32,40,77)
        held = generate("dev_ood_comp",32,40,77)
        seen=set()
        for p in train:
            for ev in p.events_a + p.events_b:
                if ev["kind"]=="assign": seen.add((ev["project"],ev["person"]))
        probe=set()
        for p in held:
            for es in (p.events_a,p.events_b):
                seed=next(ev for ev in es if ev["kind"]=="assign" and ev["project"]==p.project)
                probe.add((seed["project"],seed["person"]))
        self.assertTrue(probe)
        self.assertFalse(seen & probe)
        self.assertTrue(set(x for x,y in probe) <= set(PROJECTS))
        self.assertTrue(set(y for x,y in probe) <= set(PEOPLE))
        self.assertTrue(all(assigned_pair_allowed(x,y,"dev_ood_comp") for x,y in probe))

    def test_deterministic_hash_manifest(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            x,y=emit(Path(a),212,8),emit(Path(b),212,8)
            self.assertEqual(x,y)
            self.assertEqual(len(x["files"]),12)
            for name, info in x["files"].items():
                data=(Path(a)/name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),info["sha256"])
                self.assertEqual(len(data.splitlines()),info["primary"]+info["secondary"])

    def test_public_rows_have_no_typed_oracle(self):
        for row in labeled_rows(generate("train",8,4,82)):
            self.assertEqual(set(model_view(row)),{"history","query"})
            for banned in ("events_a","events_b","project","owner","oracle","kind","answer","arm"):
                self.assertNotIn(banned,model_view(row))

    def test_mutated_answer_rejected_even_optimized(self):
        pair=generate("train",8,4,82)[0]
        prev=pair.a["answer"]
        try:
            pair.a["answer"]="FAKE"
            with self.assertRaises(ValueError): validate_pair(pair)
        finally: pair.a["answer"]=prev

if __name__=="__main__": unittest.main()

# Additional independent grammar-oracle/shortcut negative controls.
from csa_v02_diagnostics import evaluate,symbolic,ignore_latest,last_location

class ComparatorChecks(unittest.TestCase):
    def test_parser_passes_all_diagnostic_cases_and_ignoring_edit_fails_cross(self):
        r=evaluate(seed=99,pairs=8)
        self.assertEqual(len(r["cells"]),12)
        for key, val in r["cells"].items():
            self.assertEqual(val["primary_n"],16)
            self.assertEqual(val["cross_n"],4)
            self.assertEqual(val["strong_symbolic_accuracy"],1.0,key)
            self.assertEqual(val["cross_symbolic_accuracy"],1.0,key)
            self.assertEqual(val["cross_ignore_latest_accuracy"],0.0,key)
            self.assertLess(val["ignore_latest_accuracy"],1.0,key)

    def test_no_typed_events_consulted(self):
        pair=generate("train",8,4,919)[0]
        for row in (pair.a,pair.b):
            inp=model_view(row)
            self.assertEqual(symbolic(inp),row["answer"])
            self.assertIsInstance(ignore_latest(inp),str)
            self.assertIsInstance(last_location(inp),str)
