"""Run a stochastic PyTorch CPU resume comparison with omitted-state controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from trainlab.resume_equivalence import compare
from trainlab.runner import LabError, digest, read_json, write_json

STEPS = 11
SAVE_AT = 5
SEED = 714
MODES = ("healthy", "omit-optimizer", "omit-rng", "omit-sampler")
DEV = {
    "features": [[float(i % 3), float((i * 7) % 11) / 11] for i in range(12)],
    "labels": [float((i * 7 + 3) % 13) / 13 for i in range(12)],
}


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def components(model, optimizer, sampler, batches, loss):
    import torch

    parameters = [p for _, p in sorted(model.named_parameters())]
    names = ("exp_avg", "exp_avg_sq")
    states = optimizer.state
    return {
        "weights": [value for p in parameters for value in p.detach().flatten().tolist()],
        "optimizer": [
            value
            for p in parameters
            for name in names
            for value in states.get(p, {}).get(name, torch.zeros_like(p)).flatten().tolist()
        ],
        "optimizer_steps": [int(states.get(p, {}).get("step", 0)) for p in parameters],
        "torch_rng": hashlib.sha256(bytes(torch.get_rng_state().tolist())).hexdigest(),
        "sampler": {
            **sampler,
            "generator": hashlib.sha256(bytes(batches.get_state().tolist())).hexdigest(),
        },
        "loss": [loss] if loss is not None else None,
    }


def worker(root, mode):
    import torch

    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(SEED)
    nn = torch.nn
    model = nn.Sequential(nn.Linear(2, 4), nn.Tanh(), nn.Dropout(0.25), nn.Linear(4, 1))
    optimizer = torch.optim.Adam(model.parameters(), lr=0.02)
    batches = torch.Generator().manual_seed(SEED + 1)
    sampler = {"order": torch.randperm(len(DEV["labels"]), generator=batches).tolist(), "cursor": 0}
    x = torch.tensor(DEV["features"])
    y = torch.tensor(DEV["labels"]).unsqueeze(1)
    checkpoint = root / "checkpoint.pt"
    context = read_json(root / "context.json")
    if (
        context["driver_sha256"] != digest(Path(__file__))
        or context["data_sha256"] != sha(DEV)
        or context["torch"] != str(torch.__version__)
    ):
        raise LabError("training context changed")
    saved_loss = None
    start = 0
    observations = []
    if mode != "reference":
        plan = read_json(root / "plan.json")
        raw = checkpoint.read_bytes()
        if hashlib.sha256(raw).hexdigest() != plan["checkpoint_sha256"]:
            raise LabError("checkpoint differs from frozen plan")
        import io

        checkpoint_state = torch.load(io.BytesIO(raw), map_location="cpu", weights_only=True)
        if checkpoint_state["step"] != SAVE_AT or checkpoint_state["context_sha256"] != digest(
            root / "context.json"
        ):
            raise LabError("checkpoint step/context differs")
        model.load_state_dict(checkpoint_state["weights"])
        if mode != "omit-optimizer":
            optimizer.load_state_dict(checkpoint_state["optimizer"])
        if mode != "omit-rng":
            torch.set_rng_state(checkpoint_state["torch_rng"])
        if mode != "omit-sampler":
            sampler = checkpoint_state["sampler"]
            batches.set_state(checkpoint_state["sampler_rng"])
        start = SAVE_AT
        saved_loss = checkpoint_state["loss"]
        observations.append(
            {
                "step": start,
                "components": components(model, optimizer, sampler, batches, saved_loss),
            }
        )
    for step in range(start + 1, STEPS + 1):
        if sampler["cursor"] == len(DEV["labels"]):
            sampler = {
                "order": torch.randperm(len(DEV["labels"]), generator=batches).tolist(),
                "cursor": 0,
            }
        cursor = sampler["cursor"]
        indices = sampler["order"][cursor : cursor + 3]
        sampler = {**sampler, "cursor": cursor + 3}
        optimizer.zero_grad(set_to_none=True)
        loss = nn.functional.mse_loss(model(x[indices]), y[indices])
        loss.backward()
        optimizer.step()
        value = float(loss.detach().item())
        if step == SAVE_AT and mode == "reference":
            torch.save(
                {
                    "weights": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "torch_rng": torch.get_rng_state(),
                    "sampler_rng": batches.get_state(),
                    "sampler": sampler,
                    "step": step,
                    "loss": value,
                    "context_sha256": digest(root / "context.json"),
                },
                checkpoint,
            )
        if step >= SAVE_AT:
            observations.append(
                {"step": step, "components": components(model, optimizer, sampler, batches, value)}
            )
    write_json(root / f"{mode}-samples.json", observations)


def execute(root):
    import torch

    root.mkdir(parents=True, exist_ok=False)
    ctx = root / "context.json"
    write_json(
        ctx,
        {
            "driver_sha256": digest(Path(__file__)),
            "data_sha256": sha(DEV),
            "torch": str(torch.__version__),
            "python": sys.version,
            "device": "CPU",
            "machine": platform.machine(),
            "threads": 1,
            "seed": SEED,
            "checkpoint_step": SAVE_AT,
            "total_steps": STEPS,
        },
    )
    identities, receipts = {}, {}

    def run(mode):
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--root", str(root), "--worker", mode],
            env=dict(os.environ),
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        (root / f"{mode}.stdout").write_text(completed.stdout)
        (root / f"{mode}.stderr").write_text(completed.stderr)
        receipts[mode] = {"exit_code": completed.returncode}
        write_json(root / "executions.json", receipts)
        if completed.returncode:
            raise LabError(f"resume worker {mode} failed")
        return read_json(root / f"{mode}-samples.json")

    reference = run("reference")
    pin = digest(root / "checkpoint.pt")
    plan = root / "plan.json"
    first = reference[0]["components"]
    numeric = ("weights", "optimizer", "loss")
    rules = {
        k: (
            {"kind": "numeric", "atol": 0, "rtol": 0, "length": len(first[k])}
            if k in numeric
            else {"kind": "exact"}
        )
        for k in first
    }
    write_json(
        plan,
        {
            "schema": "trainlab.resume-plan.v1",
            "context_sha256": digest(ctx),
            "checkpoint_sha256": pin,
            "steps": list(range(SAVE_AT, STEPS + 1)),
            "components": rules,
        },
    )

    def wrap(mode, samples):
        path = root / f"{mode}-trace.json"
        write_json(
            path,
            {
                "schema": "trainlab.resume-trace.v1",
                "plan_sha256": digest(plan),
                "context_sha256": digest(ctx),
                "checkpoint_sha256": pin,
                "role": "reference" if mode == "reference" else "resumed",
                "samples": samples,
            },
        )
        identities[mode] = digest(path)
        return path

    reference_path = wrap("reference", reference)
    reports = {}
    for mode in MODES:
        resumed = run(mode)
        path = wrap(mode, resumed)
        result = compare(
            plan,
            reference_path,
            path,
            plan_sha256=digest(plan),
            reference_sha256=identities["reference"],
            resumed_sha256=identities[mode],
        )
        # Independent zero-tolerance comparison of the saved component values.
        mismatches = {
            sample["step"]: sorted(
                k for k, value in sample["components"].items() if value != other["components"][k]
            )
            for sample, other in zip(reference, resumed, strict=True)
        }
        earliest = next((step for step, keys in mismatches.items() if keys), None)
        if result["first_observed_difference"] != earliest:
            raise LabError("resume evidence recount differs")
        result["independent_first_difference"] = earliest
        reports[mode] = result
    if digest(root / "checkpoint.pt") != pin:
        raise LabError("checkpoint changed")
    write_json(root / "reports.json", reports)
    expected = {
        "healthy": None,
        "omit-optimizer": SAVE_AT,
        "omit-rng": SAVE_AT,
        "omit-sampler": SAVE_AT,
    }
    if {mode: r["first_observed_difference"] for mode, r in reports.items()} != expected:
        raise LabError("resume or missing-state control did not discriminate")
    print(
        json.dumps(
            {
                mode: {
                    "status": r["status"],
                    "first_observed_difference": r["first_observed_difference"],
                    "first_components": r["first_observed_components"],
                }
                for mode, r in reports.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--worker", choices=("reference", *MODES))
    args = parser.parse_args()
    root = args.root.resolve()
    if args.worker:
        worker(root, args.worker)
    else:
        execute(root)
