import copy
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trainlab.prediction_artifacts import _bytes
from trainlab.runner import LabError
from trainlab.runtime_preflight import ENVIRONMENT, FLAGS, inspect_runtime, require_native_admission


class RuntimePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "candidate"
        self.root.mkdir()
        self.stdlib = self.base / "stdlib"
        self.stdlib.mkdir()
        self.dynload = self.stdlib / "lib-dynload"
        self.dynload.mkdir()
        self.interpreter = self.base / "python"
        self.interpreter.write_bytes(b"inert interpreter stand-in")
        self.interpreter.chmod(0o555)
        self.source = self.root / "torch.py"
        # Must never execute: this would create an obvious failure.
        self.source.write_text("raise RuntimeError('candidate was executed')\n")
        self.source.chmod(0o444)
        self.policy = {
            "schema": "trainlab.runtime-preflight.v1",
            "root": str(self.root),
            "interpreter": {
                "path": str(self.interpreter),
                "identity": self.identity(self.interpreter),
            },
            "files": {"torch.py": self.identity(self.source)},
            "flags": FLAGS,
            "environment": dict(ENVIRONMENT),
            "sys_path": [str(self.stdlib), str(self.dynload), str(self.root)],
        }

    def identity(self, p):
        return {
            "bytes": p.stat().st_size,
            "mode": p.stat().st_mode & 0o777,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }

    def run_policy(self, policy=None):
        p = self.policy if policy is None else policy
        return inspect_runtime(
            self.root, self.interpreter, p, policy_sha256=hashlib.sha256(_bytes(p)).hexdigest()
        )

    def test_static_match_never_admits(self):
        report = self.run_policy()
        self.assertEqual(report["status"], "STATIC_LAYOUT_MATCH")
        self.assertFalse(report["native_execution_admitted"])
        for value in (report, {**report, "native_execution_admitted": True}, None):
            with self.assertRaises(LabError):
                require_native_admission(value)

    def test_empty_environment_is_not_backend_disable(self):
        for env in (
            {},
            {**ENVIRONMENT, "TORCH_DEVICE_BACKEND_AUTOLOAD": "1"},
            {**ENVIRONMENT, "PYTHONPATH": "untrusted"},
        ):
            p = copy.deepcopy(self.policy)
            p["environment"] = env
            with self.assertRaises(LabError):
                self.run_policy(p)

    def test_locale_and_utf8_amendments_require_new_policy(self):
        for environment in (
            {**ENVIRONMENT, "LC_CTYPE": "C.UTF-8"},
            {**ENVIRONMENT, "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"},
        ):
            policy = copy.deepcopy(self.policy)
            policy["environment"] = environment
            with self.assertRaises(LabError):
                self.run_policy(policy)
        policy = copy.deepcopy(self.policy)
        policy["flags"] = [*FLAGS, "-X", "utf8"]
        with self.assertRaises(LabError):
            self.run_policy(policy)

    def test_changed_mode_or_bytes(self):
        self.source.chmod(0o555)
        with self.assertRaises(LabError):
            self.run_policy()
        self.source.chmod(0o644)
        self.source.write_bytes(b"different")
        self.source.chmod(0o444)
        with self.assertRaises(LabError):
            self.run_policy()

    def test_extra_missing_link_and_special_members(self):
        other = self.root / "extra"
        other.write_bytes(b"extra")
        with self.assertRaises(LabError):
            self.run_policy()
        other.unlink()
        other.symlink_to(self.source)
        with self.assertRaises(LabError):
            self.run_policy()
        other.unlink()
        self.source.unlink()
        with self.assertRaises(LabError):
            self.run_policy()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_fifo_refused_without_open(self):
        os.mkfifo(self.root / "pipe")
        with self.assertRaisesRegex(LabError, "special"):
            self.run_policy()

    def test_paths_flags_policy_pin(self):
        for flags in (["-I", "-B"], [], FLAGS + ["-O"]):
            p = copy.deepcopy(self.policy)
            p["flags"] = flags
            with self.assertRaises(LabError):
                self.run_policy(p)
        p = copy.deepcopy(self.policy)
        p["sys_path"][0] = str(self.base / "python312.zip")
        with self.assertRaises(LabError):
            self.run_policy(p)
        with self.assertRaises(LabError):
            inspect_runtime(self.root, self.interpreter, self.policy, policy_sha256="0" * 64)

    def test_incomplete_or_unbounded_traversal_refuses(self):
        def inaccessible(*args, **kwargs):
            kwargs["onerror"](PermissionError("hidden subtree"))
            yield str(self.root), [], ["torch.py"]

        with patch("trainlab.runtime_preflight.os.walk", inaccessible):
            with self.assertRaisesRegex(LabError, "incomplete"):
                self.run_policy()
        with patch("trainlab.runtime_preflight.MAX_ENTRIES", 0):
            with self.assertRaisesRegex(LabError, "entry bound"):
                self.run_policy()

    def test_after_enumeration_addition_is_not_native_admission(self):
        original_walk = os.walk

        def changing_tree(*args, **kwargs):
            yield from original_walk(*args, **kwargs)
            (self.root / "late.py").write_text("raise RuntimeError('never import')\n")

        with patch("trainlab.runtime_preflight.os.walk", changing_tree):
            report = self.run_policy()
        self.assertEqual(report["status"], "STATIC_LAYOUT_MATCH")
        self.assertEqual(report["inventory_atomicity"], "NON_ATOMIC_SEQUENTIAL_OBSERVATION")
        self.assertTrue((self.root / "late.py").exists())
        with self.assertRaises(LabError):
            require_native_admission(report)
        # A later independent scan detects the now-present extra file, but is
        # itself still not an atomic snapshot or permission to execute.
        with self.assertRaisesRegex(LabError, "extra or missing"):
            self.run_policy()

    def test_bad_inventory_names(self):
        for name in ("../outside", "/outside", "a//b", "a\\b", "a\0b"):
            p = copy.deepcopy(self.policy)
            p["files"] = {name: self.identity(self.source)}
            with self.assertRaises(LabError):
                self.run_policy(p)


if __name__ == "__main__":
    unittest.main()
