"""Parallel mathematical kernels for the untrained LANGCACHE104 candidate.

These device-generic PyTorch formulations expose batched GEMMs and work-efficient
affine scans. They are not fused CUDA kernels and have no verified GPU speed
claim. Floating-point association differs between recurrent and parallel modes.
All inputs and incoming state must use the same floating dtype/device; the model
is responsible for FP32 state accumulation and valid gates/features.
"""

from __future__ import annotations

import torch
from torch import Tensor

READ_EPSILON = 1e-4


def _interleave(even: Tensor, odd: Tensor, length: int) -> Tensor:
    """Interleave time-indexed tensors without an in-place autograd write."""
    pairs = length // 2
    joined = torch.stack((even[:, :pairs], odd), dim=2).flatten(1, 2)
    return torch.cat((joined, even[:, -1:]), dim=1) if length % 2 else joined


def _scalar_affine_prefix(a: Tensor, b: Tensor) -> tuple[Tensor, Tensor]:
    """Inclusive prefixes of s'=a*s+b; a[B,N,H], b[B,N,H,...].

    Adjacent pair reduction followed by even-prefix reconstruction performs
    O(N) state-width work and O(log N) temporal stages. There is no division by
    cumulative products, including when an input coefficient is zero.
    """
    length = a.shape[1]
    if length <= 1:
        return a, b
    extra = (None,) * (b.ndim - a.ndim)

    def scale(coefficient: Tensor, value: Tensor) -> Tensor:
        return coefficient[(...,) + extra] * value

    pairs = length // 2
    a0, a1 = a[:, : 2 * pairs : 2], a[:, 1 : 2 * pairs : 2]
    b0, b1 = b[:, : 2 * pairs : 2], b[:, 1 : 2 * pairs : 2]
    odd_a, odd_b = _scalar_affine_prefix(a1 * a0, scale(a1, b0) + b1)
    remaining = a[:, 2::2]
    previous_a = odd_a[:, : remaining.shape[1]]
    previous_b = odd_b[:, : remaining.shape[1]]
    even_a = torch.cat((a[:, :1], remaining * previous_a), dim=1)
    even_b = torch.cat((b[:, :1], scale(remaining, previous_b) + b[:, 2::2]), dim=1)
    return _interleave(even_a, odd_a, length), _interleave(even_b, odd_b, length)


