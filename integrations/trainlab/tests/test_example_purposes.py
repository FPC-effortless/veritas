"""Shipped operational examples explicitly avoid pretending scientific admission."""

import ast
import json
import unittest
from pathlib import Path


class ExamplePurposeTests(unittest.TestCase):
    def test_all_shipped_recipe_producers_declare_their_nonclaim_scope(self):
        integrations = Path(__file__).resolve().parents[2]
        paths = []
        for component in ("trainlab", "forge", "research_lab"):
            paths.extend((integrations / component / "examples").rglob("*.py"))
            paths.extend((integrations / component / "examples").rglob("*.json"))
        paths.append(integrations / "research_lab/src/research_lab/ecosystem.py")
        found = set()
        for path in paths:
            if path.suffix == ".json":
                value = json.loads(path.read_text())
                dictionaries = [value] if isinstance(value, dict) else []
            else:
                dictionaries = []
                for node in ast.walk(ast.parse(path.read_text())):
                    if isinstance(node, ast.Dict):
                        dictionaries.append(
                            {
                                key.value: value.value
                                for key, value in zip(node.keys, node.values)
                                if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)
                            }
                        )
            for value in dictionaries:
                if value.get("schema") not in ("trainlab.experiment.v1", "trainlab.experiment.v2"):
                    continue
                found.add(path.name)
                expected = (
                    "historical_replay"
                    if path.name == "changing_state_replay.py"
                    else "engineering_diagnostic"
                )
                with self.subTest(path=str(path)):
                    self.assertEqual(value.get("execution_purpose"), expected)
        self.assertEqual(
            found,
            {
                "linear.json",
                "mean.json",
                "diagnose_dataset.py",
                "diagnose_data_quality.py",
                "diagnose_models.py",
                "diagnose_experiments.py",
                "diagnose_latent.py",
                "diagnose_state.py",
                "diagnose_session_cost.py",
                "dataset_quickstart.py",
                "model_workflow.py",
                "torch_workflow.py",
                "run_acceptance.py",
                "neural_loop_bootstrap.py",
                "changing_state_replay.py",
                "ecosystem.py",
            },
        )


if __name__ == "__main__":
    unittest.main()
