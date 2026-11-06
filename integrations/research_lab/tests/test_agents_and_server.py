import http.client
import json
import threading
import unittest

import test_controller as fixtures
from research_lab.agents import register_order
from research_lab.evidence import put_node, retrieve
from research_lab.execution import run_worker
from research_lab.server import LabWorkspace
from trainlab.runner import write_json
from trainlab.server import Dashboard


class AgentAndServerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ControllerTests("test_atomic_claim_and_budget_reservation")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.lab = self.fixture.lab
        self.root = self.fixture.root
        self.recipes = self.fixture.recipes

    def order(self, *, malformed=False):
        put_node(self.lab, "prior-failure", "failure", {"summary": "correction failed"})
        result = {
            "schema": "research_lab.agent_result.v1",
            "role": "design",
            "summary": "Design falsifies stale associations",
            "findings": [],
            "proposals": [{}] if malformed else [],
            "source_nodes": ["prior-failure"],
            "next_actions": ["Compare latest-write and stale controls"],
        }
        (self.recipes / "agent.py").write_text(
            "import os,json\nfrom pathlib import Path\n"
            "context=json.loads(Path('lab_context.json').read_text())\n"
            "assert context['nodes'][0]['body']['summary']=='correction failed'\n"
            "out=Path(os.environ['TRAINLAB_OUTPUT_DIR'])\n"
            "(out/'metrics.json').write_text('{\"completed\":1}')\n"
            f"(out/'agent_result.json').write_text(json.dumps({result!r}))\n"
        )
        config = {
            "schema": "trainlab.experiment.v1",
            "name": "constructed role bridge",
            "description": "test double, no LLM inference",
            "command": [__import__("sys").executable, "agent.py"],
            "seed": 1,
            "timeout_seconds": 2,
            "source_kind": "CONSTRUCTED",
            "split_identity": "no-training",
            "inputs": ["agent.py"],
            "artifacts": ["agent_result.json"],
            "metrics": {"completed": "max"},
            "budget": {"external_model_calls": 0},
        }
        write_json(self.recipes / "agent.json", config)
        order = {
            "schema": "research_lab.work_order.v1",
            "id": "design-order",
            "program": "p",
            "author": "director",
            "role": "design",
            "resource": "local",
            "slots": 1,
            "max_attempts": 1,
            "priority": 1,
            "objective": "Design a correction falsifier",
            "acceptance": ["Name a stale-value alternative"],
            "context_nodes": ["prior-failure"],
            "dependencies": [],
            "recipe": "agent.json",
            "source_commit": "a" * 40,
        }
        register_order(self.lab, order, self.recipes)
        self.lab.worker("design-session", "design", "local")

    def test_role_worker_receives_frozen_context_and_indexes_unverified_output(self):
        self.order()
        self.assertEqual(run_worker(self.lab, "design-session"), 1)
        self.assertEqual(self.lab.task("design-order.agent")["status"], "succeeded")
        node = retrieve(self.lab, "agent.design-order")["nodes"][0]
        self.assertEqual(node["body"]["origin"], "AGENT_AUTHORED_UNVERIFIED")

    def test_malformed_nested_output_fails_without_partial_success_or_worker_crash(self):
        self.order(malformed=True)
        self.assertEqual(run_worker(self.lab, "design-session"), 1)
        self.assertEqual(self.lab.task("design-order.agent")["status"], "failed")
        self.assertEqual(retrieve(self.lab, "agent.design-order")["nodes"], [])

    def test_index_collision_rolls_back_success_and_preserves_prior_knowledge(self):
        self.order()
        put_node(self.lab, "agent.design-order", "failure", {"summary": "existing record"})
        self.assertEqual(run_worker(self.lab, "design-session"), 1)
        self.assertEqual(self.lab.task("design-order.agent")["status"], "failed")
        self.assertEqual(retrieve(self.lab, "agent.design-order")["nodes"][0]["kind"], "failure")

    def test_actual_http_is_read_only_same_origin_and_does_not_expose_tokens(self):
        server = Dashboard(self.lab.root, None, 0, workspace_factory=LabWorkspace)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request("GET", "/api/lab/state")
            response = connection.getresponse()
            state = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertIn("Content-Security-Policy", response.headers)
            self.assertNotIn("token", state)
            connection.request("GET", "/", headers={"Host": "attacker.invalid"})
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 403)
            connection.request(
                "POST", "/api/run", body="{}", headers={"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 405)
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_literature_catalog_can_append_and_revise_without_erasing_sources(self):
        from research_lab.adapters import import_catalog

        paper = {
            "id": "paper-a",
            "title": "Study A",
            "url": "https://example.org/a",
            "retrieved_at": "2026-11-01",
            "summary": "First finding",
            "relevance": "A control",
            "limitations": ["Abstract only"],
        }
        catalog = self.root / "catalog.json"
        write_json(catalog, {"schema": "research_lab.literature.v1", "papers": [paper]})
        import_catalog(self.lab, catalog)
        second = {**paper, "id": "paper-b", "title": "Study B"}
        write_json(catalog, {"schema": "research_lab.literature.v1", "papers": [paper, second]})
        import_catalog(self.lab, catalog)
        revised = {**paper, "summary": "Revised interpretation"}
        write_json(catalog, {"schema": "research_lab.literature.v1", "papers": [revised, second]})
        import_catalog(self.lab, catalog)
        papers = [x for x in retrieve(self.lab)["nodes"] if x["kind"] == "paper"]
        self.assertEqual(len(papers), 3)


if __name__ == "__main__":
    unittest.main()
