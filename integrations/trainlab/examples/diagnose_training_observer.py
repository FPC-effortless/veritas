"""Execute clean and injected CPU training checks with a fixed slice panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trainlab.runner import LabError, digest, write_json
from trainlab.training_observer import freeze_slices, slice_trajectory, train_step


def execute(root):
    import torch

    torch.set_num_threads(1)
    torch.manual_seed(12)
    root.mkdir(parents=True, exist_ok=False)
    nn = torch.nn
    batch = {
        "inputs": torch.tensor([[1.0, 0.0], [0.0, 1.0]]),
        "labels": torch.tensor([0, 1]),
        "mask": None,
    }
    model = nn.Linear(2, 2)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.3)
    validation = torch.tensor([[2.0, 0.0], [1.5, 0.0], [0.0, 2.0], [0.0, 1.5]])
    frozen = freeze_slices(
        [{"id": str(i), "slice": str(i // 2), "label": str(i // 2)} for i in range(4)],
        acquired_score=1,
        max_regression=0.25,
    )
    steps = list(range(1, 9))
    checkpoints, reports = [], []
    for step in steps:
        report = train_step(model, optimizer, batch, step=step, task="classification", classes=2)
        reports.append(report)
        with torch.inference_mode():
            answers = model(validation).argmax(-1).tolist()
        checkpoints.append(
            {
                "step": step,
                "predictions": {str(i): str(a) for i, a in enumerate(answers)},
            }
        )
    trajectory = slice_trajectory(checkpoints=checkpoints, expected_steps=steps, **frozen)

    class BadActivation(nn.Module):
        def forward(self, x):
            return x * float("nan")

    class BadBackward(torch.autograd.Function):
        @staticmethod
        def forward(_ctx, x):
            return x.clone()

        @staticmethod
        def backward(_ctx, gradient):
            return gradient * float("nan")

    class BadGradient(nn.Module):
        def forward(self, x):
            return BadBackward.apply(x)

    faults = {}
    for name, block in (("activation", BadActivation()), ("gradient", BadGradient())):
        failed = nn.Sequential(nn.Linear(2, 2), block)
        opt = torch.optim.SGD(failed.parameters(), lr=0.3)
        faults[name] = train_step(failed, opt, batch, step=1, task="classification", classes=2)
    frozen_optimizer = torch.optim.SGD(model.parameters(), lr=0.0)
    faults["frozen"] = train_step(
        model, frozen_optimizer, batch, step=9, task="classification", classes=2
    )

    language = nn.Embedding(6, 6)
    language_optimizer = torch.optim.Adam(language.parameters(), lr=0.01)
    language_batch = {
        "inputs": torch.tensor([[1, 2, 3]]),
        "labels": torch.tensor([[2, 3, -100]]),
        "mask": torch.tensor([[True, True, False]]),
    }
    language_result = train_step(
        language, language_optimizer, language_batch, step=1, task="next_token", classes=6
    )
    language_batch["labels"][0, 0] = 1
    try:
        train_step(
            language, language_optimizer, language_batch, step=2, task="next_token", classes=6
        )
    except LabError:
        shift_rejected = True
    else:
        shift_rejected = False
    evidence = {
        "runtime": {"torch": str(torch.__version__), "device": "cpu", "threads": 1},
        "driver_sha256": digest(Path(__file__)),
        "training": reports,
        "faults": faults,
        "validation_panel": frozen,
        "checkpoints": checkpoints,
        "trajectory": trajectory,
        "language_step": language_result,
        "invalid_shift_rejected": shift_rejected,
    }
    write_json(root / "report.json", evidence)
    kinds = {k: r["first_anomaly"]["kind"] for k, r in faults.items() if r["first_anomaly"]}
    wanted = {
        "activation": "NONFINITE_OR_UNSUPPORTED_ACTIVATION",
        "gradient": "NONFINITE_OR_UNSUPPORTED_GRADIENT",
        "frozen": "UNCHANGED_PARAMETERS",
    }
    if (
        any(r["status"] != "TESTED" for r in reports)
        or kinds != wanted
        or any(r["first_acquired"] is None for r in trajectory["slices"].values())
        or language_result["status"] != "TESTED"
        or not shift_rejected
    ):
        raise LabError("training observer controls did not distinguish all conditions")
    print(
        json.dumps(
            {
                "path": str(root),
                "clean_steps": len(reports),
                "faults": kinds,
                "validation_slices": len(trajectory["slices"]),
                "bad_shift_rejected": shift_rejected,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    execute(args.root.resolve())
