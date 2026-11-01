import json
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research_lab.core import Controller, LabError


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lab = Controller(self.root / "lab")
        self.lab.program("p", "Can carried state survive unrelated edits?", 100, 0)
        self.lab.resource("local", "cpu", 2, 0)
        self.recipes = self.root / "recipes"
        self.recipes.mkdir()
        (self.recipes / "worker.py").write_text(
            "import os,json\nfrom pathlib import Path\n"
            "p=Path(os.environ['TRAINLAB_OUTPUT_DIR'])\n"
            "(p/'metrics.json').write_text(json.dumps({'accuracy':0.75}))\n"
            "(p/'predictions.json').write_text('[1,0,1,1]')\n"
        )
        recipe = {
            "schema": "trainlab.experiment.v1",
            "name": "fixture",
            "description": "fixture",
            "command": [sys.executable, "worker.py"],
            "seed": 1,
            "timeout_seconds": 2,
            "source_kind": "CONSTRUCTED",
            "split_identity": "frozen-fixture",
            "inputs": ["worker.py"],
            "artifacts": ["predictions.json"],
            "metrics": {"accuracy": "max"},
            "budget": {"episodes": 4},
        }
        for arm in ("candidate", "control"):
            (self.recipes / f"{arm}.json").write_text(json.dumps(recipe))
        self.protocol = {
            "schema": "research_lab.protocol.v1",
            "id": "exp",
            "program": "p",
            "author": "designer",
            "question": "Does memory help?",
            "hypothesis": "Memory improves recall.",
            "alternatives": ["Position shortcut", "Class imbalance"],
            "predictions": ["Carry improves", "Reset removes gain"],
            "controls": ["reset", "balanced cases"],
            "ablations": ["reset"],
            "metric": "accuracy",
            "direction": "max",
            "minimum_effect": 0.1,
            "seeds": [1, 2, 3],
            "resource": "local",
            "slots": 1,
            "max_attempts": 1,
            "stopping_rule": "All three seeds; no score-based retries",
            "scope": "ENGINEERING_ONLY",
            "priority": 1,
            "source_commit": "a" * 40,
            "limitations": ["Constructed only"],
            "next_test": "Train credible models on a frozen held-out panel.",
            "candidate": "candidate.json",
            "control": "control.json",
            "replication_tolerance": 0,
            "replay_artifacts": ["predictions.json"],
        }

    def register(self):
        return self.lab.register(self.protocol, self.recipes)

    def worker(self, identity="executor", role="experiment"):
        self.lab.worker(identity, role, "local")
        return identity

    def test_atomic_claim_and_budget_reservation(self):
        self.register()
        self.worker()
        with ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(lambda _: self.lab.claim("executor"), range(8)))
        claimed = [x for x in claims if x]
        self.assertEqual(len(claimed), 2)
        self.assertEqual(len({x["id"] for x in claimed}), 2)
        self.assertEqual(self.lab.status()["programs"][0]["reserved_seconds"], 4)

    def test_frozen_registration_is_idempotent_and_change_rejected(self):
        self.register()
        self.register()
        self.assertEqual(len(self.lab.status()["tasks"]), 8)
        changed = dict(self.protocol, minimum_effect=0.2)
        with self.assertRaisesRegex(LabError, "immutable"):
            self.lab.register(changed, self.recipes)

    def test_missing_controls_and_repeated_seeds_fail_closed(self):
        for changed in (dict(controls=[]), dict(seeds=[1, 1, 1]), dict(minimum_effect=-1)):
            with self.subTest(changed=changed), self.assertRaises(LabError):
                self.lab.register({**self.protocol, **changed}, self.recipes)

    def test_mutated_input_cannot_be_dispatched(self):
        self.register()
        snapshot = self.lab.snapshot("exp")
        (snapshot / "worker.py").write_text("print('changed')")
        self.worker()
        with self.assertRaisesRegex(LabError, "snapshot"):
            self.lab.claim("executor")

    def test_lost_worker_is_quarantined_and_stale_completion_rejected(self):
        self.register()
        self.worker()
        task = self.lab.claim("executor", lease_seconds=1, now=100)
        self.lab.expire(now=102)
        self.assertEqual(self.lab.task(task["id"])["status"], "lost")
        with self.assertRaises(LabError):
            self.lab.finish(task["id"], task["token"], "failed", {}, 0)
        with self.assertRaisesRegex(LabError, "stopped"):
            self.lab.recover(task["id"])
        self.lab.recover(task["id"], confirmed_stopped=True)
        self.assertEqual(self.lab.task(task["id"])["status"], "failed")

    def test_paid_resource_requires_declared_authorization(self):
        self.lab.resource("gpu", "gpu", 1, 100)
        self.protocol["resource"] = "gpu"
        with self.assertRaisesRegex(LabError, "paid"):
            self.register()

    def test_no_program_cap_overcommit(self):
        self.lab.program("small", "small", 2, 0)
        self.protocol["program"] = "small"
        self.register()
        self.worker()
        self.assertIsNotNone(self.lab.claim("executor"))
        self.assertIsNone(self.lab.claim("executor"))

    def test_dependency_failure_blocks_review_and_missing_science_is_unknown(self):
        self.register()
        self.worker()
        task = self.lab.claim("executor")
        self.lab.finish(task["id"], task["token"], "failed", {"error": "fixture"}, 1)
        self.lab.worker("reviewer", "review", "local")
        self.assertIsNone(self.lab.claim("reviewer"))
        summary = self.lab.synthesize("exp")
        self.assertEqual(summary["conclusion"], "INCOMPLETE")
        self.assertEqual(summary["scientific_qualification"], "NOT_QUALIFIED")

    def test_checkpoint_survives_reopen_and_wrong_token_rejected(self):
        self.register()
        self.worker()
        task = self.lab.claim("executor")
        self.lab.checkpoint(task["id"], task["token"], {"step": 12, "next": "evaluate"})
        reopened = Controller(self.root / "lab")
        self.assertEqual(reopened.task(task["id"])["checkpoint"]["step"], 12)
        with self.assertRaises(LabError):
            reopened.heartbeat(task["id"], "wrong")

    def test_unknown_fields_and_external_input_paths_rejected(self):
        with self.assertRaises(LabError):
            self.lab.register({**self.protocol, "ignore_gate": True}, self.recipes)
        self.protocol["candidate"] = "../escape.json"
        with self.assertRaises(LabError):
            self.register()

    def test_database_foreign_keys_enabled(self):
        with self.lab.connect() as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO workers(id,role,resource) VALUES ('bad','experiment','missing')"
            )

    def complete_primaries(self):
        from research_lab.execution import run_worker

        self.register()
        self.worker()
        self.assertEqual(run_worker(self.lab, "executor"), 6)

    def test_real_execution_clean_replay_separate_review_and_publication(self):
        from research_lab.evidence import prepare_publication
        from research_lab.execution import evidence_pin, run_worker

        self.complete_primaries()
        self.lab.worker("replicator", "replication", "local")
        self.assertEqual(run_worker(self.lab, "replicator"), 1)
        self.lab.worker("reviewer", "review", "local")
        review = self.lab.claim("reviewer")
        receipt = {
            "evidence_pin": evidence_pin(self.lab, "exp"),
            "verdict": "clean",
            "findings": [],
            "independence": "SEPARATE_SESSION_OPERATOR_ASSERTED",
            "summary": "test fixture",
        }
        self.lab.finish(review["id"], review["token"], "succeeded", receipt, 0.1)
        summary = self.lab.synthesize("exp")
        self.assertEqual(summary["conclusion"], "BOUNDED_CONTRAST_NOT_SUPPORTED")
        self.assertTrue(summary["replicated"])
        self.assertTrue(summary["reviewed"])
        packet = prepare_publication(self.lab, "exp", self.root / "packet")
        self.assertEqual(packet["external_replication"], "NOT_PERFORMED")
        self.assertTrue((self.root / "packet" / "MANUSCRIPT.md").is_file())

    def test_aliases_cannot_self_replicate_or_review(self):
        from research_lab.execution import run_worker

        self.complete_primaries()
        self.lab.worker("fake-replica", "replication", "local", principal="executor")
        self.assertIsNone(self.lab.claim("fake-replica"))
        self.lab.worker("replicator", "replication", "local")
        run_worker(self.lab, "replicator")
        for principal in ("executor", "designer", "replicator"):
            self.lab.worker("review-" + principal, "review", "local", principal=principal)
            self.assertIsNone(self.lab.claim("review-" + principal))

    def test_altered_evidence_invalidates_synthesis(self):
        self.complete_primaries()
        task = next(x for x in self.lab.status()["tasks"] if x["role"] == "experiment")
        output = self.lab.root / "runs" / task["result"]["run_id"] / "output" / "predictions.json"
        output.write_text("[0,0,0,0]")
        self.assertEqual(self.lab.synthesize("exp")["conclusion"], "INVALID_EVIDENCE")

    def test_fabricated_completion_cannot_be_success(self):
        self.register()
        self.worker()
        task = self.lab.claim("executor")
        with self.assertRaises(LabError):
            self.lab.finish(
                task["id"],
                task["token"],
                "succeeded",
                {"run_id": "made-up", "record_pin": "0" * 64},
                0.1,
            )

    def test_knowledge_keeps_conflicts_and_rejects_mutation(self):
        from research_lab.evidence import link, put_node, retrieve

        put_node(self.lab, "old", "finding", {"claim": "memory is robust", "source": "reported"})
        put_node(
            self.lab, "new", "failure", {"claim": "memory fails corrections", "source": "reported"}
        )
        link(self.lab, "new", "contradicts", "old")
        self.assertEqual(len(retrieve(self.lab, "memory")["nodes"]), 2)
        self.assertEqual(retrieve(self.lab)["links"][0]["relation"], "contradicts")
        with self.assertRaises(LabError):
            put_node(self.lab, "old", "finding", {"claim": "silently replaced"})

    def test_stale_or_inconsistent_review_cannot_promote(self):
        from research_lab.execution import run_worker

        self.complete_primaries()
        self.lab.worker("replicator", "replication", "local")
        run_worker(self.lab, "replicator")
        self.lab.worker("reviewer", "review", "local")
        task = self.lab.claim("reviewer")
        receipt = {
            "evidence_pin": "0" * 64,
            "verdict": "clean",
            "findings": [],
            "independence": "SEPARATE_SESSION_OPERATOR_ASSERTED",
            "summary": "stale",
        }
        with self.assertRaisesRegex(LabError, "stale"):
            self.lab.finish(task["id"], task["token"], "succeeded", receipt, 0.1)

    def test_designer_alias_resolves_to_frozen_principal(self):
        from research_lab.execution import run_worker

        self.lab.worker("designer-alias", "design", "local", principal="same-person")
        self.protocol["author"] = "designer-alias"
        self.complete_primaries()
        self.lab.worker("replicator", "replication", "local")
        run_worker(self.lab, "replicator")
        self.lab.worker("review-alias", "review", "local", principal="same-person")
        self.assertIsNone(self.lab.claim("review-alias"))

    def test_frozen_author_cannot_be_reassigned_after_registration(self):
        self.register()
        with self.assertRaisesRegex(LabError, "author"):
            self.lab.worker("designer", "design", "local", principal="another-person")

    def test_tampered_snapshot_and_extra_inputs_invalidate_synthesis_and_packet(self):
        from research_lab.evidence import prepare_publication

        self.complete_primaries()
        frozen = self.lab.snapshot("exp")
        original = (frozen / "protocol.json").read_bytes()
        (frozen / "protocol.json").write_text('{"tampered":true}')
        self.assertEqual(self.lab.synthesize("exp")["conclusion"], "INVALID_EVIDENCE")
        with self.assertRaises(LabError):
            prepare_publication(self.lab, "exp", self.root / "bad-packet")
        self.assertFalse((self.root / "bad-packet").exists())
        (frozen / "protocol.json").write_bytes(original)
        (frozen / "unregistered.py").write_text("print('hidden input')")
        self.assertEqual(self.lab.synthesize("exp")["conclusion"], "INVALID_EVIDENCE")

    def test_failed_attempt_is_packaged_but_undeclared_files_are_excluded(self):
        from research_lab.evidence import prepare_publication
        from research_lab.execution import execute_claim

        (self.recipes / "worker.py").write_text("raise SystemExit(3)")
        self.register()
        self.worker()
        task = self.lab.claim("executor")
        execute_claim(self.lab, task)
        failed = self.lab.task(task["id"])
        self.assertEqual(failed["status"], "failed")
        run_id = failed["checkpoint"]["run_id"]
        (self.lab.root / "runs" / run_id / "UNDECLARED.txt").write_text("must not escape")
        prepare_publication(self.lab, "exp", self.root / "packet")
        self.assertTrue((self.root / "packet" / "runs" / run_id / "run.json").is_file())
        self.assertFalse((self.root / "packet" / "runs" / run_id / "UNDECLARED.txt").exists())
        attempts = json.loads((self.root / "packet" / "attempts.json").read_text())["attempts"]
        self.assertEqual(attempts[0]["checkpoint"]["run_id"], run_id)

    def test_expired_lease_cannot_be_resurrected_without_reaper(self):
        self.register()
        self.worker()
        task = self.lab.claim("executor", now=100)
        with self.assertRaisesRegex(LabError, "lease"):
            self.lab.heartbeat(task["id"], task["token"])

    def test_invalid_cli_review_leaves_queue_available_for_corrected_receipt(self):
        import contextlib
        import io

        from research_lab.__main__ import main
        from research_lab.execution import evidence_pin, run_worker

        self.complete_primaries()
        self.lab.worker("replicator", "replication", "local")
        run_worker(self.lab, "replicator")
        args = ["--root", str(self.lab.root), "review", "exp", "--worker", "reviewer", "--receipt"]
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([*args, str(self.root / "missing.json")]), 1)
            self.assertEqual(self.lab.task("exp.review")["status"], "queued")
            receipt = self.root / "review.json"
            payload = {
                "evidence_pin": "0" * 64,
                "verdict": "clean",
                "findings": [],
                "independence": "SEPARATE_SESSION_OPERATOR_ASSERTED",
                "summary": "fixture",
            }
            receipt.write_text(json.dumps(payload))
            self.assertEqual(main([*args, str(receipt)]), 1)
            self.assertEqual(self.lab.task("exp.review")["status"], "queued")
            payload["evidence_pin"] = evidence_pin(self.lab, "exp")
            receipt.write_text(json.dumps(payload))
            self.assertEqual(main([*args, str(receipt)]), 0)
        self.assertEqual(self.lab.task("exp.review")["status"], "succeeded")

    def test_one_execution_cannot_fill_two_declared_experiment_cells(self):
        from research_lab.execution import execute_claim

        self.register()
        self.worker()
        first = self.lab.claim("executor", task_id="exp.candidate.1")
        receipt = execute_claim(self.lab, first)
        second = self.lab.claim("executor", task_id="exp.control.1")
        with self.assertRaisesRegex(LabError, "already bound"):
            self.lab.finish(second["id"], second["token"], "succeeded", receipt, 0.1)

    def test_database_context_closes_its_connection(self):
        with self.lab.connect() as connection:
            self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
