"""Coverage for the immutable, nonexecuting frontier program bootstrap."""
from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

from trainlab.runner import read_json

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "frontier_bootstrap.py"
spec = importlib.util.spec_from_file_location("frontier_bootstrap", SCRIPT)
frontier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frontier)


class FrontierBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.manifest = read_json(frontier.MANIFEST)
        self.historic = read_json(frontier.SEVEN)

    def test_all_seven_lanes_retained_and_graph_acyclic(self):
        result = frontier.validate(self.manifest, self.historic)
        self.assertEqual(result["source_backlog"], 7)
        self.assertEqual(result["lanes"], 18)
        self.assertEqual(result["benchmarks"], 6)

    def test_duplicate_lane_fails(self):
        candidate = copy.deepcopy(self.manifest)
        candidate["lanes"].append(copy.deepcopy(candidate["lanes"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            frontier.validate(candidate, self.historic)

    def test_missing_historic_lane_fails(self):
        candidate = copy.deepcopy(self.manifest)
        candidate["lanes"] = [x for x in candidate["lanes"] if x["id"] != "PSN"]
        with self.assertRaisesRegex(ValueError, "ARCHPAR"):
            frontier.validate(candidate, self.historic)

    def test_dependency_cycle_fails(self):
        candidate = copy.deepcopy(self.manifest)
        for lane in candidate["lanes"]:
            if lane["id"] == "SCM_SIE":
                lane["dependencies"] = ["LEARNING_OBJECTIVES"]
        with self.assertRaisesRegex(ValueError, "cyclic"):
            frontier.validate(candidate, self.historic)

    def test_bootstrap_is_idempotent_and_does_not_schedule(self):
        frontier.validate(self.manifest, self.historic)
        with tempfile.TemporaryDirectory() as d:
            first = frontier.bootstrap(Path(d), self.manifest)
            second = frontier.bootstrap(Path(d), self.manifest)
            self.assertEqual(first, second)
            self.assertEqual(first["jobs_scheduled"], 0)
            self.assertEqual(first["trained_models"], 0)
            from research_lab.core import Controller
            status = Controller(Path(d)).status()
            self.assertEqual(len(status["tasks"]), 0)


if __name__ == "__main__":
    unittest.main()