def associative_read(
    q: Tensor,
    k: Tensor,
    v: Tensor,
    a: Tensor,
    w: Tensor,
    memory: Tensor,
    mass: Tensor,
    *,
    chunk_size: int,
    mode: str,
) -> tuple[Tensor, Tensor, Tensor, Tensor]:
    """Inclusive normalized rank-r associative reads and final carried state.

    q[B,T,H,K], k[B,T,H,R,K], v[B,T,H,R,V], a/w[B,T,H],
    memory[B,H,V,K], mass[B,H,K]. The recurrence is

      M_t = a_t M_(t-1) + (w_t/R) sum_r v_(t,r) k_(t,r)^T
      z_t = a_t z_(t-1) + (w_t/R) sum_r k_(t,r)
      evidence_t = z_t dot q_t; read_t = M_t q_t/(evidence_t+1e-4).

    The model supplies nonnegative keys/queries, |v|<=1 and 0<=w<=1-a.
    Those conditions preserve the normalized-bank cone from valid initial
    state. Gate values are not inspected here to avoid a GPU synchronization.

    ``chunk`` batches ALL chunks, uses causal within-chunk decay/GEMMs, and
    scans their affine boundary summaries in parallel. It stores O(T*C)
    within-chunk attention weights and O(ceil(T/C)*V*K) boundary state per
    batch/head (fixed write rank), rather than T copies of V*K state.
    C=1 intentionally degenerates to one state-width summary per token.
    ``recurrent`` is a direct independent time-loop formulation.
    """
    if mode not in {"chunk", "recurrent"}:
        raise ValueError("associative mode must be 'chunk' or 'recurrent'")
    if not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError("chunk_size must be a positive integer")
    if q.ndim != 4 or k.ndim != 5 or v.ndim != 5:
        raise ValueError("expected q[B,T,H,K], k[B,T,H,R,K], v[B,T,H,R,V]")
    batch, length, heads, key_dim = q.shape
    rank, value_dim = k.shape[-2], v.shape[-1]
    if rank < 1 or k.shape != (batch, length, heads, rank, key_dim):
        raise ValueError("key geometry does not match query geometry")
    if v.shape != (batch, length, heads, rank, value_dim):
        raise ValueError("value geometry does not match keys")
    if a.shape != (batch, length, heads) or w.shape != a.shape:
        raise ValueError("gate geometry does not match query geometry")
    if memory.shape != (batch, heads, value_dim, key_dim):
        raise ValueError("incoming memory geometry does not match features")
    if mass.shape != (batch, heads, key_dim):
        raise ValueError("incoming mass geometry does not match features")
    if length == 0:
        return q.new_empty((batch, 0, heads, value_dim)), memory, mass, a

    if mode == "recurrent":
        reads, evidences = [], []
        current_memory, current_mass = memory, mass
        for index in range(length):
            weight = w[:, index] / rank
            write = v[:, index].transpose(-1, -2) @ k[:, index]
            current_memory = (
                a[:, index, :, None, None] * current_memory + weight[..., None, None] * write
            )
            current_mass = a[:, index, :, None] * current_mass + weight[..., None] * k[
                :, index
            ].sum(dim=-2)
            query = q[:, index]
            evidence = (current_mass * query).sum(dim=-1)
            numerator = (current_memory @ query.unsqueeze(-1)).squeeze(-1)
            reads.append(numerator / (evidence[..., None] + READ_EPSILON))
            evidences.append(evidence)
        return (
            torch.stack(reads, dim=1),
            current_memory,
            current_mass,
            torch.stack(evidences, dim=1),
        )

    # Identity padding admits no extra write and leaves final state unchanged.
    width = min(chunk_size, length)
    chunks = (length + width - 1) // width
    padding = chunks * width - length

    def padded(value: Tensor, fill: float = 0.0) -> Tensor:
        if not padding:
            return value
        tail = value.new_full((batch, padding, *value.shape[2:]), fill)
        return torch.cat((value, tail), dim=1)

    query = padded(q).reshape(batch, chunks, width, heads, key_dim)
    query = query.permute(0, 1, 3, 2, 4)
    keys = padded(k).reshape(batch, chunks, width, heads, rank, key_dim)
    keys = keys.permute(0, 1, 3, 2, 4, 5).flatten(-3, -2)
    values = padded(v).reshape(batch, chunks, width, heads, rank, value_dim)
    values = values.permute(0, 1, 3, 2, 4, 5).flatten(-3, -2)
    retention = padded(a, 1.0).reshape(batch, chunks, width, heads)
    retention = retention.permute(0, 1, 3, 2)
    write_weight = padded(w).reshape(batch, chunks, width, heads)
    write_weight = write_weight.permute(0, 1, 3, 2) / rank

    # D[i,j]=prod_(l=j+1)^i a[l] for j<=i. Masked factors and cumprod
    # avoid ratios of tiny/zero prefix products. This is O(C^2), not C^3.
    positions = torch.arange(width, device=q.device)
    row, column = positions[:, None], positions[None, :]
    factors = torch.where(row > column, retention.unsqueeze(-1), retention.new_ones(()))
    decay = factors.cumprod(dim=-2) * (row >= column).to(q.dtype)
    prefix_retention = retention.cumprod(dim=-1)
    final_weights = (decay[..., -1, :] * write_weight).repeat_interleave(rank, -1)
    weighted_keys = keys * final_weights.unsqueeze(-1)
    memory_offer = values.transpose(-1, -2) @ weighted_keys
    mass_offer = weighted_keys.sum(dim=-2)

    # Join mass with the memory rows so one scalar affine scan supplies
    # both incoming states. The scan is over chunks, not over full token states.
    offer = torch.cat((memory_offer, mass_offer.unsqueeze(-2)), dim=-2)
    initial = torch.cat((memory, mass.unsqueeze(-2)), dim=-2)
    prefix_a, prefix_b = _scalar_affine_prefix(prefix_retention[..., -1], offer)
    boundary = prefix_a[..., None, None] * initial.unsqueeze(1) + prefix_b
    incoming = torch.cat((initial.unsqueeze(1), boundary[:, :-1]), dim=1)
    incoming_memory = incoming[..., :value_dim, :]
    incoming_mass = incoming[..., value_dim, :]

    scores = query @ keys.transpose(-1, -2)
    within_weights = (decay * write_weight.unsqueeze(-2)).repeat_interleave(rank, -1)
    scores = scores * within_weights
    numerator = (query @ incoming_memory.transpose(-1, -2)) * prefix_retention.unsqueeze(
        -1
    ) + scores @ values
    evidence = (query * incoming_mass.unsqueeze(-2)).sum(dim=-1) * prefix_retention + scores.sum(
        dim=-1
    )
    reads = numerator / (evidence.unsqueeze(-1) + READ_EPSILON)
    reads = reads.permute(0, 1, 3, 2, 4).reshape(batch, chunks * width, heads, value_dim)
    evidence = evidence.permute(0, 1, 3, 2).reshape(batch, chunks * width, heads)
    # A final-state view would pin every chunk's boundary allocation after
    # no-grad inference. Own compact backing storage for the carried cache.
    # During training autograd still retains its required computation graph.
    return (
        reads[:, :length],
        boundary[:, -1, :, :value_dim, :].clone(),
        boundary[:, -1, :, value_dim, :].clone(),
        evidence[:, :length],
    )


