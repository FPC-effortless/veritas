"""Native PyTorch Transformer and pinned LANGMATH098 backend adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.checkpoint import checkpoint

from trainlab.runner import LabError


@dataclass(frozen=True)
class ModelConfig:
    backend: str = "transformer"
    vocab_size: int = 512
    width: int = 144
    layers: int = 4
    heads: int = 4
    context: int = 128
    activation_checkpointing: bool = False
    native: dict | None = None

    def validate(self):
        if (
            self.backend not in ("transformer", "tac098", "tac104")
            or any(
                type(v) is not int or v < 1
                for v in (self.vocab_size, self.width, self.layers, self.heads, self.context)
            )
            or self.width % self.heads
            or self.context < 8
        ):
            raise LabError("invalid model configuration")
        if self.backend == "tac098" and (self.width, self.layers, self.heads) != (32, 1, 1):
            raise LabError("TAC098 has fixed native dimensions; use width=32,layers=1,heads=1")
        if self.native is not None and self.backend != "tac104":
            raise LabError("native geometry applies only to TAC104")
        if self.backend == "tac098" and self.vocab_size != 256:
            raise LabError("exact TAC098 requires byte-v1 tokenizer (256 symbols)")


class ModelBackend(Protocol):
    config: ModelConfig

    def forward(self, tokens: torch.Tensor) -> torch.Tensor: ...
    def step(self, tokens: torch.Tensor, state=None) -> tuple: ...


class Block(nn.Module):
    def __init__(self, config):
        super().__init__()
        d = config.width
        self.heads, self.head_dim = config.heads, d // config.heads
        self.norm1, self.norm2 = nn.RMSNorm(d), nn.RMSNorm(d)
        self.qkv, self.out = nn.Linear(d, 3 * d, bias=False), nn.Linear(d, d, bias=False)
        self.up, self.gate = nn.Linear(d, 4 * d, bias=False), nn.Linear(d, 4 * d, bias=False)
        self.down = nn.Linear(4 * d, d, bias=False)

    def forward(self, x, cache=None):
        batch, length, width = x.shape
        q, k, v = (
            self.qkv(self.norm1(x)).view(batch, length, 3, self.heads, self.head_dim).unbind(2)
        )
        q, k, v = (t.transpose(1, 2) for t in (q, k, v))
        if cache is not None:
            k, v = torch.cat((cache[0], k), 2), torch.cat((cache[1], v), 2)
        # Cached calls accept one token. Full prefill uses the ordinary causal mask.
        a = F.scaled_dot_product_attention(q, k, v, is_causal=cache is None)
        x = x + self.out(a.transpose(1, 2).reshape(batch, length, width))
        y = self.norm2(x)
        return x + self.down(F.silu(self.gate(y)) * self.up(y)), (k, v)


class Transformer(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.embedding = nn.Embedding(config.vocab_size, config.width)
        self.position = nn.Embedding(config.context, config.width)
        self.blocks = nn.ModuleList(Block(config) for _ in range(config.layers))
        self.norm = nn.RMSNorm(config.width)
        nn.init.normal_(self.embedding.weight, std=0.02)
        nn.init.normal_(self.position.weight, std=0.02)

    def step(self, tokens, state=None):
        start = 0 if state is None else state[0][0].shape[2]
        if start + tokens.shape[1] > self.config.context or (
            state is not None and tokens.shape[1] != 1
        ):
            raise LabError("context limit or multi-token cached decode")
        x = self.embedding(tokens) + self.position(
            torch.arange(start, start + tokens.shape[1], device=tokens.device)
        )
        caches = []
        for i, block in enumerate(self.blocks):
            if self.config.activation_checkpointing and self.training and state is None:
                x = checkpoint(lambda value, b=block: b(value)[0], x, use_reentrant=False)
                caches.append(None)
            else:
                x, cache = block(x, None if state is None else state[i])
                caches.append(cache)
        return F.linear(self.norm(x), self.embedding.weight), caches

    def forward(self, tokens):
        return self.step(tokens)[0]


class TAC098(nn.Module):
    def __init__(self, config):
        super().__init__()
        from ._tac098 import ContextualAssociativeTAC098

        self.native = ContextualAssociativeTAC098()
        self.config = config

    def forward(self, tokens):
        return self.native(tokens)[0]

    def step(self, tokens, state=None):
        return self.native(tokens, state=state)


class TAC104(nn.Module):
    """Deeper token-vocabulary extension of the actual four-layer width blueprint."""

    def __init__(self, config):
        super().__init__()
        from ._tac104 import Config104, DeepCacheTAC104

        geometry = dict(
            key_dim=16,
            value_dim=16,
            write_rank=2,
            ffn_dim=224,
            window=128,
            chunk_size=32,
            rotary=True,
            local_rope=True,
            tied_embedding=True,
        )
        if config.native:
            if set(config.native) - set(geometry):
                raise LabError("unknown native TAC geometry field")
            geometry.update(config.native)
        self.native = DeepCacheTAC104(
            Config104(
                d_model=config.width,
                n_layers=config.layers,
                n_heads=config.heads,
                vocab_size=config.vocab_size,
                activation_checkpointing=config.activation_checkpointing,
                **geometry,
            )
        )
        self.config = config

    def forward(self, tokens):
        return self.native(tokens)[0]

    def step(self, tokens, state=None):
        owners = (
            state.owners
            if state is not None
            else tuple(f"fresh-{i}" for i in range(tokens.shape[0]))
        )
        return self.native(
            tokens,
            state=state,
            owners=owners,
            mode="recurrent" if tokens.shape[1] == 1 else "chunk",
        )


def create_model(config):
    config = config if isinstance(config, ModelConfig) else ModelConfig(**config)
    config.validate()
    constructors = {"transformer": Transformer, "tac098": TAC098, "tac104": TAC104}
    return constructors[config.backend](config)


def configuration(model):
    return asdict(model.config)
