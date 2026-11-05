"""Constructed manager-brief tests; no model or live-host claims."""

import unittest

from research_lab.manager import manager_brief


class ManagerBriefTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "tasks": [],
            "autonomous_rounds": [],
            "autonomous_lanes": [{"id": "a", "phase": "ready", "reason": "secret error"}],
            "workers": [{"id": "w", "liveness": "REGISTERED_ONLY"}],
            "programs": [{
                "id": "p", "cap_seconds": 100, "charged_seconds": 40,
                "reserved_seconds": 10, "cap_microusd": 1000,
                "charged_microusd": 200, "reserved_microusd": 300,
                "allow_paid": 0,
            }],
        }

    def test_missing_round_does_not_invent_worker_or_fit(self):
        result = manager_brief(self.state)
        self.assertIsNone(result["lanes"][0]["round"])
        self.assertIn("DISPATCH", result["lanes"][0]["next_action"])
        self.assertEqual(result["model_fits"], "UNKNOWN_FROM_TASK_RECORDS")
        self.assertEqual(result["hosting"], "UNVERIFIED_FROM_CONTROLLER_STATE")
        self.assertEqual(result["registered_worker_count"], 1)
        self.assertEqual(result["program_budgets"][0]["remaining_declared_slot_seconds"], 50)
        self.assertEqual(result["program_budgets"][0]["remaining_declared_microusd"], 500)
        self.assertNotIn("secret error", str(result))

    def test_review_requires_independent_receipt(self):
        self.state["autonomous_rounds"].append({"lane": "a", "n": 1, "protocol": "a-r001"})
        self.state["autonomous_lanes"][0]["phase"] = "waiting"
        self.state["tasks"] = [
            {"protocol": "a-r001", "status": "succeeded", "role": "experiment"},
            {"protocol": "a-r001", "status": "succeeded", "role": "replication"},
            {"protocol": "a-r001", "status": "queued", "role": "review"},
        ]
        result = manager_brief(self.state)
        self.assertEqual(result["lanes"][0]["tasks"], {"queued": 1, "succeeded": 2})
        self.assertIn("independent", result["lanes"][0]["next_action"])
        self.assertEqual(result["task_counts"]["queued"], 1)

    def test_lost_task_blocks_and_shows_no_auto_recovery(self):
        self.state["autonomous_rounds"].append({"lane": "a", "n": 1, "protocol": "a-r001"})
        self.state["tasks"] = [{"protocol": "a-r001", "status": "lost", "role": "experiment"}]
        next_action = manager_brief(self.state)["lanes"][0]["next_action"]
        self.assertIn("confirm process stopped", next_action)

    def test_no_raw_task_result_or_error_leak_and_budget_stop(self):
        self.state["autonomous_lanes"][0]["phase"] = "budget_exhausted"
        self.state["tasks"] = [{
            "protocol": "other", "status": "failed", "role": "experiment",
            "result": {"error": "private-token-and-benchmark-label"},
        }]
        output = manager_brief(self.state)
        self.assertIn("STOP", output["lanes"][0]["next_action"])
        self.assertNotIn("private-token", str(output))
        self.assertEqual(output["task_counts"]["failed"], 1)

    def test_latest_round_selected_and_complete_stops(self):
        self.state["autonomous_rounds"] = [
            {"lane": "a", "n": 2, "protocol": "a-r002"},
            {"lane": "a", "n": 1, "protocol": "a-r001"},
        ]
        self.state["autonomous_lanes"][0]["phase"] = "complete"
        out = manager_brief(self.state)
        self.assertEqual(out["lanes"][0]["protocol"], "a-r002")
        self.assertIn("STOP", out["lanes"][0]["next_action"])


    def test_installed_cli_projects_real_controller_without_admitting_jobs(self):
        import io
        import json
        import tempfile
        from contextlib import redirect_stdout
        from pathlib import Path

        from research_lab.__main__ import main

        with tempfile.TemporaryDirectory() as directory:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["--root", str(Path(directory) / "lab"), "manager"])
            self.assertEqual(code, 0)
            projected = json.loads(buffer.getvalue())
            self.assertEqual(projected["schema"], "research_lab.manager_brief.v1")
            self.assertEqual(projected["lanes"], [])
            self.assertEqual(projected["task_counts"], {})
            self.assertEqual(projected["hosting"], "UNVERIFIED_FROM_CONTROLLER_STATE")

if __name__ == "__main__":
    unittest.main()
