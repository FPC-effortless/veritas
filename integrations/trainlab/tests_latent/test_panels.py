import copy
import os
import unittest
from pathlib import Path

import numpy as np
from trainlab.latent.panels import (
    association_families,
    audit_association_panel,
    condition_prompt,
    make_association_panel,
    make_copy_panel,
    make_cue_panel,
    position_conditions,
    position_contrasts,
    select_training_cues,
    split_association_families,
    training_byte_frequency,
)
from trainlab.runner import LabError


class LatentPanelTests(unittest.TestCase):
    @staticmethod
    def subset(panel, rows):
        result = copy.deepcopy(panel)
        for name, value in result.items():
            if isinstance(value, np.ndarray):
                result[name] = value[rows].copy()
        return result

    def test_complete_pair_does_not_pass_as_the_full_declared_design(self):
        panel = make_association_panel(family_ids=[0])
        self.assertEqual(len(panel["input_ids"]), 64)
        first_pair = panel["pair_ids"] == panel["pair_ids"][0]
        with self.assertRaises(LabError):
            audit_association_panel(self.subset(panel, first_pair))

    def test_every_declared_factor_is_required_even_when_remaining_pairs_are_complete(self):
        panel = make_association_panel(
            families=association_families(b"ab", b"ij"),
            values=b"ABCD",
            delays=(0, 8),
            include_local3=True,
            include_copy=True,
        )
        omissions = {
            "family": panel["family_ids"] != 0,
            "delay": panel["delay"] != 8,
            "order": panel["order"] != 1,
            "query": panel["query"] != 1,
            "value_pair": panel["candidate_ids"][:, 0] != ord("C"),
            "local_control": panel["condition"] != "local3",
            "copy_control": panel["task"] != "one_binding",
        }
        for factor, keep in omissions.items():
            with self.subTest(factor=factor), self.assertRaises(LabError):
                audit_association_panel(self.subset(panel, keep))

    def test_duplicate_pair_cannot_replace_another_cartesian_cell(self):
        panel = make_association_panel(family_ids=[0], values=b"AB")
        first = np.flatnonzero(panel["pair_ids"] == 0)
        second = np.flatnonzero(panel["pair_ids"] == 1)
        duplicate = copy.deepcopy(panel)
        for name, value in duplicate.items():
            if isinstance(value, np.ndarray) and name != "pair_ids":
                value[second] = value[first]
        self.assertEqual(len(duplicate["input_ids"]), len(panel["input_ids"]))
        with self.assertRaises(LabError):
            audit_association_panel(duplicate)

    def test_copy_and_lexical_panels_require_declared_key_and_value_coverage(self):
        panels = [
            make_copy_panel(keys=[b"ai", b"bi"], values=b"ABCD"),
            make_cue_panel([b"cat car bat bar mat mar " * 3], max_families=2),
        ]
        for panel in panels:
            with self.subTest(kind=panel["metadata"]["kind"]):
                self.assertEqual(panel["audit"]["scope"], "complete_declared_design")
                first_pair = panel["pair_ids"] == panel["pair_ids"][0]
                with self.assertRaises(LabError):
                    audit_association_panel(self.subset(panel, first_pair))
                without_key = panel["query_key_ids"] != panel["query_key_ids"][0]
                with self.assertRaises(LabError):
                    audit_association_panel(self.subset(panel, without_key))

    def test_design_metadata_is_consistent_and_detached_from_caller_mutation(self):
        families = association_families(b"ab", b"ij")
        panel = make_association_panel(families=families, values=b"ABCD", include_local3=True)
        families[0]["keys"][0] = b"zz".hex()
        self.assertEqual(audit_association_panel(panel)["status"], "PASS")
        changes = [
            lambda m: m.pop("design"),
            lambda m: m["design"].update(delays=[0]),
            lambda m: m["design"].update(include_local3=False),
            lambda m: m["design"].update(include_copy=True),
            lambda m: m["design"].update(key_ids=[0]),
            lambda m: m["families"].pop(),
            lambda m: m["families"].append(copy.deepcopy(m["families"][0])),
            lambda m: m["families"][0].update(stratum="neither"),
            lambda m: m["families"][0].update(key_ids=[0, 3]),
            lambda m: m.update(values=list(b"ABEF")),
        ]
        for index, change in enumerate(changes):
            bad = copy.deepcopy(panel)
            change(bad["metadata"])
            with self.subTest(change=index), self.assertRaises(LabError):
                audit_association_panel(bad)
        copy_panel = make_copy_panel(keys=[b"ai", b"bi"], values=b"AB")
        copy_panel["metadata"]["keys"][0] = b"zz".hex()
        with self.assertRaises(LabError):
            audit_association_panel(copy_panel)

    def test_full_key_counterfactual_pairs_and_position_matched_local_control(self):
        families = association_families(b"ab", b"ij")
        panel = make_association_panel(
            families=families, values=b"ABCD", delays=(0, 8), include_local3=True
        )
        self.assertEqual(panel["audit"]["status"], "PASS")
        self.assertEqual(panel["audit"]["value_coverage"], list(b"ABCD"))
        self.assertEqual(panel["audit"]["key_coverage"], [0, 1, 2, 3])
        for pair in np.unique(panel["pair_ids"][panel["condition"] == "local3"]):
            rows = np.flatnonzero(panel["pair_ids"] == pair)
            np.testing.assert_array_equal(panel["input_ids"][rows[0]], panel["input_ids"][rows[1]])
            self.assertNotEqual(panel["target_ids"][rows[0]], panel["target_ids"][rows[1]])
        bad = copy.deepcopy(panel)
        bad["target_ids"][0] = 255
        with self.assertRaises(LabError):
            audit_association_panel(bad)
        bad = copy.deepcopy(panel)
        bad["query"][0] = 1 - bad["query"][0]
        with self.assertRaises(LabError):
            audit_association_panel(bad)

    def test_split_has_every_key_without_family_leakage(self):
        families = association_families()
        result = split_association_families(families, seed=17)
        splits = [set(v) for v in result["splits"].values()]
        self.assertEqual([len(v) for v in result["splits"].values()], [96, 192, 1728])
        self.assertFalse(any(a & b for i, a in enumerate(splits) for b in splits[i + 1 :]))
        self.assertTrue(result["every_key_in_every_split"])
        self.assertEqual(result, split_association_families(families, seed=17))

    def test_copy_controls_and_budget_validation(self):
        panel = make_copy_panel(keys=[b"ai", b"bi"], values=b"AB")
        self.assertEqual(panel["audit"]["pairs"], 2)
        with self.assertRaises(LabError):
            make_association_panel(max_rows=10)
        with self.assertRaises(LabError):
            make_copy_panel(max_rows=0)

    def test_lexical_selection_uses_training_whole_words_and_counterfactuals(self):
        training = [b"cat car bat bar " * 3 + b"scat carrot "]
        selected = select_training_cues(training, max_families=1)
        self.assertEqual(selected["families"][0]["training_counts"], [3, 3, 3, 3])
        panel = make_cue_panel(training, max_families=1, delays=(0, 8))
        self.assertEqual(panel["audit"]["pairs"], 18)
        self.assertIn("one_binding", panel["task"])
        with self.assertRaises(LabError):
            select_training_cues(
                [{"split": "test", "text": "cat car bat bar " * 3}], max_families=1
            )
        with self.assertRaises(LabError):
            select_training_cues(training, max_families=2)

    def test_byte_frequency_boundaries_are_integer_exact_and_train_only(self):
        raw = b"a" * 9890 + b"b" * 100 + b"c" * 9 + b"d"
        result = training_byte_frequency([raw])
        self.assertEqual(result["total_bytes"], 10000)
        self.assertEqual(result["byte_groups"][[ord(c) for c in "abcdz"]].tolist(), [3, 3, 1, 1, 0])
        boundary = training_byte_frequency([b"a" * 9990 + b"b" * 10])
        self.assertEqual(boundary["byte_groups"][ord("b")], 2)

    def test_position_factorial_preserves_physical_bytes_and_last_four_filler(self):
        specs = {s["name"]: s for s in position_conditions()}
        self.assertEqual(len(specs), 11)
        self.assertEqual(specs["gap40_query16"]["position_ids"][-2:], [16, 17])
        self.assertEqual(specs["gap40_fillerwrap"]["position_ids"][8:48], list(range(8, 16)) * 5)
        native = condition_prompt(b"aiA biB ", b"ai", specs["gap40_native"])
        shifted = condition_prompt(b"aiA biB ", b"ai", specs["gap40_query16"])
        swapped = condition_prompt(b"aiA biB ", b"ai", specs["gap40_phase_swap"])
        self.assertEqual(native, shifted)
        self.assertEqual(native[-6:], swapped[-6:])
        self.assertNotEqual(native[8:-6], swapped[8:-6])
        self.assertEqual(len(position_contrasts()), 16)
        with self.assertRaises(LabError):
            position_conditions(position_limit=10)

    @unittest.skipUnless(
        os.environ.get("VERITAS_LATENT_ARCHIVE_ROOT"), "optional saved-study parity"
    )
    def test_cycle006_position_bytes_and_ids_match_archived_panel(self):
        path = (
            Path(os.environ["VERITAS_LATENT_ARCHIVE_ROOT"])
            / "latent_transfer_006/inputs/position_panels.npz"
        )
        with np.load(path, allow_pickle=False) as archive:
            native = bytes(archive["input_ids"][0, 0, :18])
            for index, spec in enumerate(position_conditions()):
                prompt = condition_prompt(native[:8], native[-2:], spec)
                self.assertEqual(prompt, bytes(archive["input_ids"][index, 0, : spec["length"]]))
                np.testing.assert_array_equal(
                    spec["position_ids"], archive["position_ids"][index, : spec["length"]]
                )


if __name__ == "__main__":
    unittest.main()
