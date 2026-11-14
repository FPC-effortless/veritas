import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import resource
except ImportError:
    resource = None

from trainlab.resource_diagnostics import EXECUTION, run_command
from trainlab.runner import LabError, digest, read_json

LIMITS = {
    "wall_seconds": 3,
    "cpu_seconds": 2,
    "address_space_bytes": 256 * 1024**2,
    "file_bytes": 4096,
}
IDENTITIES = {k: "a" * 64 for k in ("model", "dataset", "code", "configuration")}


@unittest.skipUnless(sys.platform == "linux", "Linux resource session backend")
class ResourceTests(unittest.TestCase):
    def test_unsupported_execution_rejected_before_output(self):
        for execution in (
            {**EXECUTION, "device": "gpu"},
            {**EXECUTION, "remote_work": True},
            {**EXECUTION, "detaches": True},
            {**EXECUTION, "synchronous": 1},
            {},
        ):
            with self.assertRaises(LabError):
                self.execute("pass", execution=execution)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_completed_child_after_supervisor_delay_is_not_within_budget(self):
        real_sleep = time.sleep
        with patch(
            "trainlab.resource_diagnostics.time.sleep", side_effect=lambda _: real_sleep(0.3)
        ):
            result, _ = self.execute("pass", limits={**LIMITS, "wall_seconds": 0.15})
        self.assertEqual(result["state"], "TIMEOUT")
        self.assertTrue(result["wall_budget_exceeded"])
        self.assertEqual(result["cost_coverage"], "INCOMPLETE")

    def test_boolean_limit_evidence_does_not_equal_integer(self):
        output = self.root / str(self.n + 1)
        code = (
            "import json; from pathlib import Path; "
            f"p=Path({str(output / 'limits-applied.json')!r}); "
            "r=json.loads(p.read_text()); r['limits']['cpu_seconds']=[True,True]; "
            "p.write_text(json.dumps(r))"
        )
        result, _ = self.execute(code, limits={**LIMITS, "cpu_seconds": 1})
        self.assertFalse(result["limits_applied"])
        self.assertEqual(result["cost_coverage"], "INCOMPLETE")

    def test_interrupt_receipt_and_reap(self):
        real_wait4 = os.wait4

        def interrupted(pid, options):
            if options == os.WNOHANG:
                raise KeyboardInterrupt()
            return real_wait4(pid, options)

        with patch("trainlab.resource_diagnostics.os.wait4", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.execute("import time; time.sleep(10)")
        result = read_json(self.root / "1/receipt.json")
        self.assertEqual(result["state"], "INTERRUPTED")
        with self.assertRaises(ProcessLookupError):
            os.kill(result["pid"], 0)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.n = 0

    def execute(self, code, **kwargs):
        self.n += 1
        output = self.root / str(self.n)
        result = run_command(
            [sys.executable, "-c", code],
            output,
            cwd=self.root,
            identities=IDENTITIES,
            workload_sha256="b" * 64,
            limits=kwargs.pop("limits", LIMITS),
            execution=kwargs.pop("execution", EXECUTION),
            **kwargs,
        )
        self.assertEqual(result, read_json(output / "receipt.json"))
        return result, output

    def test_success_records_direct_wall_cpu_rss_and_hashes(self):
        result, root = self.execute("print('completed')")
        self.assertEqual(result["state"], "SUCCEEDED")
        self.assertEqual(result["cost_coverage"], "MEASURED")
        self.assertTrue(result["limits_applied"])
        self.assertGreater(result["wall_seconds"], 0)
        self.assertGreater(result["peak_process_rss_bytes"], 0)
        self.assertGreater(result["user_cpu_seconds"] + result["system_cpu_seconds"], 0)
        self.assertEqual(result["artifacts"]["stdout.log"], digest(root / "stdout.log"))

    def test_nonzero_exit_cost_is_retained_but_incomplete(self):
        result, _ = self.execute("raise SystemExit(7)")
        self.assertEqual(result["returncode"], 7)
        self.assertEqual(result["state"], "FAILED")
        self.assertEqual(result["cost_coverage"], "INCOMPLETE")
        self.assertGreater(result["wall_seconds"], 0)

    def test_timeout_terminates_and_reaps_leader(self):
        limits = {**LIMITS, "wall_seconds": 0.15}
        result, _ = self.execute("import time; time.sleep(10)", limits=limits)
        self.assertEqual(result["state"], "TIMEOUT")
        self.assertLess(result["wall_seconds"], 2)
        with self.assertRaises(ProcessLookupError):
            os.kill(result["pid"], 0)

    def test_address_space_refusal_does_not_limit_parent(self):
        parent = resource.getrlimit(resource.RLIMIT_AS)
        result, _ = self.execute(
            "try:\n x=bytearray(512*1024**2)\nexcept MemoryError:\n raise SystemExit(42)"
        )
        self.assertEqual(result["returncode"], 42)
        self.assertEqual(resource.getrlimit(resource.RLIMIT_AS), parent)
        self.assertTrue(result["limits_applied"])

    def test_cpu_limit_inherited_and_enforced(self):
        limits = {**LIMITS, "cpu_seconds": 1, "wall_seconds": 4}
        result, root = self.execute(
            "import resource; print(resource.getrlimit(resource.RLIMIT_CPU), flush=True)"
            "\nwhile True: pass",
            limits=limits,
        )
        self.assertIn("(1, 1)", (root / "stdout.log").read_text())
        self.assertLess(result["returncode"], 0)
        self.assertEqual(result["state"], "FAILED")
        self.assertEqual(result["signal_cause"], "NOT_INFERRED_FROM_EXIT_STATUS")

    def test_file_limit_bounds_stdout(self):
        result, root = self.execute("import os; os.write(1, b'x'*100000); os.write(1, b'y'*100000)")
        self.assertLessEqual((root / "stdout.log").stat().st_size, LIMITS["file_bytes"])
        self.assertEqual(result["state"], "FAILED")

    def test_orphan_group_is_terminated_and_cannot_qualify(self):
        code = (
            "import os,time\npid=os.fork()\nif pid==0:\n time.sleep(10)"
            "\nelse:\n print(pid,flush=True)"
        )
        result, root = self.execute(code)
        self.assertTrue(result["descendants_terminated"])
        self.assertEqual(result["cost_coverage"], "INCOMPLETE")
        pid = int((root / "stdout.log").read_text())
        for _ in range(20):
            stat = Path(f"/proc/{pid}/stat")
            if not stat.exists() or stat.read_text().split()[2] == "Z":
                break
            time.sleep(0.01)
        else:
            self.fail("supervised descendant still running")

    def test_rate_estimate_keeps_explicit_rate_date_and_units(self):
        rate = {"per_hour": 0.5, "currency": "USD", "as_of": "2026-11-14"}
        result, _ = self.execute("pass", hourly_rate=rate)
        self.assertAlmostEqual(result["money_estimate"]["amount"], result["wall_seconds"] / 7200)
        self.assertEqual(result["money_estimate"]["as_of"], rate["as_of"])
        self.assertIn("NOT_A_BILL", result["money_estimate"]["scope"])

    def test_malformed_limits_and_rate_rejected_before_output(self):
        for key, value in [
            ("wall_seconds", float("nan")),
            ("cpu_seconds", True),
            ("address_space_bytes", 1),
            ("file_bytes", 0),
        ]:
            with self.assertRaises(LabError):
                self.execute("pass", limits={**LIMITS, key: value})
        with self.assertRaises(LabError):
            self.execute("pass", hourly_rate={"per_hour": 0.1, "currency": "USD", "as_of": "bad"})
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_output_refused_and_parent_cpu_limit_unchanged(self):
        parent = resource.getrlimit(resource.RLIMIT_CPU)
        result, path = self.execute("pass")
        with self.assertRaises(FileExistsError):
            run_command(
                [sys.executable, "-c", "pass"],
                path,
                cwd=self.root,
                identities=IDENTITIES,
                workload_sha256="b" * 64,
                limits=LIMITS,
                execution=EXECUTION,
            )
        self.assertEqual(resource.getrlimit(resource.RLIMIT_CPU), parent)
        self.assertEqual(read_json(path / "receipt.json"), result)

    def test_missing_or_modified_request_cannot_qualify(self):
        for action in ("unlink()", "write_text('{}')"):
            output = self.root / str(self.n + 1)
            code = f"from pathlib import Path; Path({str(output / 'request.json')!r}).{action}"
            result, _ = self.execute(code)
            self.assertFalse(result["request_unchanged"])
            self.assertEqual(result["cost_coverage"], "INCOMPLETE")

    def test_missing_setup_evidence_cannot_qualify(self):
        output = self.root / str(self.n + 1)
        code = f"from pathlib import Path; Path({str(output / 'limits-applied.json')!r}).unlink()"
        result, _ = self.execute(code)
        self.assertFalse(result["limits_applied"])
        self.assertEqual(result["state"], "FAILED")

    def test_argv_and_identity_validation(self):
        for argv, identities in [
            ("echo x", IDENTITIES),
            (["python", "-c", "pass"], IDENTITIES),
            ([sys.executable, "-c", "pass"], {"model": "a" * 64}),
        ]:
            with self.assertRaises(LabError):
                run_command(
                    argv,
                    self.root / "bad",
                    cwd=self.root,
                    identities=identities,
                    workload_sha256="b" * 64,
                    limits=LIMITS,
                    execution=EXECUTION,
                )


if __name__ == "__main__":
    unittest.main()