def _complex_action(real: Tensor, imag: Tensor, value: Tensor) -> Tensor:
    x, y = value.unbind(dim=-1)
    return torch.stack((real * x - imag * y, imag * x + real * y), dim=-1)


def _rotary_affine_prefix(
    real: Tensor, imag: Tensor, offer: Tensor
) -> tuple[Tensor, Tensor, Tensor]:
    """O(T)-work pair reduction for fixed-plane scaled-rotation affine maps."""
    length = real.shape[1]
    if length <= 1:
        return real, imag, offer
    pairs = length // 2
    r0, r1 = real[:, : 2 * pairs : 2], real[:, 1 : 2 * pairs : 2]
    i0, i1 = imag[:, : 2 * pairs : 2], imag[:, 1 : 2 * pairs : 2]
    b0, b1 = offer[:, : 2 * pairs : 2], offer[:, 1 : 2 * pairs : 2]
    odd_r, odd_i, odd_b = _rotary_affine_prefix(
        r1 * r0 - i1 * i0,
        r1 * i0 + i1 * r0,
        _complex_action(r1, i1, b0) + b1,
    )
    r, i = real[:, 2::2], imag[:, 2::2]
    count = r.shape[1]
    previous_r, previous_i = odd_r[:, :count], odd_i[:, :count]
    even_r = torch.cat((real[:, :1], r * previous_r - i * previous_i), dim=1)
    even_i = torch.cat((imag[:, :1], r * previous_i + i * previous_r), dim=1)
    even_b = torch.cat(
        (offer[:, :1], _complex_action(r, i, odd_b[:, :count]) + offer[:, 2::2]),
        dim=1,
    )
    return (
        _interleave(even_r, odd_r, length),
        _interleave(even_i, odd_i, length),
        _interleave(even_b, odd_b, length),
    )


def rotary_scan(
    a: Tensor, theta: Tensor, offer: Tensor, initial: Tensor, *, mode: str = "parallel"
) -> Tensor:
    """Trajectory f_t=a_t R(theta_t)f_(t-1)+(1-a_t)offer_t.

    a[B,T,H,1], theta[B,T,H,V/2], offer[B,T,H,V], initial[B,H,V].
    Consecutive value coordinates form each two-dimensional rotation plane;
    R(theta)[x,y]=[cos(theta)x-sin(theta)y,sin(theta)x+cos(theta)y].
    Rotations act in fixed planes, so their scaled affine maps remain closed
    under composition. No dense transition matrices or inverse products occur.
    This branch has a norm-envelope bound, not the positive-bank cone theorem.
    """
    if mode not in {"parallel", "recurrent"}:
        raise ValueError("rotary mode must be 'parallel' or 'recurrent'")
    if offer.ndim != 4:
        raise ValueError("offer must have geometry [B,T,H,V]")
    batch, length, heads, value_dim = offer.shape
    if value_dim % 2:
        raise ValueError("rotary value dimension must be even")
    if a.shape != (batch, length, heads, 1):
        raise ValueError("rotary retention must have geometry [B,T,H,1]")
    if theta.shape != (batch, length, heads, value_dim // 2):
        raise ValueError("rotary angles must have geometry [B,T,H,V/2]")
    if initial.shape != (batch, heads, value_dim):
        raise ValueError("rotary initial state must have geometry [B,H,V]")
    if length == 0:
        return offer
    real, imag = a * theta.cos(), a * theta.sin()
    additive = ((1 - a) * offer).reshape(batch, length, heads, value_dim // 2, 2)
    start = initial.reshape(batch, heads, value_dim // 2, 2)
    if mode == "recurrent":
        state, states = start, []
        for index in range(length):
            state = _complex_action(real[:, index], imag[:, index], state) + additive[:, index]
            states.append(state)
        return torch.stack(states, dim=1).reshape(batch, length, heads, value_dim)
    prefix_r, prefix_i, prefix_b = _rotary_affine_prefix(real, imag, additive)
    trajectory = _complex_action(prefix_r, prefix_i, start.unsqueeze(1)) + prefix_b
    return trajectory.reshape(batch, length, heads, value_dim)
