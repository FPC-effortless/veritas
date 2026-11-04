"""Operational process evidence, not model work or persistent-host qualification."""

import json
import os
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch

import test_controller
from research_lab.core import Controller, LabError
from research_lab.supervisor import health, supervise


class ServiceHealthTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_controller.ControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lab = self.fixture.lab
        self.workers = [
            {
                "id": f"worker-{i:02}",
                "role": "experiment",
                "principal": "constructed",
                "resource": "local",
            }
            for i in range(18)
        ]
        self.config = self.fixture.root / "workers.json"
        self.config.write_text(json.dumps(self.workers))

    def start(self):
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "research_lab",
                "--root",
                str(self.lab.root),
                "supervise",
                str(self.config),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        def cleanup():
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            child.stderr.close()

        self.addCleanup(cleanup)
        return child

    def wait_healthy(self):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            report = health(self.lab, self.workers)
            if report["healthy"]:
                return report
            time.sleep(0.1)
        self.fail(f"service never became healthy: {report}")

    def test_registration_alone_and_wrong_config_never_pass(self):
        for worker in self.workers:
            self.lab.worker(
                worker["id"], worker["role"], worker["resource"], principal=worker["principal"]
            )
        report = health(self.lab, self.workers)
        self.assertFalse(report["healthy"])
        self.assertEqual(report["live_workers"], 0)
        self.assertEqual(report["running_tasks"], 0)
        for value in ([], [{**self.workers[0], "role": "review"}], [self.workers[0]] * 2):
            with self.subTest(value=value), self.assertRaises(LabError):
                health(self.lab, value)

    def test_eighteen_processes_restart_with_durable_state_and_truthful_health(self):
        # A blocked review task must survive both service sessions without becoming
        # a model fit, independent review, or a claim of eighteen active lanes.
        self.fixture.register()
        with self.lab.transaction() as db:
            db.execute("UPDATE tasks SET status='failed' WHERE role='experiment'")
        before = self.lab.status()["tasks"]
        first = self.start()
        report = self.wait_healthy()
        self.assertEqual(report["live_workers"], 18)
        self.assertEqual(report["idle_workers"], 18)
        self.assertEqual(report["running_tasks"], 0)
        self.assertEqual(report["scientific_qualification"], "NOT_QUALIFIED")
        self.assertEqual(report["persistent_host"], "UNVERIFIED")
        with self.lab.connect() as db:
            previous = dict(db.execute("SELECT * FROM supervisor_activity").fetchone())
        with patch("research_lab.supervisor.time.time", return_value=time.time() + 60):
            self.assertFalse(health(self.lab, self.workers)["healthy"])
        with patch("research_lab.supervisor.time.time", return_value=0):
            self.assertFalse(health(self.lab, self.workers)["healthy"])
        self.assertFalse(health(self.lab, self.workers[:-1])["healthy"])
        # A recent record is not sufficient when its recorded child PID differs.
        with self.lab.transaction() as db:
            db.execute("UPDATE worker_activity SET pid=? WHERE id=?", (os.getpid(), "worker-00"))
        self.assertFalse(health(self.lab, self.workers)["healthy"])
        first.terminate()
        self.assertEqual(first.wait(timeout=20), 0)
        self.assertFalse(health(self.lab, self.workers)["healthy"])
        self.assertEqual(Controller(self.lab.root).status()["tasks"], before)
        second = self.start()
        self.wait_healthy()
        with self.lab.connect() as db:
            after = dict(db.execute("SELECT * FROM supervisor_activity").fetchone())
        self.assertNotEqual(previous["session"], after["session"])
        self.assertNotEqual(previous["pid"], after["pid"])
        self.assertEqual(Controller(self.lab.root).status()["tasks"], before)
        second.terminate()
        self.assertEqual(second.wait(timeout=20), 0)

    def test_expired_tasks_stay_reserved_and_are_never_recovered_by_probe(self):
        self.fixture.register()
        worker = self.workers[0]
        self.lab.worker(worker["id"], worker["role"], worker["resource"])
        task = self.lab.claim(worker["id"])
        with self.lab.transaction() as db:
            db.execute("UPDATE tasks SET lease_until=0 WHERE id=?", (task["id"],))
        before = self.lab.status()
        report = health(self.lab, self.workers[:1])
        self.assertFalse(report["healthy"])
        self.assertEqual(report["lost_or_expired_tasks"], 1)
        self.assertEqual(report["running_tasks"], 0)
        after = self.lab.status()
        self.assertEqual(before["tasks"], after["tasks"])
        self.assertEqual(before["programs"], after["programs"])

    def test_duplicate_supervisor_cannot_register_another_configuration(self):
        import fcntl

        with (self.lab.root / "supervisor.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(LabError, "supervisor is already active"):
                supervise(self.lab, self.workers)
        self.assertEqual(self.lab.status()["workers"], [])

    def test_storage_failure_still_reaps_launched_workers(self):
        child = Mock(pid=os.getpid())
        child.poll.return_value = None
        child.wait.return_value = 0

        def start(*args, **kwargs):
            self.lab.transaction = Mock(side_effect=sqlite3.OperationalError("storage unavailable"))
            return child

        with (
            patch("research_lab.supervisor.subprocess.Popen", side_effect=start),
            patch("research_lab.supervisor.tick"),
            self.assertRaises(sqlite3.OperationalError),
        ):
            supervise(self.lab, self.workers[:1])
        child.terminate.assert_called_once()
        child.wait.assert_called_once()

    def test_shutdown_grace_is_shared_by_all_stuck_workers(self):
        elapsed = [0.0]
        children = [Mock(pid=os.getpid() + i) for i in range(len(self.workers))]

        def wait(timeout=None):
            if timeout is not None:
                elapsed[0] += timeout
                raise subprocess.TimeoutExpired("constructed-stuck-worker", timeout)
            return -9

        for child in children:
            child.poll.return_value = None
            child.wait.side_effect = wait
        stop = Mock()
        stop.is_set.side_effect = [False, True]
        with (
            patch("research_lab.supervisor.subprocess.Popen", side_effect=children),
            patch("research_lab.supervisor.tick"),
            patch("research_lab.supervisor.time.monotonic", side_effect=lambda: elapsed[0]),
        ):
            supervise(self.lab, self.workers, stop=stop)
        self.assertEqual(elapsed[0], 15)
        for child in children:
            child.terminate.assert_called_once()
            child.kill.assert_called_once()
            self.assertEqual(child.wait.call_count, 2)

    def test_health_cli_fails_closed_without_service(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_lab",
                "--root",
                str(self.lab.root),
                "health",
                str(self.config),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["healthy"])


if __name__ == "__main__":
    unittest.main()
