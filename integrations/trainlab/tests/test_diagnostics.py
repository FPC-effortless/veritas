import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from trainlab.diagnostics import ModuleProfiler, require_finite
from trainlab.runner import LabError


class DiagnosticTests(unittest.TestCase):
    def test_nonfinite_and_empty_values_fail_without_disclosing_values(self):
        self.assertEqual(require_finite("weights", iter([1, -2.5, 0])), 3)
        for values in ([], [float("nan")], [float("inf")], [True], ["private-value"]):
            with self.subTest(values=values), self.assertRaises(LabError) as caught:
                require_finite("weights", values)
            self.assertNotIn("private-value", str(caught.exception))

    def test_timing_aggregation_failed_calls_and_sync(self):
        sync = Mock()
        profiler = ModuleProfiler(synchronize=sync)
        with patch("trainlab.diagnostics.perf_counter_ns", side_effect=[0, 10, 20, 50]):
            with profiler.measure("encoder"):
                pass
            with self.assertRaisesRegex(RuntimeError, "model failed"):
                with profiler.measure("encoder"):
                    raise RuntimeError("model failed")
        report = profiler.report()
        row = report["modules"]["encoder"]
        self.assertEqual(row["calls"], 2)
        self.assertEqual(row["failed_calls"], 1)
        self.assertAlmostEqual(row["total_seconds"], 4e-8)
        self.assertEqual(row["min_seconds"], 1e-8)
        self.assertEqual(row["max_seconds"], 3e-8)
        self.assertEqual(sync.call_count, 4)
        row["calls"] = 0
        self.assertEqual(profiler.report()["modules"]["encoder"]["calls"], 2)
        self.assertEqual(report["qualification"], "NOT_QUALIFIED")

    def test_names_and_bounded_cardinality(self):
        profiler = ModuleProfiler()
        for name in ("", " ", "x" * 121, None):
            with self.assertRaises(LabError), profiler.measure(name):
                pass
        for i in range(256):
            with profiler.measure(str(i)):
                pass
        with self.assertRaises(LabError), profiler.measure("overflow"):
            pass

    def test_nested_active_regions_count_toward_name_limit(self):
        profiler = ModuleProfiler()
        with ExitStack() as stack:
            for i in range(256):
                stack.enter_context(profiler.measure(str(i)))
            with self.assertRaises(LabError), profiler.measure("overflow"):
                pass
        self.assertEqual(len(profiler.report()["modules"]), 256)
