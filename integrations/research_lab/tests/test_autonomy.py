"""Constructed operation tests, never model-provider or scientific evidence."""

import copy
import json
import os
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

import test_controller
from research_lab.autonomy import register_lane, tick
from research_lab.core import Controller, LabError
from research_lab.execution import evidence_pin, run_worker, submit_review


class AutonomyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_controller.ControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lab = self.fixture.lab
        self.root = self.fixture.recipes
        self.p = copy.deepcopy(self.fixture.protocol)
        self.p["max_attempts"] = 2
        for profile in ("first", "next"):
            (self.root / f"{profile}.json").write_text(json.dumps(self.p))
        self.spec = {
            "schema": "research_lab.autonomy.v1",
            "id": "lane",
            "program": "p",
            "initial": "first",
            "max_rounds": 2,
            "director": None,
            "profiles": {
                "first": {
                    "protocol": "first.json",
                    "transitions": {
                        "BOUNDED_CONTRAST_SUPPORTED": None,
                        "BOUNDED_CONTRAST_NOT_SUPPORTED": "next",
                    },
                },
                "next": {
                    "protocol": "next.json",
                    "transitions": {
                        "BOUNDED_CONTRAST_SUPPORTED": None,
                        "BOUNDED_CONTRAST_NOT_SUPPORTED": None,
                    },
                },
            },
        }
        self.lab.program("autonomy", "Constructed closed loop", 1000, 0)
        self.spec["program"] = "autonomy"
        self.p["program"] = "autonomy"
        for profile in ("first", "next"):
            (self.root / f"{profile}.json").write_text(json.dumps(self.p))

    def activate(self):
        return register_lane(self.lab, self.spec, self.root)

    def reviewed_round(self, protocol):
        self.lab.worker("execute", "experiment", "local")
        self.assertEqual(run_worker(self.lab, "execute"), 6)
        self.lab.worker("replica", "replication", "local")
        self.assertEqual(run_worker(self.lab, "replica"), 1)
        self.lab.worker("review", "review", "local")
        return submit_review(
            self.lab,
            protocol,
            "review",
            {
                "evidence_pin": evidence_pin(self.lab, protocol),
                "verdict": "clean",
                "findings": [],
                "summary": "Constructed test receipt; no live independent-science claim.",
                "independence": "SEPARATE_SESSION_OPERATOR_ASSERTED",
            },
        )

    def test_reviewed_negative_result_dispatches_once_after_reopen(self):
        self.activate()
        tick(self.lab)
        tick(self.lab)
        self.reviewed_round("lane-r001")
        reopened = Controller(self.lab.root)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: tick(reopened), range(4)))
        self.assertEqual(len(reopened.status()["autonomous_rounds"]), 2)
        self.assertEqual(len(reopened.status()["tasks"]), 16)
        self.reviewed_round("lane-r002")
        self.assertEqual(tick(reopened)[0]["phase"], "complete")
        tick(reopened)
        self.assertEqual(len(reopened.status()["autonomous_rounds"]), 2)
        self.assertTrue(reopened.status()["workers"][0]["activity"])

    def test_pending_review_and_corrupt_receipt_never_dispatch(self):
        self.activate()
        tick(self.lab)
        tick(self.lab)
        self.lab.worker("execute", "experiment", "local")
        run_worker(self.lab, "execute")
        self.lab.worker("replica", "replication", "local")
        run_worker(self.lab, "replica")
        self.assertEqual(tick(self.lab)[0]["phase"], "waiting")
        self.assertEqual(len(self.lab.status()["autonomous_rounds"]), 1)
        task = self.lab.task("lane-r001.candidate.1")
        path = self.lab.root / "runs" / task["result"]["run_id"] / "output" / "predictions.json"
        path.write_text("changed")
        self.lab.worker("review", "review", "local")
        with self.assertRaises(LabError):
            evidence_pin(self.lab, "lane-r001")
        self.assertEqual(len(self.lab.status()["autonomous_rounds"]), 1)

    def test_frozen_policy_and_recipe_mutation_fail_closed(self):
        pin = self.activate()
        self.assertEqual(self.activate(), pin)
        (self.root / "worker.py").write_text("changed")
        with self.assertRaisesRegex(LabError, "immutable"):
            self.activate()
        frozen = self.lab.root / "autonomy" / "lane" / "worker.py"
        frozen.write_text("changed")
        self.assertEqual(tick(self.lab)[0]["phase"], "blocked")
        self.assertEqual(self.lab.status()["tasks"], [])

    def test_malformed_routes_are_rejected_as_lab_errors(self):
        for value in (None, [], "not-a-route"):
            with self.subTest(value=value), self.assertRaises(LabError):
                bad = copy.deepcopy(self.spec)
                bad["profiles"]["first"]["transitions"] = value
                register_lane(self.lab, bad, self.root)

    def test_budget_and_lost_process_have_explicit_reasons(self):
        self.lab.program("tiny", "tiny", 1, 0)
        self.spec["program"] = "tiny"
        for profile in ("first", "next"):
            (self.root / f"{profile}.json").write_text(json.dumps({**self.p, "program": "tiny"}))
        self.activate()
        tick(self.lab)
        self.assertEqual(tick(self.lab)[0]["phase"], "budget_exhausted")
        self.assertFalse(self.lab.status()["tasks"])

    def test_running_lost_and_failed_tasks_never_spawn_a_second_round(self):
        self.activate()
        tick(self.lab)
        tick(self.lab)
        self.lab.worker("execute", "experiment", "local")
        self.lab.claim("execute", now=100, lease_seconds=1)
        self.lab.expire(now=102)
        result = tick(self.lab)[0]
        self.assertEqual(result["phase"], "blocked")
        self.assertIn("lost", result["reason"])
        self.assertEqual(len(self.lab.status()["autonomous_rounds"]), 1)

    def test_positive_result_takes_explicit_stop_branch(self):
        self.p["minimum_effect"] = 0
        for profile in ("first", "next"):
            (self.root / f"{profile}.json").write_text(json.dumps(self.p))
        self.activate()
        tick(self.lab)
        tick(self.lab)
        self.reviewed_round("lane-r001")
        self.assertEqual(tick(self.lab)[0]["phase"], "complete")
        self.assertEqual(len(self.lab.status()["autonomous_rounds"]), 1)

    def test_post_enqueue_crash_is_idempotent(self):
        self.activate()
        tick(self.lab)
        with self.lab.connect() as db:
            p = json.loads(db.execute("SELECT spec FROM autonomous_rounds").fetchone()[0])
        self.lab.register(p, self.lab.root / "autonomy" / "lane")
        tick(Controller(self.lab.root))
        self.assertEqual(len(self.lab.status()["tasks"]), 8)

    def director_fixture(self, profile):
        proposal = {
            "schema": "research_lab.proposal.v1",
            "id": "fixture-next",
            "author": "designer",
            "question": self.p["question"],
            "hypothesis": self.p["hypothesis"],
            "competing_explanations": self.p["alternatives"],
            "predictions": self.p["predictions"],
            "controls": self.p["controls"],
            "ablations": self.p["ablations"],
            "primary_metric": self.p["metric"],
            "direction": self.p["direction"],
            "minimum_effect": self.p["minimum_effect"],
            "seeds": self.p["seeds"],
            "stopping_rule": self.p["stopping_rule"],
            "limitations": self.p["limitations"],
            "next_discriminating_test": self.p["next_test"],
            "execution": {"profile": profile},
        }
        output = {
            "schema": "research_lab.agent_result.v1",
            "role": "director",
            "summary": "Constructed provider fixture",
            "findings": [],
            "proposals": [proposal],
            "source_nodes": [],
            "next_actions": ["Run admitted profile"],
        }
        (self.root / "director.py").write_text(
            "import json,os\nfrom pathlib import Path\np=Path(os.environ['TRAINLAB_OUTPUT_DIR'])\n"
            + "(p/'metrics.json').write_text('{\"accuracy\":1.0}')\n"
            + "(p/'agent_result.json').write_text("
            + repr(json.dumps(output))
            + ")\n"
        )
        recipe = json.loads((self.root / "candidate.json").read_text())
        recipe.update(
            command=[sys.executable, "director.py"],
            inputs=["director.py"],
            artifacts=["agent_result.json"],
        )
        (self.root / "director-recipe.json").write_text(json.dumps(recipe))
        order = {
            "schema": "research_lab.work_order.v1",
            "id": "director-template",
            "program": "autonomy",
            "author": "designer",
            "role": "director",
            "resource": "local",
            "slots": 1,
            "max_attempts": 1,
            "priority": 1,
            "objective": "Select one next admitted experiment",
            "acceptance": ["Return a valid bounded proposal"],
            "context_nodes": [],
            "dependencies": [],
            "recipe": "director-recipe.json",
            "source_commit": "a" * 40,
        }
        (self.root / "director-order.json").write_text(json.dumps(order))
        self.spec["director"] = "director-order.json"

    def test_validated_provider_proposal_becomes_frozen_training_protocol(self):
        self.director_fixture("next")
        self.activate()
        tick(self.lab)
        tick(self.lab)
        self.reviewed_round("lane-r001")
        self.assertIn("director", tick(self.lab)[0]["reason"])
        self.lab.worker("director-worker", "director", "local", principal="designer")
        self.assertEqual(run_worker(self.lab, "director-worker"), 1)
        tick(self.lab)
        tick(self.lab)
        self.assertEqual(len(self.lab.status()["autonomous_rounds"]), 2)
        decision = json.loads(self.lab.status()["autonomous_rounds"][-1]["decision"])
        self.assertEqual(decision["basis"], "VALIDATED_DIRECTOR_PROPOSAL")
        self.assertEqual(len(self.lab.status()["tasks"]), 17)
        self.assertEqual(self.lab.protocol("lane-r002")["author"], "director-worker")
        self.lab.worker("execute", "experiment", "local")
        run_worker(self.lab, "execute")
        self.lab.worker("director-replica-alias", "replication", "local", principal="designer")
        self.assertIsNone(self.lab.claim("director-replica-alias", task_id="lane-r002.replication"))

    def test_unadmitted_provider_profile_is_blocked(self):
        self.director_fixture("arbitrary-command")
        self.activate()
        tick(self.lab)
        tick(self.lab)
        self.reviewed_round("lane-r001")
        tick(self.lab)
        self.lab.worker("director-worker", "director", "local")
        run_worker(self.lab, "director-worker")
        result = tick(self.lab)[0]
        self.assertEqual(result["phase"], "blocked")
        self.assertIn("unadmitted", result["reason"])
        self.assertEqual(len(self.lab.status()["autonomous_rounds"]), 1)

    def test_registered_worker_is_not_reported_alive(self):
        self.lab.worker("idle", "experiment", "local")
        self.assertEqual(self.lab.status()["workers"][0]["liveness"], "REGISTERED_ONLY")
        run_worker(self.lab, "idle")
        self.assertEqual(self.lab.status()["workers"][0]["liveness"], "STOPPED")

    def test_live_supervisor_restarts_idle_worker_and_shuts_down(self):
        workers = self.root / "workers.json"
        workers.write_text(
            json.dumps(
                [
                    {
                        "id": "supervised",
                        "role": "experiment",
                        "principal": "test",
                        "resource": "local",
                    }
                ]
            )
        )
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "research_lab",
                "--root",
                str(self.lab.root),
                "supervise",
                str(workers),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)

        def wait_for(predicate):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                value = predicate()
                if value:
                    return value
                time.sleep(0.1)
            self.fail("supervisor did not reach expected state")

        def active():
            rows = self.lab.status()["workers"]
            return next((w["activity"] for w in rows if w["liveness"] == "HEARTBEAT_RECENT"), None)

        first = wait_for(active)
        os.kill(first["pid"], 15)
        second = wait_for(lambda: v if (v := active()) and v["pid"] != first["pid"] else None)
        self.assertNotEqual(first["session"], second["session"])
        child.terminate()
        self.assertEqual(child.wait(timeout=15), 0)
        child.stderr.close()
        self.assertEqual(self.lab.status()["workers"][0]["liveness"], "STOPPED")


if __name__ == "__main__":
    unittest.main()
