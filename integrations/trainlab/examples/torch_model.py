"""Tiny real PyTorch recipe command; CONSTRUCTED operational acceptance only."""

from __future__ import annotations

import argparse
import hashlib
import os
from datetime import timedelta
from pathlib import Path

import torch
import trainlab.pytorch as backend
from forge_data.dataset import Dataset
from torch import distributed as dist
from torch import nn
from torch.nn.parallel import DistributedDataParallel
from trainlab.runner import LabError, digest, write_json


class Model(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = nn.Linear(1, 4)
        self.activation = nn.Tanh()
        self.head = nn.Linear(4, 1)

    def forward(self, features):
        return self.head(self.activation(self.encoder(features)))


def batch(dataset, split, device):
    rows = dataset.examples(
        split,
        cutoff="2026-01-01T10:00:01Z",
        target_cutoff="2026-01-02T10:00:00Z",
        feature_fields=["temperature"],
    )
    return (
        torch.tensor([[row["features"]["temperature"] / 30] for row in rows], device=device),
        torch.tensor([[row["target"]["value"] / 61] for row in rows], device=device),
    )


def state_digest(model):
    # Logical tensor identity, independent of checkpoint ZIP metadata.
    value = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        value.update(name.encode())
        value.update(bytes(tensor.detach().cpu().contiguous().view(torch.uint8).flatten().tolist()))
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task",
        required=True,
        choices=("train", "debug", "profile", "test", "export", "deployment_check"),
    )
    parser.add_argument("--pin", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--updates", type=int, default=80)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--inject-nonfinite", action="store_true")
    parser.add_argument("--fail-rank", type=int)
    args = parser.parse_args()
    if not 1 <= args.updates <= 1000 or args.resume and args.checkpoint is None:
        parser.error("updates must be 1–1000; resume requires a checkpoint")
    # This example is tiny, deterministic and offline; no provider/model download.
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    seed = int(os.environ["TRAINLAB_SEED"])
    torch.manual_seed(seed)
    world = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    if args.fail_rank is not None and not 0 <= args.fail_rank < world:
        parser.error("fail-rank must name an actual rank")
    if world > 1 and int(os.environ.get("LOCAL_WORLD_SIZE", str(world))) != world:
        raise LabError("the example supports distributed training on one host only")
    device_name = args.device
    if world > 1 and device_name == "cuda":
        device_name = "cuda:" + os.environ["LOCAL_RANK"]
    device = backend.resolve_device(device_name)
    if device.type == "cuda":
        torch.cuda.set_device(device)
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    dataset = Dataset(Path("dataset"), manifest_sha256=args.pin)
    validation_x, validation_y = batch(dataset, "validation", device)
    model = Model().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.03)
    step = 0
    if args.checkpoint is not None:
        # Only trusted, declared local checkpoints. Never load arbitrary pickle code.
        saved = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
        if saved["manifest_sha256"] != args.pin:
            raise LabError("checkpoint dataset identity does not match the frozen manifest")
        model.load_state_dict(saved["model"])
        if args.resume:
            if world != 1 or saved["world_size"] != 1 or saved["device_type"] != device.type:
                raise LabError("this example resumes only on the same single-process device type")
            optimizer.load_state_dict(saved["optimizer"])
            torch.set_rng_state(saved["torch_rng"])
            if device.type == "cuda":
                torch.cuda.set_rng_state(saved["cuda_rng"], device)
            step = saved["step"]
    if args.task != "train" and args.checkpoint is None:
        raise LabError("non-training tasks require the declared checkpoint")
    if world > 1 and args.task != "train":
        raise LabError("only the training example supports a distributed launcher")
    connected = False
    try:
        if world > 1:
            if device.type == "cpu":
                os.environ.setdefault("GLOO_SOCKET_IFNAME", "lo")
            dist.init_process_group(
                "nccl" if device.type == "cuda" else "gloo", timeout=timedelta(seconds=30)
            )
            connected = True
            rank, world = dist.get_rank(), dist.get_world_size()
        if args.fail_rank == rank:
            raise LabError("injected constructed rank failure")
        report = {
            "source": "CONSTRUCTED_ONLY",
            "qualification": "NOT_QUALIFIED",
            "task": args.task,
            "torch_version": str(torch.__version__),
            "adapter_sha256": digest(Path(backend.__file__)),
            "device": str(device),
            "world_size": world,
            "rank": rank,
            "backend": dist.get_backend() if connected else None,
            "manifest_sha256": args.pin,
        }
        metrics = {}
        if args.task == "train":
            train_x, train_y = batch(dataset, "train", device)
            if len(train_x) % world:
                raise LabError("example requires equal nonempty training partitions per rank")
            train_x, train_y = train_x[rank::world], train_y[rank::world]
            if not len(train_x):
                raise LabError("empty rank training partition")
            batch_size = min(8, len(train_x))
            fitted = (
                DistributedDataParallel(
                    model, device_ids=[device.index] if device.type == "cuda" else None
                )
                if connected
                else model
            )
            for _ in range(args.updates):
                optimizer.zero_grad(set_to_none=True)
                indices = torch.randperm(len(train_x), device=device)[:batch_size]
                loss = nn.functional.mse_loss(fitted(train_x[indices]), train_y[indices])
                backend.check_tensor("train loss", loss)
                loss.backward()
                optimizer.step()
            backend.check_model(model, gradients=True)
            step += args.updates
            report.update(
                step=step,
                training_examples=len(train_x),
                batch_size=batch_size,
                exposures=batch_size * args.updates,
                state_sha256=state_digest(model),
            )
            if connected:
                state = torch.tensor(
                    list(bytes.fromhex(report["state_sha256"])), dtype=torch.uint8, device=device
                )
                states = [torch.empty_like(state) for _ in range(world)]
                dist.all_gather(states, state)
                if any(not torch.equal(states[0], item) for item in states[1:]):
                    raise LabError("distributed model replicas disagree")
            write_json(output / f"rank-{rank}.json", report)
            if rank == 0:
                torch.save(
                    {
                        "model": model.state_dict(),
                        "optimizer": optimizer.state_dict(),
                        "torch_rng": torch.get_rng_state(),
                        "cuda_rng": torch.cuda.get_rng_state(device)
                        if device.type == "cuda"
                        else None,
                        "step": step,
                        "seed": seed,
                        "manifest_sha256": args.pin,
                        "world_size": world,
                        "device_type": device.type,
                    },
                    output / "checkpoint.pt",
                )
        elif args.task == "debug":
            if args.inject_nonfinite:
                with torch.no_grad():
                    model.encoder.weight[0, 0] = float("nan")
            with backend.check_activations(model) as checked:
                loss = nn.functional.mse_loss(model(validation_x), validation_y)
                loss.backward()
            report["activations"] = checked
            report["model"] = backend.check_model(model, gradients=True)
        elif args.task == "profile":
            model.eval()
            with torch.no_grad():
                for _ in range(3):
                    model(validation_x)
                with backend.profile_modules(model, device=str(device)) as profile:
                    for _ in range(10):
                        model(validation_x)
                report["module_profile"] = profile.report()
                with torch.profiler.profile(
                    activities=[torch.profiler.ProfilerActivity.CPU]
                    + ([torch.profiler.ProfilerActivity.CUDA] if device.type == "cuda" else []),
                    profile_memory=True,
                ) as trace:
                    model(validation_x)
                trace.export_chrome_trace(str(output / "operators.json"))
        elif args.task in ("export", "deployment_check"):
            if device.type != "cpu":
                raise LabError("the portable export acceptance target is explicitly CPU")
            model.eval()
            if args.task == "export":
                exported = torch.export.export(
                    model,
                    (validation_x,),
                    dynamic_shapes=({0: torch.export.Dim("batch", min=1, max=256)},),
                )
                torch.export.save(exported, output / "model.pt2")
            else:
                exported = torch.export.load("model.pt2")
            with torch.no_grad():
                # Use a different batch size to exercise exported shape constraints.
                probe = torch.linspace(0, 1, 5).reshape(-1, 1)
                expected, observed = model(probe), exported.module()(probe)
                backend.check_tensor("export predictions", observed)
                metrics["export_max_error"] = (expected - observed).abs().max().item()
                if args.task == "export":
                    write_json(
                        output / "reference.json",
                        {
                            "source": "CONSTRUCTED_ONLY",
                            "inputs": probe.tolist(),
                            "predictions": expected.tolist(),
                            "qualification": "NOT_QUALIFIED",
                        },
                    )
            report["scope"] = "LOCAL_CPU_TORCH_EXPORT_INFERENCE"
        model.eval()
        with torch.no_grad():
            predictions = model(validation_x)
            backend.check_tensor("validation predictions", predictions)
            metrics["validation_mse"] = nn.functional.mse_loss(predictions, validation_y).item()
        if rank == 0:
            write_json(output / "metrics.json", metrics)
            write_json(output / "runtime.json", report)
    finally:
        if connected:
            dist.destroy_process_group()


if __name__ == "__main__":
    main()
