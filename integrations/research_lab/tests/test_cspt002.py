"""No-fit source and anti-leakage checks for the CSPT002 diagnostic."""
import copy
import random
import sys
import unittest
from importlib import import_module
from pathlib import Path

# Works both next to the runner (archived diagnostic) and in the
# research_lab/tests directory after installation in Veritas.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
m = import_module("cspt002")


class DataIntegrity(unittest.TestCase):
    def test_paraphrase_preserves_structure_and_target(self):
        r = random.Random(25)
        for _ in range(100):
            w = m.sample_world(r, "train")
            a, b = m.render(w, 0), m.render(w, 1)
            self.assertNotEqual(a, b)
            self.assertEqual(a[-2:], b[-2:])
            self.assertEqual(w.answer(), w.final_owners()[w.queried_slot])
            self.assertEqual(m.tokens(a)[0], m.VOCAB["<cls>"])

    def test_receiver_intervention_changes_target_when_relevant(self):
        rng = random.Random(31)
        tested = 0
        for _ in range(100):
            w = m.sample_world(rng, "dev")
            swapped = w.receiver_swap()
            self.assertIsNotNone(swapped)
            self.assertNotEqual(m.render(w), m.render(swapped))
            self.assertEqual(w.owners, swapped.owners)
            if w.queried_slot == w.moved_slot:
                self.assertNotEqual(w.answer(), swapped.answer())
                tested += 1
            else:
                self.assertEqual(w.answer(), swapped.answer())
        self.assertGreater(tested, 20)

    def test_canonical_split_cannot_cross_paraphrases(self):
        rng = random.Random(33)
        tr = [m.sample_world(rng, "train") for _ in range(500)]
        dv = [m.sample_world(rng, "dev") for _ in range(100)]
        te = [m.sample_world(rng, "test") for _ in range(100)]
        t = {w.canonical() for w in tr}
        d = {w.canonical() for w in dv}
        e = {w.canonical() for w in te}
        self.assertFalse(t & d)
        self.assertFalse(t & e)
        self.assertFalse(d & e)
        # Same underlying state with alternate query must have same split.
        for w in tr + dv + te:
            other_query = m.World(w.owners, w.objects, w.receiver,
                                  w.moved_slot, 1-w.queried_slot)
            self.assertEqual(m.partition(w), m.partition(other_query))
        self.assertTrue(all(m.partition(w) == "train" for w in tr))
        self.assertTrue(all(m.partition(w) == "dev" for w in dv))
        self.assertTrue(all(m.partition(w) == "test" for w in te))

    def test_context_never_includes_post_state_or_answer_label(self):
        w = m.World((0, 1), (3, 4), 2, 0, 0)
        inp = m.render(w)
        target_only = m.render(w, target_only=True)
        self.assertNotIn("now", inp)
        self.assertIn("now", target_only)
        self.assertIn("e2", inp)  # legal receiver, not a leaked future label
        self.assertEqual(w.answer(), 2)
        self.assertEqual(w.before_answer(), 0)
        # The old first study leaked alternate queries of the same state.
        self.assertEqual(m.partition(w), m.partition(m.World(w.owners,
            w.objects, w.receiver, w.moved_slot, 1)))
        self.assertNotEqual(w.answer(), w.before_answer())
        # Only the training-side target contains post-action state.
        self.assertNotEqual(m.tokens(inp), m.tokens(target_only))

    def test_tokenizer_rejects_context_truncation(self):
        with self.assertRaises(ValueError):
            m.tokens(["<cls>"] * 33)


    def test_counterfactual_never_crosses_partition(self):
        r = random.Random(42)
        eligible = 0
        for _ in range(300):
            w = m.sample_world(r, "dev")
            alt = w.receiver_swap(same_split=True)
            if alt is not None:
                self.assertEqual(m.partition(alt), "dev")
                self.assertNotEqual(w.receiver, alt.receiver)
                eligible += 1
        self.assertGreater(eligible, 100)

    def test_shortcut_fails_joint_binding_gate(self):
        # A recipient-only predictor gets every transferred-item answer
        # and every receiver-intervention pair right without tracking state.
        r = random.Random(44)
        rows = [m.sample_world(r, "dev") for _ in range(100)]
        for w in rows:
            transferred = m.World(w.owners, w.objects, w.receiver, w.moved_slot, w.moved_slot)
            unchanged = m.World(w.owners, w.objects, w.receiver, w.moved_slot, 1-w.moved_slot)
            self.assertEqual(transferred.answer(), w.receiver)
            self.assertNotEqual(unchanged.answer(), w.receiver)
        shortcut_successes = sum(
            int(w.receiver == m.World(
                w.owners, w.objects, w.receiver, w.moved_slot, 1-w.moved_slot
            ).answer())
            for w in rows
        )
        self.assertEqual(shortcut_successes, 0)

    def test_sampling_reproducible(self):
        a, b = random.Random(181), random.Random(181)
        self.assertEqual([m.sample_world(a, "train") for _ in range(10)],
                         [m.sample_world(b, "train") for _ in range(10)])


class ModelIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import torch
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest("PyTorch is an optional fit dependency") from exc
        cls.torch = torch
        torch.set_num_threads(1)

    def test_forward_and_gradient_through_actual_backbone(self):
        torch = self.torch
        model = m.make_model(d=32, layers=1)
        scenarios = [m.sample_world(random.Random(i), "train") for i in range(8)]
        batch = m.batch_examples(scenarios)
        logits, rep = model(batch["context"])
        self.assertEqual(tuple(logits.shape), (8, len(m.ENTITIES)))
        self.assertEqual(tuple(rep.shape), (8, 32))
        loss = torch.nn.functional.cross_entropy(logits, batch["owner"])
        loss.backward()
        self.assertGreater(model.encoder.embedding.weight.grad.abs().sum().item(), 0)
        attention_gradient = (
            model.encoder.backbone.layers[0].self_attn.in_proj_weight.grad
        )
        self.assertGreater(attention_gradient.abs().sum().item(), 0)
        self.assertGreater(model.predictor[0].weight.grad.abs().sum().item(), 0)
        self.assertGreater(model.answer.weight.grad.abs().sum().item(), 0)

    def test_ema_target_is_separate_and_frozen(self):
        import torch
        model = m.make_model(d=32, layers=1)
        target = copy.deepcopy(model.encoder)
        for p in target.parameters():
            p.requires_grad_(False)
        before = [p.clone() for p in target.parameters()]
        with torch.no_grad():
            for p, q in zip(target.parameters(), model.encoder.parameters()):
                p.lerp_(q + 1, 0.01)
        self.assertTrue(all(not p.requires_grad for p in target.parameters()))
        self.assertTrue(any(not torch.equal(p, q) for p, q in zip(target.parameters(), before)))

    def test_post_state_tensor_separated_from_inference_input(self):
        w = m.World((0, 1), (3, 4), 2, 0, 0)
        batch = m.batch_examples([w])
        self.assertFalse(batch["context"].equal(batch["target_post"]))

    def test_no_labels_passed_to_inference(self):
        torch = self.torch
        model = m.make_model(d=32, layers=1).eval()
        world = m.sample_world(random.Random(8), "train")
        original = m.batch_examples([world])
        with torch.no_grad():
            p0 = model(original["context"])[0]
            altered = {**original, "owner": original["owner"]*0,
                       "owner_before": original["owner_before"]*0,
                       "target_post": torch.zeros_like(original["target_post"])}
            p1 = model(altered["context"])[0]
        self.assertTrue(torch.equal(p0, p1))

    def test_same_online_parameter_count_across_arms(self):
        torch = self.torch
        torch.manual_seed(3)
        model = m.make_model(d=48, layers=2)
        self.assertGreater(m.count_parameters(model), 10000)
        self.assertEqual(tuple(model(self.torch.tensor([m.tokens(m.render(
            m.sample_world(random.Random(5), "train"))) ]))[0].shape), (1, len(m.ENTITIES)))


if __name__ == "__main__":
    unittest.main()
