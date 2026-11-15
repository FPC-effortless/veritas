"""Queue expansion must preserve the operator's seed-bound research recipes."""

import copy
import unittest

import test_controller
from research_lab.core import LabError, validate_protocol
from trainlab.research_adequacy import recipe_identity
from trainlab.runner import read_json, write_json


class SeedRecipeAdmissionTests(unittest.TestCase):
    def setUp(self):
        test_controller.ControllerTests.setUp(self)

    def mapped(self):
        self.protocol["seed_recipes"] = {"candidate": {}, "control": {}}
        expected = {}
        for arm in ("candidate", "control"):
            base = read_json(self.recipes / f"{arm}.json")
            base["execution_purpose"] = "research"
            for seed in self.protocol["seeds"]:
                filename = f"{arm}.json" if seed == 1 else f"{arm}-{seed}.json"
                extra = f"{arm}-{seed}.txt"
                (self.recipes / extra).write_text(f"independent input {arm} {seed}")
                cfg = {**base, "seed": seed, "inputs": base["inputs"] + [extra]}
                write_json(self.recipes / filename, cfg)
                self.protocol["seed_recipes"][arm][str(seed)] = filename
                expected[arm, seed] = cfg
        return expected

    def test_research_default_refuses_implicit_seed_rewrite(self):
        cfg = read_json(self.recipes / "candidate.json")
        cfg.pop("execution_purpose")
        write_json(self.recipes / "candidate.json", cfg)
        with self.assertRaisesRegex(LabError, "exact seed_recipes"):
            self.lab.register(self.protocol, self.recipes)
        self.assertFalse(self.lab.snapshot("exp").exists())

    def test_assessed_diagnostic_also_cannot_be_rewritten(self):
        cfg = read_json(self.recipes / "candidate.json")
        cfg["research_adequacy"] = {"file": "adequacy.json", "sha256": "a" * 64}
        write_json(self.recipes / "candidate.json", cfg)
        with self.assertRaisesRegex(LabError, "exact seed_recipes"):
            self.lab.register(self.protocol, self.recipes)

    def test_exact_seed_identity_and_union_input_closure_preserved(self):
        expected = self.mapped()
        self.lab.register(self.protocol, self.recipes)
        for (arm, seed), cfg in expected.items():
            frozen = read_json(self.lab.snapshot("exp") / f"lab-{arm}-{seed}.json")
            self.assertEqual(frozen, cfg)
            self.assertEqual(recipe_identity(frozen), recipe_identity(cfg))
            for item in cfg["inputs"]:
                self.assertEqual(
                    (self.lab.snapshot("exp") / item).read_bytes(),
                    (self.recipes / item).read_bytes(),
                )
        self.assertEqual(len(self.lab.status()["tasks"]), 8)

    def test_missing_extra_seed_or_arm_is_rejected(self):
        self.mapped()
        baseline = copy.deepcopy(self.protocol)
        for mapping in (
            {},
            {"candidate": {}},
            {"candidate": {"1": "candidate.json"}, "control": baseline["seed_recipes"]["control"]},
        ):
            with self.subTest(mapping=mapping), self.assertRaises(LabError):
                validate_protocol({**baseline, "seed_recipes": mapping})
        changed = copy.deepcopy(baseline)
        changed["seed_recipes"]["candidate"]["4"] = "extra.json"
        with self.assertRaises(LabError):
            validate_protocol(changed)

    def test_wrong_seed_budget_split_purpose_or_replay_artifacts_rejected(self):
        self.mapped()
        path = self.recipes / "candidate-2.json"
        original = read_json(path)
        for change in (
            {"seed": 3},
            {"budget": {"episodes": 9}},
            {"split_identity": "different"},
            {"execution_purpose": "engineering_diagnostic"},
            {"artifacts": ["other.json"]},
        ):
            write_json(path, {**original, **change})
            with self.subTest(change=change), self.assertRaises(LabError):
                self.lab.register(self.protocol, self.recipes)
        self.assertFalse(self.lab.snapshot("exp").exists())

    def test_mapping_must_bind_the_declared_base(self):
        self.mapped()
        self.protocol["seed_recipes"]["candidate"]["1"] = "candidate-2.json"
        with self.assertRaisesRegex(LabError, "base recipe"):
            self.lab.register(self.protocol, self.recipes)

    def test_unassessed_diagnostics_keep_legacy_seed_expansion(self):
        self.lab.register(self.protocol, self.recipes)
        for seed in self.protocol["seeds"]:
            cfg = read_json(self.lab.snapshot("exp") / f"lab-candidate-{seed}.json")
            self.assertEqual(cfg["seed"], seed)
            self.assertEqual(cfg["execution_purpose"], "engineering_diagnostic")

    def lane(self):
        from research_lab.autonomy import register_lane

        write_json(self.recipes / "profile.json", self.protocol)
        spec = {
            "schema": "research_lab.autonomy.v1",
            "id": "lane",
            "program": "p",
            "initial": "first",
            "max_rounds": 1,
            "director": None,
            "profiles": {
                "first": {
                    "protocol": "profile.json",
                    "transitions": {
                        "BOUNDED_CONTRAST_SUPPORTED": None,
                        "BOUNDED_CONTRAST_NOT_SUPPORTED": None,
                    },
                }
            },
        }
        register_lane(self.lab, spec, self.recipes)
        return self.lab.root / "autonomy" / "lane"

    def test_autonomous_snapshot_preserves_all_seed_recipes_and_dispatches(self):
        from research_lab.autonomy import tick

        expected = self.mapped()
        frozen = self.lane()
        for (arm, seed), cfg in expected.items():
            filename = self.protocol["seed_recipes"][arm][str(seed)]
            self.assertEqual(read_json(frozen / filename), cfg)
            self.assertTrue(all((frozen / name).is_file() for name in cfg["inputs"]))
        tick(self.lab)
        tick(self.lab)
        self.assertEqual(len(self.lab.status()["tasks"]), 8)
        self.assertEqual(
            read_json(self.lab.snapshot("lane-r001") / "lab-candidate-2.json"),
            expected["candidate", 2],
        )

    def test_autonomous_seed_input_mutation_rejected(self):
        from research_lab.autonomy import tick

        self.mapped()
        frozen = self.lane()
        (frozen / "candidate-2.txt").write_text("changed")
        result = tick(self.lab)
        self.assertEqual(result[0]["phase"], "blocked")
        self.assertFalse(self.lab.status()["tasks"])

    def test_affordability_counts_each_seed_timeout(self):
        from research_lab.autonomy import _affordable

        self.mapped()
        self.assertTrue(_affordable(self.lab, self.protocol, self.recipes))
        path = self.recipes / "candidate-2.json"
        cfg = read_json(path)
        cfg["timeout_seconds"] = 40
        write_json(path, cfg)
        self.assertFalse(_affordable(self.lab, self.protocol, self.recipes))


if __name__ == "__main__":
    unittest.main()
