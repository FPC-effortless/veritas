"""LANGMATH098 contextual normalized associative TAC, untrained candidate.

Two native key/value banks, distinct learned addresses and time ranges, contextual
writes and independently exposed reads. Two work-efficient affine scans replace
the old nonlinear feedback and graph solve. No labels or loss masks enter forward.
"""

import math
from dataclasses import dataclass

import torch
from torch import nn
from torch.nn import functional as F


def affine_scan(a, b, initial, *, parallel=True):
    """Inclusive scan of s'=a*s+b; a may broadcast over trailing state axes.

    Pair reduction plus reconstruction: O(T) state operations, O(log T) span.
    This is not a Hillis--Steele O(T log T) implementation. Never divides by a
    prefix product, so long horizons/underflow and a=0 are legitimate.
    """
    if b.ndim < 3 or b.shape[1] < 1 or a.shape[:2] != b.shape[:2] or initial.shape != b[:, 0].shape:
        raise ValueError("aligned nonempty batch/time/state required")
    length = b.shape[1]
    if length < 1:
        raise ValueError("nonempty scan required")
    if not parallel:
        state = initial
        result = []
        for i in range(length):
            state = a[:, i] * state + b[:, i]
            result.append(state)
        return torch.stack(result, 1)
    if length == 1:
        return a * initial[:, None] + b
    pairs = length // 2
    left_a, right_a = a[:, : 2 * pairs : 2], a[:, 1 : 2 * pairs : 2]
    left_b, right_b = b[:, : 2 * pairs : 2], b[:, 1 : 2 * pairs : 2]
    odds = affine_scan(right_a * left_a, right_a * left_b + right_b, initial, parallel=True)
    before_even = torch.cat((initial[:, None], odds), 1)[:, : (length + 1) // 2]
    evens = a[:, ::2] * before_even + b[:, ::2]
    paired = torch.stack((evens[:, :pairs], odds), 2).flatten(1, 2)
    return torch.cat((paired, evens[:, -1:]), 1) if length % 2 else paired


@dataclass(frozen=True)
class State098:
    owners: tuple[str, ...]
    clock: int
    tensors: dict[str, torch.Tensor]

    @property
    def arm(self):
        return "tac098"

    def tensor_bytes(self):
        return sum(v.numel() * v.element_size() for v in self.tensors.values())


class ContextualAssociativeTAC098(nn.Module):
    """100370 active learned parameters, 432 persistent floats per stream."""

    arm = "tac098"

    def __init__(self):
        super().__init__()
        self.embedding = nn.Embedding(256, 32)
        self.context_lag = nn.Parameter(torch.full((3, 32), 0.1))
        self.context_input = nn.Linear(32, 48)
        horizons = torch.logspace(math.log10(8.0), math.log10(4096.0), 48)
        self.raw_context_decay = nn.Parameter(torch.log(torch.expm1(1.0 / horizons)))
        self.address_value = nn.Linear(112, 66)
        self.compare = nn.Linear(130, 16)
        self.norm = nn.LayerNorm(162)
        self.ffn_up = nn.Linear(162, 138)
        self.ffn_gate = nn.Linear(162, 138)
        self.ffn_out = nn.Linear(138, 256)
        self.register_buffer("bank_min", torch.tensor([0.97, 0.995]))
        self.register_buffer("bank_max", torch.tensor([0.995, 0.99995]))
        self.read_epsilon = 1e-4

    def counts(self):
        return {
            "trainable": sum(p.numel() for p in self.parameters() if p.requires_grad),
            "deployed": sum(p.numel() for p in self.parameters()),
            "fixed_buffer_bytes": sum(p.numel() * p.element_size() for p in self.buffers()),
        }

    def start(self, owners):
        owners = tuple(owners)
        if (
            not owners
            or len(set(owners)) != len(owners)
            or any(type(o) is not str or not o for o in owners)
        ):
            raise ValueError("explicit unique nonempty stream owners required")
        shapes = {
            "context": (48,),
            "lexical": (3, 32),
            "previous_key": (2, 8),
            "memory": (2, 16, 8),
            "mass": (2, 8),
        }
        return State098(
            owners,
            0,
            {
                n: self.embedding.weight.new_zeros((len(owners), *shape))
                for n, shape in shapes.items()
            },
        )

    def validate(self, tokens, state, owners):
        if (
            not isinstance(tokens, torch.Tensor)
            or tokens.dtype != torch.long
            or tokens.ndim != 2
            or min(tokens.shape) < 1
            or bool((tokens < 0).any())
            or bool((tokens > 255).any())
        ):
            raise ValueError("observed nonempty Long[B,T] byte IDs required")
        if self.embedding.weight.dtype not in (torch.float32, torch.float64):
            raise ValueError("FP32/FP64 only until mixed-precision correspondence is qualified")
        if tokens.device != self.embedding.weight.device:
            raise ValueError("tokens and model must share a device")
        if (
            not owners
            or len(set(owners)) != len(owners)
            or any(type(o) is not str or not o for o in owners)
        ):
            raise ValueError("explicit unique nonempty stream owners required")
        # Validate metadata without allocating five throwaway zero tensors on
        # every streaming step. No learned-value or state cache is maintained.
        shapes = {
            "context": (48,),
            "lexical": (3, 32),
            "previous_key": (2, 8),
            "memory": (2, 16, 8),
            "mass": (2, 8),
        }
        if (
            state.owners != owners
            or type(state.clock) is not int
            or state.clock < 0
            or tokens.shape[0] != len(owners)
            or set(state.tensors) != set(shapes)
        ):
            raise ValueError("complete same-owner state and legitimate clock required")
        for name, tensor in state.tensors.items():
            if (
                not isinstance(tensor, torch.Tensor)
                or tensor.shape != (len(owners), *shapes[name])
                or tensor.dtype != self.embedding.weight.dtype
                or tensor.device != self.embedding.weight.device
                or not bool(torch.isfinite(tensor).all())
            ):
                raise ValueError("state tensor shape/precision/device/finite mismatch: " + name)

    def forward(
        self, tokens, *, state=None, owners=None, write_mask=None, parallel=True, return_trace=False
    ):
        if owners is None:
            owners = tuple(f"train-{i}" for i in range(tokens.shape[0]))
        owners = tuple(owners)
        if state is None:
            state = self.start(owners)
        self.validate(tokens, state, owners)
        batch, length = tokens.shape
        s = state.tensors
        if write_mask is None:
            write_mask = torch.ones_like(tokens, dtype=torch.bool)
        if (
            not isinstance(write_mask, torch.Tensor)
            or write_mask.shape != tokens.shape
            or write_mask.dtype != torch.bool
            or write_mask.device != tokens.device
        ):
            raise ValueError("legal write mask must be Bool[B,T] on source device")
        e = self.embedding(tokens).tanh()
        history = torch.cat((s["lexical"], e), 1)
        local = e
        for lag in range(3):
            local = local + self.context_lag[lag].tanh() * history[:, 2 - lag : 2 - lag + length]
        local = local.tanh()
        delta = torch.sigmoid(-self.raw_context_decay)
        context_offer = self.context_input(local).tanh()
        contexts = affine_scan(
            delta[None, None].expand(batch, length, -1),
            (1 - delta) * context_offer,
            s["context"],
            parallel=parallel,
        )
        past_context = torch.cat((s["context"][:, None], contexts[:, :-1]), 1)
        features = torch.cat((e, local, past_context), -1)
        raw = self.address_value(features)
        keys = raw[..., :16].reshape(batch, length, 2, 8).softmax(-1)
        queries = raw[..., 16:32].reshape(batch, length, 2, 8).softmax(-1)
        values = raw[..., 32:64].reshape(batch, length, 2, 16).tanh()
        alpha = self.bank_min + (self.bank_max - self.bank_min) * raw[..., 64:].sigmoid()
        previous = torch.cat((s["previous_key"][:, None], keys[:, :-1]), 1)
        legal = write_mask
        if state.clock == 0:
            legal = torch.cat((torch.zeros_like(legal[:, :1]), legal[:, 1:]), 1)
        a = torch.where(legal[..., None], alpha, torch.ones_like(alpha))
        offer = torch.cat(
            ((values[..., :, None] * previous[..., None, :]).flatten(-2), previous), -1
        )
        b = (1 - a[..., None]) * offer
        initial = torch.cat((s["memory"].flatten(-2), s["mass"]), -1)
        banks = affine_scan(a[..., None], b, initial, parallel=parallel)
        memory = banks[..., :128].reshape(batch, length, 2, 16, 8)
        mass = banks[..., 128:]
        numerator = (memory * queries[..., None, :]).sum(-1)
        evidence = (mass * queries).sum(-1)
        reads = numerator / (evidence[..., None] + self.read_epsilon)
        fast, slow = reads.unbind(-2)
        compare_input = torch.cat(
            (local, past_context, fast, slow, (fast - slow).abs(), evidence), -1
        )
        gate = self.compare(compare_input).sigmoid()
        mixed = gate * fast + (1 - gate) * slow
        z = self.norm(torch.cat((e, local, past_context, fast, slow, mixed, evidence), -1))
        logits = self.ffn_out(self.ffn_up(z) * F.silu(self.ffn_gate(z)))
        final = State098(
            owners,
            state.clock + length,
            {
                "context": contexts[:, -1],
                "lexical": history[:, -3:],
                "previous_key": keys[:, -1],
                "memory": memory[:, -1],
                "mass": mass[:, -1],
            },
        )
        if return_trace:
            return (
                logits,
                final,
                {
                    "keys": keys,
                    "queries": queries,
                    "values": values,
                    "alpha": a,
                    "memory": memory,
                    "mass": mass,
                    "reads": reads,
                    "evidence": evidence,
                    "compare_gate": gate,
                    "context": contexts,
                },
            )
        return logits, final
