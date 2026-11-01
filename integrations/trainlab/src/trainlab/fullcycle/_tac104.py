"""LANGCACHE104: untrained deep associative cache candidate.

The state is owned by explicit streams and carries two compressed associative
banks, a separate oscillatory field, and a bounded recent-token KV cache per
layer.  This source supports differentiable chunk prefill and recurrent
inference; it is not a claim of measured GPU speed or trained capability.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, fields
from typing import Any

import torch
from torch import nn
from torch.nn import functional as F

from ._tac104_kernels import associative_read, rotary_scan


@dataclass(frozen=True)
class Config104:
    d_model: int = 128
    vocab_size: int = 256
    activation_checkpointing: bool = False
    n_layers: int = 4
    n_heads: int = 4
    key_dim: int = 16
    value_dim: int = 32
    write_rank: int = 2
    ffn_dim: int = 256
    window: int = 128
    chunk_size: int = 32
    rotary: bool = True
    local_rope: bool = True
    tied_embedding: bool = True

    def __post_init__(self):
        for name in (
            "vocab_size",
            "d_model",
            "n_layers",
            "n_heads",
            "key_dim",
            "value_dim",
            "write_rank",
            "ffn_dim",
            "window",
            "chunk_size",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if any(
            type(getattr(self, name)) is not bool
            for name in ("rotary", "local_rope", "tied_embedding", "activation_checkpointing")
        ):
            raise ValueError("rotary, local_rope and tied_embedding must be bool")
        if self.local_rope and self.key_dim % 2:
            raise ValueError("local RoPE key_dim must contain complete 2D pairs")
        if self.rotary and self.value_dim % 2:
            raise ValueError("rotary value_dim must contain complete 2D pairs")


@dataclass(frozen=True)
class LayerState104:
    fast_memory: torch.Tensor
    fast_mass: torch.Tensor
    slow_memory: torch.Tensor
    slow_mass: torch.Tensor
    rotary: torch.Tensor
    recent_key: torch.Tensor
    recent_value: torch.Tensor

    def tensors(self):
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def detach(self):
        return LayerState104(**{k: v.detach() for k, v in self.tensors().items()})


@dataclass(frozen=True)
class State104:
    owners: tuple[str, ...]
    clock: int
    layers: tuple[LayerState104, ...]
    config_signature: str

    @property
    def arm(self):
        return "langcache104"

    def detach(self):
        """Explicit truncated-BPTT boundary; forward never detaches silently."""
        return State104(
            self.owners, self.clock, tuple(x.detach() for x in self.layers), self.config_signature
        )

    def state_bytes(self):
        return sum(
            v.numel() * v.element_size() for layer in self.layers for v in layer.tensors().values()
        )

    def tensor_bytes(self):
        return self.state_bytes()

    def payload(self):
        """Plain metadata and named tensors; caller chooses safe serialization."""
        return {
            "schema": "tac-osm.langcache104-state.v2",
            "owners": self.owners,
            "clock": self.clock,
            "config_signature": self.config_signature,
            "layers": [layer.tensors() for layer in self.layers],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]):
        expected = {"schema", "owners", "clock", "layers", "config_signature"}
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("complete LANGCACHE104 state payload required")
        if payload["schema"] != "tac-osm.langcache104-state.v2":
            raise ValueError("unsupported state schema")
        signature = payload["config_signature"]
        if (
            type(signature) is not str
            or len(signature) != 64
            or any(char not in "0123456789abcdef" for char in signature)
        ):
            raise ValueError("canonical SHA-256 config signature required")
        owners = payload["owners"]
        if not isinstance(owners, (tuple, list)):
            raise ValueError("owners must be an ordered collection")
        if not isinstance(payload["layers"], (tuple, list)):
            raise ValueError("layers must be an ordered collection")
        names = {f.name for f in fields(LayerState104)}
        if any(not isinstance(layer, dict) or set(layer) != names for layer in payload["layers"]):
            raise ValueError("complete layer tensor payloads required")
        return cls(
            tuple(owners),
            payload["clock"],
            tuple(LayerState104(**layer) for layer in payload["layers"]),
            signature,
        )


class RMSNorm104(nn.Module):
    def __init__(self, width: int, epsilon: float = 1e-6):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(width))
        self.epsilon = epsilon

    def forward(self, x):
        return self.weight * x * torch.rsqrt(x.square().mean(-1, keepdim=True) + self.epsilon)


class AssociativeBank104(nn.Module):
    def __init__(self, config: Config104, retention_bias: float):
        super().__init__()
        self.config = config
        d, h, k, v, r = (
            config.d_model,
            config.n_heads,
            config.key_dim,
            config.value_dim,
            config.write_rank,
        )
        self.query = nn.Linear(d, h * k, bias=False)
        self.key = nn.Linear(d, h * r * k, bias=False)
        self.value = nn.Linear(d, h * r * v, bias=False)
        self.retention = nn.Linear(d, h)
        self.eligibility = nn.Linear(d, h)
        nn.init.constant_(self.retention.bias, retention_bias)
        nn.init.zeros_(self.eligibility.bias)

    def forward(self, x, memory, mass, write_mask, mode):
        b, t, _ = x.shape
        c = self.config
        q = self.query(x).reshape(b, t, c.n_heads, c.key_dim).softmax(-1)
        k = self.key(x).reshape(b, t, c.n_heads, c.write_rank, c.key_dim).softmax(-1)
        v = self.value(x).reshape(b, t, c.n_heads, c.write_rank, c.value_dim).tanh()
        alpha = self.retention(x).sigmoid()
        # A masked observation freezes THIS bank. It does not hide the observed
        # byte from the residual, local KV, or other prediction pathways.
        a = torch.where(write_mask[..., None], alpha, torch.ones_like(alpha))
        w = (1 - a) * self.eligibility(x).sigmoid()
        return associative_read(q, k, v, a, w, memory, mass, chunk_size=c.chunk_size, mode=mode)


class Block104(nn.Module):
    def __init__(self, config: Config104):
        super().__init__()
        self.config = config
        c = config
        self.memory_norm = RMSNorm104(c.d_model)
        self.fast = AssociativeBank104(c, 2.2)
        self.slow = AssociativeBank104(c, 5.3)
        self.local_query = nn.Linear(c.d_model, c.n_heads * c.key_dim, bias=False)
        self.local_key = nn.Linear(c.d_model, c.n_heads * c.key_dim, bias=False)
        self.local_value = nn.Linear(c.d_model, c.n_heads * c.value_dim, bias=False)
        if c.local_rope:
            self.register_buffer(
                "local_frequencies",
                torch.exp(-math.log(10000.0) * torch.arange(0, c.key_dim, 2) / c.key_dim),
            )
        if c.rotary:
            self.rotary_retention = nn.Linear(c.d_model, c.n_heads)
            self.rotary_angle = nn.Linear(c.d_model, c.n_heads * (c.value_dim // 2))
            self.rotary_offer = nn.Linear(c.d_model, c.n_heads * c.value_dim)
            nn.init.constant_(self.rotary_retention.bias, 2.2)
        # Different heads learn distinct comparison projections. Difference and
        # product features allow the mixer to compare rather than only average.
        lanes = 6 if c.rotary else 5  # fast, slow, difference, product, [field], KV
        self.perspective_out = nn.Linear(
            c.n_heads * (lanes * c.value_dim + 2), c.d_model, bias=False
        )
        self.ffn_norm = RMSNorm104(c.d_model)
        self.ffn_value = nn.Linear(c.d_model, c.ffn_dim, bias=False)
        self.ffn_gate = nn.Linear(c.d_model, c.ffn_dim, bias=False)
        self.ffn_out = nn.Linear(c.ffn_dim, c.d_model, bias=False)
        self.residual_scale = 1 / math.sqrt(2 * c.n_layers)

    def local_attention(self, x, previous_key, previous_value, clock):
        c = self.config
        b, t, _ = x.shape
        q = self.local_query(x).reshape(b, t, c.n_heads, c.key_dim).transpose(1, 2)
        new_key = self.local_key(x).reshape(b, t, c.n_heads, c.key_dim).transpose(1, 2)
        new_value = self.local_value(x).reshape(b, t, c.n_heads, c.value_dim).transpose(1, 2)
        if c.local_rope:
            # Cached keys are already rotated at their original stream position.
            # Positive associative addresses remain nonnegative and unrotated.
            if type(clock) is not int or clock < 0 or clock + t > 2**53:
                raise ValueError(
                    "RoPE observation positions must remain in exact float64 integer range"
                )
            # Use integer positions and double phase/trigonometry even for FP32
            # source activations. FP32 absolute clocks otherwise merge adjacent
            # positions after 2**24. This strict reference path is potentially
            # expensive on GPUs; relative phase kernels remain future work.
            positions = torch.arange(clock, clock + t, device=x.device, dtype=torch.long).to(
                torch.float64
            )
            phase = positions[:, None] * self.local_frequencies.to(torch.float64)[None, :]
            cosine = phase.cos().to(x.dtype)[None, None]
            sine = phase.sin().to(x.dtype)[None, None]

            def rotate(z):
                pairs = z.reshape(b, c.n_heads, t, c.key_dim // 2, 2)
                u, v = pairs.unbind(-1)
                return torch.stack((cosine * u - sine * v, sine * u + cosine * v), -1).flatten(-2)

            q, new_key = rotate(q), rotate(new_key)
        keys = torch.cat((previous_key, new_key), 2)
        values = torch.cat((previous_value, new_value), 2)
        past = previous_key.shape[2]
        outputs = []
        # Each tile has C queries and at most W+C-1 keys. We never construct a
        # T-by-T mask. SDPA chooses its backend; a fused/fast backend is not
        # asserted for every dtype, mask, or device.
        for begin in range(0, t, c.chunk_size):
            end = min(begin + c.chunk_size, t)
            left = max(0, past + begin - c.window + 1)
            right = past + end
            query_pos = torch.arange(past + begin, past + end, device=x.device)
            key_pos = torch.arange(left, right, device=x.device)
            legal = (key_pos[None, :] <= query_pos[:, None]) & (
                key_pos[None, :] > query_pos[:, None] - c.window
            )
            output = F.scaled_dot_product_attention(
                q[:, :, begin:end],
                keys[:, :, left:right],
                values[:, :, left:right],
                attn_mask=legal[None, None],
                dropout_p=0.0,
                is_causal=False,
            )
            outputs.append(output.transpose(1, 2))
        keep = c.window - 1
        # The copied suffix owns its storage. A view would retain the entire
        # prefill allocation even though its logical tensor_bytes is small.
        final_key = keys[:, :, -keep:].clone() if keep else keys[:, :, :0].clone()
        final_value = values[:, :, -keep:].clone() if keep else values[:, :, :0].clone()
        return torch.cat(outputs, 1), final_key, final_value

    def forward(self, x, state: LayerState104, write_mask, mode, clock):
        c = self.config
        b, t, _ = x.shape
        normalized = self.memory_norm(x)
        fast, fast_memory, fast_mass, fast_evidence = self.fast(
            normalized, state.fast_memory, state.fast_mass, write_mask, mode
        )
        slow, slow_memory, slow_mass, slow_evidence = self.slow(
            normalized, state.slow_memory, state.slow_mass, write_mask, mode
        )
        recent, recent_key, recent_value = self.local_attention(
            normalized, state.recent_key, state.recent_value, clock
        )
        pieces = [fast, slow, fast - slow, fast * slow]
        rotary_final = state.rotary
        if c.rotary:
            alpha = self.rotary_retention(normalized).sigmoid()[..., None]
            a = torch.where(write_mask[..., None, None], alpha, torch.ones_like(alpha))
            theta = math.pi * self.rotary_angle(normalized).tanh().reshape(
                b, t, c.n_heads, c.value_dim // 2
            )
            theta = torch.where(write_mask[..., None, None], theta, torch.zeros_like(theta))
            offer = self.rotary_offer(normalized).tanh().reshape(b, t, c.n_heads, c.value_dim)
            trajectory = rotary_scan(
                a, theta, offer, state.rotary, mode="parallel" if mode == "chunk" else "recurrent"
            )
            pieces.append(trajectory)
            rotary_final = trajectory[:, -1].clone()
        pieces.extend([recent, fast_evidence[..., None], slow_evidence[..., None]])
        comparisons = torch.cat(pieces, -1).flatten(-2)
        x = x + self.residual_scale * self.perspective_out(comparisons)
        normalized = self.ffn_norm(x)
        x = x + self.residual_scale * self.ffn_out(
            self.ffn_value(normalized) * F.silu(self.ffn_gate(normalized))
        )
        final = LayerState104(
            fast_memory, fast_mass, slow_memory, slow_mass, rotary_final, recent_key, recent_value
        )
        return x, final


class DeepCacheTAC104(nn.Module):
    arm = "langcache104"

    def __init__(self, config: Config104 | None = None):
        super().__init__()
        self.config = config or Config104()
        if not isinstance(self.config, Config104):
            raise ValueError("Config104 required")
        self.config_signature = hashlib.sha256(
            json.dumps(asdict(self.config), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        c = self.config
        self.embedding = nn.Embedding(c.vocab_size, c.d_model)
        nn.init.normal_(self.embedding.weight, mean=0.0, std=0.02)
        self.blocks = nn.ModuleList(Block104(c) for _ in range(c.n_layers))
        self.output_norm = RMSNorm104(c.d_model)
        self.output = nn.Linear(c.d_model, c.vocab_size, bias=False)
        if c.tied_embedding:
            self.output.weight = self.embedding.weight

    def counts(self):
        return {
            "trainable": sum(p.numel() for p in self.parameters() if p.requires_grad),
            "deployed": sum(p.numel() for p in self.parameters()),
            "fixed_buffer_bytes": sum(p.numel() * p.element_size() for p in self.buffers()),
        }

    @staticmethod
    def _owners(owners):
        if not isinstance(owners, (tuple, list)):
            raise ValueError("explicit ordered stream owners required")
        owners = tuple(owners)
        if (
            not owners
            or any(type(x) is not str or not x for x in owners)
            or len(set(owners)) != len(owners)
        ):
            raise ValueError("unique nonempty string stream owners required")
        return owners

    def start(self, owners):
        owners = self._owners(owners)
        c = self.config
        b = len(owners)
        new = self.embedding.weight.new_zeros
        states = tuple(
            LayerState104(
                new((b, c.n_heads, c.value_dim, c.key_dim)),
                new((b, c.n_heads, c.key_dim)),
                new((b, c.n_heads, c.value_dim, c.key_dim)),
                new((b, c.n_heads, c.key_dim)),
                new((b, c.n_heads, c.value_dim)),
                new((b, c.n_heads, 0, c.key_dim)),
                new((b, c.n_heads, 0, c.value_dim)),
            )
            for _ in range(c.n_layers)
        )
        return State104(owners, 0, states, self.config_signature)

    def validate(self, tokens, state, owners):
        if (
            not isinstance(tokens, torch.Tensor)
            or tokens.dtype != torch.long
            or tokens.ndim != 2
            or min(tokens.shape) < 1
            or bool((tokens < 0).any())
            or bool((tokens >= self.config.vocab_size).any())
        ):
            raise ValueError("observed nonempty Long[B,T] vocabulary IDs required")
        if torch.is_autocast_enabled("cpu") or torch.is_autocast_enabled("cuda"):
            raise ValueError(
                "autocast is unsupported until mixed-precision correspondence is qualified"
            )
        weight = self.embedding.weight
        if weight.dtype not in (torch.float32, torch.float64):
            raise ValueError("FP32/FP64 only until mixed-precision correspondence is qualified")
        if tokens.device != weight.device:
            raise ValueError("tokens and model must share device")
        if (
            not isinstance(state, State104)
            or state.owners != owners
            or type(state.clock) is not int
            or state.clock < 0
            or tokens.shape[0] != len(owners)
            or len(state.layers) != self.config.n_layers
        ):
            raise ValueError("complete same-owner layer state and legal clock required")
        if state.config_signature != self.config_signature:
            raise ValueError("carried state configuration does not match model")
        c, b = self.config, len(owners)
        if c.local_rope and state.clock + tokens.shape[1] > 2**53:
            raise ValueError(
                "RoPE observation positions must remain in exact float64 integer range"
            )
        cache_length = min(state.clock, c.window - 1)
        shapes = {
            "fast_memory": (b, c.n_heads, c.value_dim, c.key_dim),
            "slow_memory": (b, c.n_heads, c.value_dim, c.key_dim),
            "fast_mass": (b, c.n_heads, c.key_dim),
            "slow_mass": (b, c.n_heads, c.key_dim),
            "rotary": (b, c.n_heads, c.value_dim),
            "recent_key": (b, c.n_heads, cache_length, c.key_dim),
            "recent_value": (b, c.n_heads, cache_length, c.value_dim),
        }
        for layer in state.layers:
            if not isinstance(layer, LayerState104):
                raise ValueError("typed layer state required")
            for name, shape in shapes.items():
                value = getattr(layer, name)
                if (
                    not isinstance(value, torch.Tensor)
                    or value.shape != shape
                    or value.device != weight.device
                    or value.dtype != weight.dtype
                    or not bool(torch.isfinite(value).all())
                ):
                    raise ValueError("state shape/precision/device/finite mismatch: " + name)

    def forward(self, tokens, *, state=None, owners=None, write_mask=None, mode="chunk"):
        if mode not in ("chunk", "recurrent"):
            raise ValueError("mode must be chunk or recurrent")
        if owners is None:
            if state is not None:
                raise ValueError("explicit owners required when continuing carried state")
            if not isinstance(tokens, torch.Tensor) or tokens.ndim != 2:
                raise ValueError("Long[B,T] byte IDs required")
            owners = tuple(f"fresh-{i}" for i in range(tokens.shape[0]))
        owners = self._owners(owners)
        if state is None:
            state = self.start(owners)
        self.validate(tokens, state, owners)
        if write_mask is None:
            write_mask = torch.ones_like(tokens, dtype=torch.bool)
        if (
            not isinstance(write_mask, torch.Tensor)
            or write_mask.dtype != torch.bool
            or write_mask.shape != tokens.shape
            or write_mask.device != tokens.device
        ):
            raise ValueError("write_mask must be Bool[B,T] on source device")
        x = self.embedding(tokens)
        final_layers = []
        for block, layer_state in zip(self.blocks, state.layers):
            if self.config.activation_checkpointing and self.training and torch.is_grad_enabled():
                from torch.utils.checkpoint import checkpoint

                def apply(value, b=block, incoming=layer_state):
                    return b(value, incoming, write_mask, mode, state.clock)

                x, final = checkpoint(apply, x, use_reentrant=False)
            else:
                x, final = block(x, layer_state, write_mask, mode, state.clock)
            final_layers.append(final)
        logits = self.output(self.output_norm(x))
        return logits, State104(
            owners, state.clock + tokens.shape[1], tuple(final_layers), self.config_signature
        )

    def step(self, tokens, *, state, owners, write_mask=None):
        if not isinstance(tokens, torch.Tensor) or tokens.ndim != 2 or tokens.shape[1] != 1:
            raise ValueError("step requires Long[B,1]")
        return self(tokens, state=state, owners=owners, write_mask=write_mask, mode="recurrent")
