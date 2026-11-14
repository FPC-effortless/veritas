import unittest

from trainlab.runner import LabError
from trainlab.token_memory_adapter import TokenMemory


def state():
    return {"tokens": []}


def step(tokens, value):
    value["tokens"].extend(tokens)
    return value["tokens"][-1], value


class MemoryAdapterTests(unittest.TestCase):
    def make(self, run=step, clone=None, identity="a" * 64):
        kwargs = {"clone_state": clone} if clone is not None else {}
        return TokenMemory(state, run, identity=identity, vocabulary_size=16, **kwargs)

    def test_query_discard_and_peer_restore(self):
        a, b = self.make(), self.make()
        a.update({"op": "tokens", "tokens": [1, 2]})
        snap = a.snapshot()
        self.assertEqual(a.query([3]), 3)
        self.assertEqual(a.snapshot().state["tokens"], [1, 2])
        b.restore(snap)
        b.update({"op": "tokens", "tokens": [4]})
        a.update({"op": "tokens", "tokens": [5]})
        b.restore(snap)
        self.assertEqual(b.snapshot().state["tokens"], [1, 2])
        self.assertEqual(a.snapshot().state["tokens"], [1, 2, 5])

    def test_update_failure_preserves_last_admitted_state(self):
        def faulty(tokens, value):
            answer, value = step(tokens, value)
            if answer == 5:
                raise ValueError("injected")
            return answer, value

        memory = self.make(faulty)
        memory.update({"op": "tokens", "tokens": [2]})
        with self.assertRaises(ValueError):
            memory.update({"op": "tokens", "tokens": [5]})
        self.assertEqual(memory.snapshot().state["tokens"], [2])

    def test_unsupported_input_and_foreign_snapshot_rejected(self):
        a, b = self.make(), self.make(identity="b" * 64)
        for event in (
            {"op": "DELETE", "tokens": [1]},
            {"op": "tokens", "tokens": [True]},
            {"op": "tokens", "tokens": [16]},
        ):
            with self.subTest(event=event), self.assertRaises(LabError):
                a.update(event)
        with self.assertRaises(LabError):
            b.restore(a.snapshot())

    def test_rejected_output_and_callback_alias_are_explicit(self):
        with self.assertRaises(LabError):
            self.make(lambda ids, value: (float("nan"), value)).query([1])
        with self.assertRaises(LabError):
            self.make(clone=lambda value: value).query([1])

    def test_malformed_and_excessive_history_fails_before_execution(self):
        def should_not_run(tokens, value):
            raise AssertionError("validation must finish before execution")

        memory = self.make(should_not_run)
        for history in ([[1] * 1025], ["unexpected"], [[1] * 1024] * 65):
            with self.subTest(length=len(history)), self.assertRaises(LabError):
                memory.predict_rows([{"id": "x", "input": {"history": history, "query": [1]}}])

    def test_row_predictions_have_isolated_fresh_state_and_order(self):
        memory = self.make(lambda ids, s: (len(step(ids, s)[1]["tokens"]), s))
        memory.update({"op": "tokens", "tokens": [7]})
        rows = [
            {"id": "b", "input": {"history": [[1, 2]], "query": [3]}},
            {"id": "a", "input": {"history": [], "query": [4]}},
        ]
        self.assertEqual(
            memory.predict_rows(rows),
            [
                {"id": "b", "output": 3},
                {"id": "a", "output": 1},
            ],
        )
        self.assertEqual(memory.snapshot().state["tokens"], [7])
