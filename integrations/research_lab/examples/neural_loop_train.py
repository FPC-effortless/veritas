"""Standard GRU operational fit, unrelated to TAC-OSM model qualification.

A generated delayed-copy task tests whether a recurrent trainer runs, checkpoints,
evaluates and replays through Lab OS. It establishes no novel architecture claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from pathlib import Path

import torch
from torch import nn


def main():
    arm, delay, updates = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    seed = int(os.environ["TRAINLAB_SEED"])
    random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    model = nn.ModuleDict(
        {
            "embedding": nn.Embedding(16, 32),
            "gru": nn.GRU(32, 160, batch_first=True),
            "head": nn.Linear(160, 16),
        }
    )
    parameters = sum(p.numel() for p in model.parameters() if p.requires_grad)
    assert parameters == 96208
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.003)
    train_generator = torch.Generator().manual_seed(seed + 101)
    dev_generator = torch.Generator().manual_seed(8901)

    def batch(generator, size):
        labels = torch.randint(1, 16, (size,), generator=generator)
        tokens = torch.zeros(size, delay + 1, dtype=torch.long)
        tokens[:, 0] = labels
        return tokens, labels

    def forward(tokens):
        embedded = model["embedding"](tokens)
        if arm == "control":
            # Same learned parameters, data and optimizer steps; erase carried state.
            hidden = None
            for token in embedded.unbind(1):
                output, hidden = model["gru"](token[:, None, :], None)
        else:
            output, hidden = model["gru"](embedded)
        return model["head"](output[:, -1])

    losses = []
    for step in range(updates):
        tokens, labels = batch(train_generator, 32)
        optimizer.zero_grad(set_to_none=True)
        loss = nn.functional.cross_entropy(forward(tokens), labels)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1)
        optimizer.step()
        losses.append(loss.item())
    model.eval()
    with torch.no_grad():
        tokens, labels = batch(dev_generator, 256)
        logits = forward(tokens)
        predictions = logits.argmax(-1)
        accuracy = (predictions == labels).float().mean().item()
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    # torch.save ZIP timestamps need not be byte-identical; replay uses logical tensor hash.
    state_hash = hashlib.sha256()
    for key, tensor in sorted(model.state_dict().items()):
        state_hash.update(key.encode())
        state_hash.update(tensor.detach().contiguous().numpy().tobytes())
    checkpoint = {
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "torch_rng": torch.get_rng_state(),
        "train_rng": train_generator.get_state(),
        "step": updates,
        "seed": seed,
    }
    torch.save(checkpoint, output / "checkpoint.pt")
    for filename, data in {
        "metrics.json": {
            "accuracy": accuracy,
            "train_loss": losses[-1],
            "fitted_models": 1,
            "parameters": parameters,
        },
        "predictions.json": {
            "seed": seed,
            "arm": arm,
            "delay": delay,
            "predictions": predictions.tolist(),
            "labels": labels.tolist(),
            "state_sha256": state_hash.hexdigest(),
        },
        "training.json": {
            "architecture": "STANDARD_GRU_NOT_TAC_OSM",
            "parameters_before": parameters,
            "parameters_after": sum(p.numel() for p in model.parameters()),
            "updates": updates,
            "batch_size": 32,
            "delay": delay,
            "seed": seed,
            "torch_version": torch.__version__,
            "loss_first": losses[0],
            "loss_last": losses[-1],
            "scope": "SYNTHETIC_OPERATIONAL_ACCEPTANCE_ONLY",
            "resume": "FULL_STATE_SAVED; MID_UPDATE_RESUME_NOT_TESTED",
        },
    }.items():
        (output / filename).write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
    print(
        json.dumps({"arm": arm, "accuracy": accuracy, "updates": updates, "parameters": parameters})
    )


if __name__ == "__main__":
    main()
