"""Bridge trusted native token models to TrainLab's state diagnostics."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .prediction_artifacts import _bytes, _hash, _require, _rows
from .research_diagnostics import Adapter


@dataclass(frozen=True)
class Snapshot:
    """An in-memory snapshot owned by the caller. The identity binds backend scope."""

    identity: str
    state: object


class TokenMemory:
    """Own state behind a bounded token interface for synchronous, trusted callbacks.

    The backend must construct fresh initial state and independently clone all
    mutable storage. The callback may mutate its working copy, but cannot mutate
    model weights, external state, or an earlier snapshot through a closed-over
    reference. The adapter does not inspect provider-specific hidden tensors.
    """

    def __init__(self, init_state, run_tokens, *, identity, vocabulary_size, clone_state=deepcopy):
        _require(
            all(callable(fn) for fn in (init_state, run_tokens, clone_state)),
            "native state callbacks required",
        )
        _require(
            _hash(identity) and type(vocabulary_size) is int and 2 <= vocabulary_size <= 2**31,
            "invalid backend identity or vocabulary",
        )
        self._init_state = init_state
        self._run_tokens = run_tokens
        self._clone_state = clone_state
        self.identity = identity
        self.vocabulary_size = vocabulary_size
        self.reset()

    def _clone(self, value):
        copied = self._clone_state(value)
        _require(copied is not value, "native clone returned the original state")
        return copied

    def reset(self):
        self._state = self._clone(self._init_state())

    def _tokens(self, tokens):
        _require(
            type(tokens) is list
            and 1 <= len(tokens) <= 1024
            and all(type(t) is int and 0 <= t < self.vocabulary_size for t in tokens),
            "bounded in-vocabulary token list required",
        )
        return tuple(tokens)

    def _run(self, tokens, state):
        result = self._run_tokens(tokens, state)
        _require(
            type(result) is tuple and len(result) == 2, "native runner must return (answer, state)"
        )
        answer, next_state = result
        _bytes(answer)
        return answer, next_state

    def update(self, event):
        _require(
            type(event) is dict and set(event) == {"op", "tokens"} and event["op"] == "tokens",
            "only explicit token updates are supported",
        )
        tokens = self._tokens(event["tokens"])
        _, next_state = self._run(tokens, self._clone(self._state))
        self._state = self._clone(next_state)

    def query(self, tokens):
        answer, _ = self._run(self._tokens(tokens), self._clone(self._state))
        return answer

    def snapshot(self):
        return Snapshot(self.identity, self._clone(self._state))

    def restore(self, snapshot):
        _require(
            type(snapshot) is Snapshot and snapshot.identity == self.identity,
            "snapshot belongs to another backend identity",
        )
        self._state = self._clone(snapshot.state)

    def predict_rows(self, rows):
        """Each input contains its own history; preserve row order and live state."""
        _rows(rows, "input", limit=128)
        request, total = [], 0
        for row in rows:
            value = row["input"]
            _require(
                type(value) is dict
                and set(value) == {"history", "query"}
                and type(value["history"]) is list
                and len(value["history"]) <= 128,
                "prediction row requires bounded history and query",
            )
            prefix = [self._tokens(block) for block in value["history"]]
            query = self._tokens(value["query"])
            total += sum(map(len, prefix)) + len(query)
            _require(total <= 65536, "prediction token budget exceeded")
            request.append((row["id"], prefix, query))
        result = []
        for identity, prefix, query in request:
            state = self._clone(self._init_state())
            for block in prefix:
                _, state = self._run(block, state)
            answer, _ = self._run(query, state)
            result.append({"id": identity, "output": answer})
        _bytes(result)
        return result

    def as_adapter(self, name, *, peer=None):
        operations = {
            "reset": self.reset,
            "update": self.update,
            "query": self.query,
            "snapshot": self.snapshot,
            "restore": self.restore,
            "predict_rows": self.predict_rows,
        }
        if peer is not None:
            _require(
                type(peer) is TokenMemory and peer is not self and peer.identity == self.identity,
                "independent peer with matching backend required",
            )
            operations.update(
                {
                    f"peer_{key}": getattr(peer, key)
                    for key in ("reset", "update", "query", "restore")
                }
            )
        return Adapter(
            name,
            operations,
            {
                "persists": "native state through declared token updates",
                "query_mutates": False,
                "reset": "fresh backend state",
            },
        )
