"""Bounded Kaggle T4 launcher; preserves the full-cycle token budget across ranks."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RELEASE_SHA256 = "7685a510195b2e2466878c9b634abe7f888e02096c271d41f14272001e5b4b9b"
TOKENIZER_SHA256 = "87567e3e62a688ab666c2e8d25e76917df7709986a7a53cc5be36697d3552609"
PLAN_SHA256 = "31f4e8d46e711812e925ac6dd77742b0a9f57a649b5e356bb4bf13f2115ac327"
ACQUISITION_SHA256 = "72938960b41800710df0275e5a06f931e13c6013df628e0d264585486945921f"
EXAMPLES = Path(__file__).resolve().parent


def world_config(config, gpus):
    """Same global pretraining batch/updates; same total RL trajectories."""
    if gpus not in (1, 2):
        raise ValueError("choose one or two T4 GPUs")
    config = copy.deepcopy(config)
    config["cpu_threads"] = max(1, min(4, (os.cpu_count() or 1) // gpus))
    for stage in config["stages"]:
        accumulation = stage.get("gradient_accumulation", 1)
        if accumulation % gpus == 0:
            stage["gradient_accumulation"] = accumulation // gpus
        elif stage["name"] == "rl" and stage["steps"] % gpus == 0:
            stage["steps"] //= gpus
            stage["warmup_steps"] = min(stage.get("warmup_steps", 0) // gpus, stage["steps"] - 1)
        else:
            raise ValueError("GPU count cannot preserve this stage's declared work budget")
    return config


def hardware(gpus):
    import torch

    if not torch.cuda.is_available() or torch.cuda.device_count() != 2:
        raise ValueError("Kaggle NvidiaTeslaT4 requires exactly two real visible T4 devices")
    devices = [torch.cuda.get_device_name(i) for i in range(2)]
    if any("T4" not in name for name in devices):
        raise ValueError("requested Kaggle T4 hardware is unavailable; no accelerator fallback")
    return {"visible_devices": devices, "training_ranks": gpus, "torch": str(torch.__version__)}


def full_recipe(output, gpus):
    """Resolve the reviewed recipe without downloading or fitting anything."""
    expected = world_config(json.loads((EXAMPLES / "tac-10m-full.json").read_bytes()), gpus)
    data = Path(output).resolve() / "data"
    expected["dataset"] = {
        "directory": str(data / "release"),
        "manifest_sha256": RELEASE_SHA256,
        "source_plan_sha256": PLAN_SHA256,
        "acquisition_sha256": ACQUISITION_SHA256,
    }
    expected["tokenizer"] = {
        "kind": "artifact",
        "artifact_path": str(data / "tokenizer.json"),
        "artifact_sha256": TOKENIZER_SHA256,
    }
    return expected


def verify_full_recipe(config, output, gpus):
    """An internally valid checkpoint must also belong to this exact full run."""
    if config != full_recipe(output, gpus):
        raise ValueError("configuration is not the pinned Kaggle full-training recipe")


def publish_data(config, destination):
    """Copy only verified prepared inputs to persistent outputs, excluding raw shards."""
    from forge_data.language import LanguageRelease
    from trainlab.runner import contained_file, digest

    source = Path(config["dataset"]["directory"])
    tokenizer = Path(config["tokenizer"]["artifact_path"])
    if (
        config["dataset"]["manifest_sha256"] != RELEASE_SHA256
        or digest(tokenizer) != TOKENIZER_SHA256
    ):
        raise ValueError("prepared inputs differ from the reviewed FULLCYCLE-003 release")
    release = LanguageRelease(source, RELEASE_SHA256)
    destination = Path(destination)
    if destination.exists():
        LanguageRelease(destination / "release", RELEASE_SHA256)
        if digest(destination / "tokenizer.json") != TOKENIZER_SHA256:
            raise ValueError("existing persistent tokenizer changed")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".prepared-", dir=destination.parent))
        try:
            (temporary / "release").mkdir()
            for name in ["manifest.json", *release.manifest["files"]]:
                shutil.copyfile(contained_file(source, name), temporary / "release" / name)
            shutil.copyfile(tokenizer, temporary / "tokenizer.json")
            LanguageRelease(temporary / "release", RELEASE_SHA256)
            temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    result = copy.deepcopy(config)
    result["dataset"]["directory"] = str((destination / "release").resolve())
    result["tokenizer"]["artifact_path"] = str((destination / "tokenizer.json").resolve())
    return result


def restore_input(source, output):
    """Explicitly attach/copy a previous session; never merge over working outputs."""
    for name in ("data", "run"):
        root, target = Path(source) / name, Path(output) / name
        if target.exists() or not root.is_dir() or any(p.is_symlink() for p in root.rglob("*")):
            raise ValueError("resume requires intact previous data/run folders and empty targets")
    for name in ("data", "run"):
        shutil.copytree(Path(source) / name, Path(output) / name)


def process_info(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {
            "parent": int(fields[1]),
            "group": int(fields[2]),
            "start": fields[19],
            "state": fields[0],
        }
    except (OSError, IndexError, ValueError):
        return None


def compatible_proc_namespace():
    try:
        return int(Path("/proc/self/stat").read_text().split(" ", 1)[0]) == os.getpid()
    except (OSError, ValueError):
        return False


def refresh_tree(root, tracked):
    # Retain descendants even if an intermediate wrapper/agent exits. Start times
    # prevent a recycled PID from being treated as part of this launch.
    todo, visited = [root, *tracked], set()
    while todo:
        pid = todo.pop()
        if pid in visited:
            continue
        visited.add(pid)
        info = process_info(pid)
        if not info or (pid in tracked and info["start"] != tracked[pid]["start"]):
            continue
        tracked[pid] = info
        try:
            children = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
            todo.extend(int(child) for child in children)
        except OSError:
            pass
    return {
        pid: info
        for pid, old in tracked.items()
        if (info := process_info(pid)) and info["start"] == old["start"] and info["state"] != "Z"
    }


def launch(command, seconds, *, grace=120):
    """Supervise detached rank sessions without killing their agent before saving."""
    if not compatible_proc_namespace():
        raise ValueError("process supervision requires /proc matching the current PID namespace")
    child = subprocess.Popen(command, start_new_session=True)
    tracked, timed_out, operator_interrupted = {}, False, False
    until = time.monotonic() + seconds
    try:
        while child.poll() is None:
            refresh_tree(child.pid, tracked)
            if time.monotonic() >= until:
                timed_out = True
                break
            time.sleep(min(0.1, max(0, until - time.monotonic())))
    except KeyboardInterrupt:
        operator_interrupted = True
    live = refresh_tree(child.pid, tracked)
    cleanup = bool(live)
    forced_groups = 0
    if cleanup:
        # Signal leaves (training ranks) individually. The intermediate worker
        # stays alive so subprocess.run cannot kill torchrun before it checkpoints.
        parents = {info["parent"] for info in live.values()}
        for pid, info in live.items():
            if pid not in parents:
                current = process_info(pid)
                if current and current["start"] == info["start"]:
                    try:
                        os.kill(pid, signal.SIGINT if pid == child.pid else signal.SIGTERM)
                    except ProcessLookupError:
                        pass
        stop_at = time.monotonic() + grace
        try:
            while time.monotonic() < stop_at:
                child.poll()
                live = refresh_tree(child.pid, tracked)
                if not live:
                    break
                time.sleep(0.1)
        except KeyboardInterrupt:
            operator_interrupted = True
        # torchrun ranks use their own sessions. Kill every still-owned group,
        # including detached descendants, after the checkpoint grace period.
        live = refresh_tree(child.pid, tracked)
        groups = {info["group"] for info in live.values()} - {os.getpgrp()}
        forced_groups = len(groups)
        for group in groups:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        # SIGKILL delivery is asynchronous; do not return with a surviving rank.
        stop_at = time.monotonic() + 5
        while refresh_tree(child.pid, tracked) and time.monotonic() < stop_at:
            child.poll()
            time.sleep(0.05)
        if refresh_tree(child.pid, tracked):
            raise RuntimeError("owned training processes survived forced shutdown")
    code = child.wait(timeout=5)
    return {
        "returncode": code,
        "budget_expired": timed_out,
        "operator_interrupted": operator_interrupted,
        "descendant_cleanup": cleanup,
        "forced_kill_groups": forced_groups,
    }


def torch_command(gpus):
    command = [sys.executable]
    if gpus > 1:
        command += ["-m", "torch.distributed.run", "--standalone", "--nproc_per_node", str(gpus)]
    return command


def probe(output, gpus):
    """One synthetic optimizer update, discarded before the independently initialized full run."""
    from datetime import timedelta

    import torch
    import torch.distributed as dist
    from torch.nn.parallel import DistributedDataParallel
    from trainlab.fullcycle.backends import create_model
    from trainlab.runner import read_json, write_json

    rank = int(os.environ.get("LOCAL_RANK", "0"))
    hardware(gpus)
    torch.cuda.set_device(rank)
    torch.use_deterministic_algorithms(True)
    if gpus > 1:
        dist.init_process_group("nccl", timeout=timedelta(seconds=180))
    try:
        torch.manual_seed(10601)
        config = read_json(EXAMPLES / "tac-10m-full.json")["model"]
        model = create_model(config).to(f"cuda:{rank}")
        network = DistributedDataParallel(model, device_ids=[rank]) if gpus > 1 else model
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-5)
        x = torch.randint(0, 3072, (1, 65), device=f"cuda:{rank}")
        loss = torch.nn.functional.cross_entropy(
            network(x[:, :-1]).flatten(0, 1), x[:, 1:].flatten()
        )
        loss.backward()
        finite = all(
            p.grad is not None and bool(torch.isfinite(p.grad).all()) for p in model.parameters()
        )
        flag = torch.tensor(int(finite), device=f"cuda:{rank}")
        if gpus > 1:
            dist.all_reduce(flag, op=dist.ReduceOp.MIN)
        if not flag.item():
            raise ValueError("GPU diagnostic produced nonfinite or missing gradients")
        optimizer.step()
        h = hashlib.sha256()
        for p in model.parameters():
            h.update(p.detach().cpu().numpy().tobytes())
        hashes = [h.hexdigest()]
        if gpus > 1:
            hashes = [None] * gpus
            dist.all_gather_object(hashes, h.hexdigest())
        if len(set(hashes)) != 1:
            raise ValueError("distributed diagnostic weights differ between ranks")
        if rank == 0:
            write_json(
                output / "gpu-probe.json",
                {
                    "passed": True,
                    "hardware": hardware(gpus),
                    "parameters": sum(p.numel() for p in model.parameters()),
                    "optimizer_updates_per_rank": 1,
                    "rank_weight_hashes": hashes,
                    "scope": "synthetic GPU gradient/communication diagnostic; weights discarded",
                    "qualification": "NOT_QUALIFIED",
                },
            )
    finally:
        if gpus > 1:
            dist.destroy_process_group()


def worker(args):
    from trainlab.fullcycle.pipeline import prepare_configuration
    from trainlab.runner import read_json, write_json

    hardware(args.gpus)  # Before acquisition or optimizer work.
    if args.resume_input:
        restore_input(args.resume_input, args.output)
    run = args.output / "run"
    if args.prepared_input and run.exists():
        raise ValueError("prepared inputs require a fresh run; use resume for existing training")
    if (run / "protocol.json").exists():
        # The core controller also enforces exact source/runtime/world-size pins.
        protocol = read_json(run / "protocol.json")
        if protocol["world_size"] != args.gpus:
            raise ValueError("resume must use the original GPU count")
        verify_full_recipe(read_json(run / "pipeline.json"), args.output, args.gpus)
        publish_data(read_json(run / "pipeline.json"), args.output / "data")
    else:
        if args.prepared_input:
            config = full_recipe(args.output, args.gpus)
            config["dataset"]["directory"] = str(args.prepared_input / "release")
            config["tokenizer"]["artifact_path"] = str(args.prepared_input / "tokenizer.json")
        else:
            config = world_config(read_json(EXAMPLES / "tac-10m-full.json"), args.gpus)
            config["dataset"] = {
                "source_plan": str(EXAMPLES / "data-plan.json"),
                "cache": str(args.cache),
            }
            temporary_config = args.output / "acquisition-config.json"
            write_json(temporary_config, config)
            config = prepare_configuration(temporary_config)
        config = publish_data(config, args.output / "data")
        verify_full_recipe(config, args.output, args.gpus)
        write_json(args.output / "training-config.json", config)
        # Raw shards are no longer needed by the trainer. These hints change no bytes.
        if hasattr(os, "posix_fadvise"):
            for path in (args.cache / "raw").rglob("*.parquet"):
                with path.open("rb") as f:
                    os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
    subprocess.run(
        torch_command(args.gpus)
        + [
            str(Path(__file__).resolve()),
            "--probe",
            "--output",
            str(args.output),
            "--gpus",
            str(args.gpus),
        ],
        check=True,
    )
    command = torch_command(args.gpus) + ["-m", "trainlab", "pipeline"]
    command += (
        ["resume", str(run)]
        if (run / "protocol.json").exists()
        else ["run", str(args.output / "training-config.json"), "--output", str(run)]
    )
    subprocess.run(command, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/kaggle/working/fullcycle003"))
    parser.add_argument("--cache", type=Path, default=Path("/tmp/fullcycle003-cache"))
    parser.add_argument("--gpus", type=int, choices=(1, 2), default=2)
    parser.add_argument("--budget-seconds", type=int, default=14400)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--resume-input", type=Path)
    inputs.add_argument("--prepared-input", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.output, args.cache = args.output.resolve(), args.cache.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    if args.probe:
        probe(args.output, args.gpus)
        return
    if args.worker:
        worker(args)
        return
    if not 60 <= args.budget_seconds <= 14400:
        parser.error("first-session budget must be between 60 seconds and four hours")
    started = time.time()
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--output",
        str(args.output),
        "--cache",
        str(args.cache),
        "--gpus",
        str(args.gpus),
    ]
    if args.resume_input:
        command += ["--resume-input", str(args.resume_input)]
    if args.prepared_input:
        command += ["--prepared-input", str(args.prepared_input)]
    receipt = launch(command, args.budget_seconds)
    receipt.update(
        schema="trainlab.kaggle-session.v1",
        elapsed_seconds=time.time() - started,
        training_ranks=args.gpus,
        budget_seconds=args.budget_seconds,
        qualification="NOT_QUALIFIED",
        status="FAILED",
    )
    # Preserve the primary worker outcome even if later artifact inspection fails.
    (args.output / "session-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    report = args.output / "run/report.json"
    if report.exists() and receipt["returncode"] == 0:
        from trainlab.fullcycle.pipeline import verify_pipeline

        verify_pipeline(args.output / "run")
        receipt["status"] = "COMPLETE"
    else:
        receipt["status"] = (
            "INTERRUPTED"
            if receipt["budget_expired"] or receipt["operator_interrupted"]
            else "FAILED"
        )
        receipt["resume_requires"] = (
            "saved data/run folders; identical source, runtime and GPU count"
        )
        from trainlab.runner import contained_file, digest, read_json

        for stage in ("rl", "dpo", "sft", "midtrain", "pretrain"):
            index_path = args.output / "run" / stage / "checkpoint-index.json"
            if index_path.exists():
                index = read_json(index_path)
                selected = contained_file(index_path.parent, index["file"])
                if digest(selected) != index["sha256"]:
                    raise ValueError("interrupted checkpoint digest mismatch")
                receipt["saved_checkpoint"] = {
                    "stage": stage,
                    "step": index["step"],
                    "sha256": index["sha256"],
                }
                break
    (args.output / "session-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
    if receipt["status"] == "FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
