"""Multi-token on-policy GRPO for public verified completions, without tool execution."""

from __future__ import annotations

import torch
from forge_data.verifiers import verify_math
from torch.nn import functional as F

from trainlab.runner import LabError


def legal_logp(logits, tokens, temperature=1.0):
    scores = logits.float() / temperature
    forbidden = sorted(set(tokens.special.values()) - {tokens.eos, tokens.end})
    scores = scores.clone()
    scores[..., forbidden] = -torch.inf
    return F.log_softmax(scores, -1)


@torch.no_grad()
def rollout(model, tokens, prompt, generator, *, max_new_tokens, temperature=1.0):
    ids, _ = tokens.conversation([{"role": "user", "content": prompt}], prompt=True)
    if len(ids) + max_new_tokens > model.config.context:
        raise LabError("rollout prompt and completion exceed declared context")
    device = next(model.parameters()).device
    scores, state = model.step(torch.tensor([ids], device=device))
    generated, old_logp, executed_positions = [], [], len(ids)
    for _ in range(max_new_tokens):
        logp = legal_logp(scores[0, -1], tokens, temperature)
        # CPU sampling keeps the saved sampler RNG sufficient for exact replay.
        # This reference path prioritizes correspondence; GPU batching is a later optimization.
        token = int(torch.multinomial(logp.exp().cpu(), 1, generator=generator))
        generated.append(token)
        old_logp.append(float(logp[token]))
        if token in (tokens.end, tokens.eos):
            break
        scores, state = model.step(torch.tensor([[token]], device=device), state)
        executed_positions += 1
    return {
        "prefix": ids,
        "tokens": generated,
        "old_logp": old_logp,
        "completion": tokens.decode(generated),
        "generation_positions": executed_positions,
    }


def completion_grpo(network, policy, reference, rows, tokens, generator, stage):
    """Sample behavior trajectories first; gold answers enter only the verifier."""
    device = next(policy.parameters()).device
    group_size = stage.get("group_size", 4)
    max_new = stage.get("max_new_tokens", 128)
    temperature = stage.get("temperature", 1.0)
    records, objectives, rewards = [], [], []
    used, targets = 0, 0
    for row in rows:
        if row["verifier"] != "gsm8k-exact-v1":
            raise LabError("completion GRPO requires a supported public verifier")
        trajectories = [
            rollout(
                policy,
                tokens,
                row["prompt"],
                generator,
                max_new_tokens=max_new,
                temperature=temperature,
            )
            for _ in range(group_size)
        ]
        values = torch.tensor(
            [verify_math(row, t["completion"]) for t in trajectories], device=device
        )
        advantage = (values - values.mean()) / values.std(unbiased=False).clamp_min(1e-4)
        length = max(len(t["prefix"]) + len(t["tokens"]) for t in trajectories)
        x = torch.full((group_size, length - 1), tokens.pad, dtype=torch.long, device=device)
        y = x.clone()
        mask = torch.zeros_like(x, dtype=torch.bool)
        old = torch.zeros_like(x, dtype=torch.float32)
        for i, trajectory in enumerate(trajectories):
            ids = trajectory["prefix"] + trajectory["tokens"]
            n, start = len(ids) - 1, len(trajectory["prefix"]) - 1
            x[i, :n] = torch.tensor(ids[:-1], device=device)
            y[i, :n] = torch.tensor(ids[1:], device=device)
            mask[i, start:n] = True
            old[i, start:n] = torch.tensor(trajectory["old_logp"], device=device)
        current = legal_logp(network(x), tokens, temperature).gather(-1, y[..., None]).squeeze(-1)
        with torch.no_grad():
            ref = legal_logp(reference(x), tokens, temperature).gather(-1, y[..., None]).squeeze(-1)
        # Padding/control targets have -inf logp. Remove them before any subtraction.
        current = torch.where(mask, current, torch.zeros_like(current))
        ref = torch.where(mask, ref, torch.zeros_like(ref))
        ratio = (current - old).exp()
        epsilon = stage.get("clip_epsilon", 0.2)
        unclipped = ratio * advantage[:, None]
        clipped = ratio.clamp(1 - epsilon, 1 + epsilon) * advantage[:, None]
        difference = ref - current
        kl = difference.exp() - difference - 1
        token_loss = -torch.minimum(unclipped, clipped) + stage.get("kl_beta", 0.02) * kl
        counts = mask.sum(-1).clamp_min(1)
        objectives.append(((token_loss * mask).sum(-1) / counts).mean())
        used += x.numel() + sum(t["generation_positions"] for t in trajectories)
        targets += int(mask.sum())
        rewards.extend(values.tolist())
        records.append(
            {
                "group": row["group"],
                "prompt": row["prompt"],
                "verifier": row["verifier"],
                "sampling": "full legal vocabulary categorical, multi-token autoregressive",
                "temperature": temperature,
                "max_new_tokens": max_new,
                "trajectories": [
                    {**t, "reward": float(value)} for t, value in zip(trajectories, values.tolist())
                ],
            }
        )
    return torch.stack(objectives).mean(), used, targets, len(rewards), records, rewards
