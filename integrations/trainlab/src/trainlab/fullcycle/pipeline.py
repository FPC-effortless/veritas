"""Pinned stage DAG, recovery, immutable stage receipts and model promotion."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import torch
import torch.distributed as dist
from forge_data.language import LanguageRelease

from trainlab.runner import LabError, contained_file, digest, read_json, write_json

from .backends import ModelConfig, create_model
from .inference import export_model, load_bundle
from .tokenization import Tokens, fit_tokenizer, pack_training
from .training import atomic_checkpoint, train_stage, validate_stage

STAGES = ["pretrain", "midtrain", "sft", "dpo", "rl"]


def object_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def source_identity():
    import forge_data.language

    import investigation_world.lm_evaluation

    paths = sorted([*Path(__file__).parent.glob("*.py"), *Path(__file__).parent.glob("*.html")]) + [
        Path(forge_data.language.__file__),
        Path(forge_data.language.__file__).with_name("hub.py"),
        Path(forge_data.language.__file__).with_name("verifiers.py"),
        Path(investigation_world.lm_evaluation.__file__),
    ]
    return {
        (
            "fullcycle/" + p.name
            if p.parent == Path(__file__).parent
            else p.parent.name + "/" + p.name
        ): digest(p)
        for p in paths
    }


def runtime_identity(config):
    import numpy
    import tokenizers

    use_cuda = config.get("device") in ("auto", "cuda") and torch.cuda.is_available()
    return {
        "python": platform.python_version(),
        "torch": str(torch.__version__),
        "numpy": numpy.__version__,
        "tokenizers": tokenizers.__version__,
        "platform": platform.platform(),
        "device": "cuda" if use_cuda else "cpu",
        "cuda_runtime": torch.version.cuda if use_cuda else None,
        "cudnn": torch.backends.cudnn.version() if use_cuda else None,
        "torch_build_sha256": hashlib.sha256(torch.__config__.show().encode()).hexdigest(),
        "precision": config.get("precision", "fp32"),
    }


def validate_config(config):
    if config.get("schema") != "trainlab.pipeline.v1":
        raise LabError("unsupported pipeline schema")
    if [s.get("name") for s in config["stages"]] != STAGES:
        raise LabError("complete pipeline requires pretrain, midtrain, sft, dpo, rl in order")
    if type(config.get("seed")) is not int:
        raise LabError("integer seed required")
    for stage in config["stages"]:
        validate_stage(stage, config.get("checkpoint_every", 25))
    if type(config.get("cpu_threads", 2)) is not int or config.get("cpu_threads", 2) < 1:
        raise LabError("cpu_threads must be positive")
    if (
        type(config.get("evaluation_token_budget", 4096)) is not int
        or config.get("evaluation_token_budget", 4096) < 1
    ):
        raise LabError("evaluation_token_budget must be positive")
    if config.get("device", "cpu") not in ("cpu", "cuda", "auto"):
        raise LabError("device must be cpu, cuda or auto")
    if config.get("device") == "cuda" and not torch.cuda.is_available():
        raise LabError("CUDA was requested but is unavailable")
    return config


def verify_receipt(directory, receipt, expected_input):
    if receipt.get("input_identity") != expected_input or receipt.get("status") != "complete":
        raise LabError("stage receipt dependency or completion mismatch")
    expected_files = {"checkpoint.pt", "metrics.json", "evaluation.json"}
    if Path(directory).name == "rl":
        expected_files.add("rollout-manifest.json")
    if set(receipt.get("files", {})) != expected_files:
        raise LabError("stage receipt requires exact checkpoint, metrics and evaluation artifacts")
    for name, sha in receipt["files"].items():
        if digest(contained_file(directory, name)) != sha:
            raise LabError("stage artifact hash mismatch; refusing silent skip")
    if "rollout-manifest.json" in expected_files:
        manifest = read_json(Path(directory) / "rollout-manifest.json", limit=16 * 1024 * 1024)
        expected = manifest["expected_updates"] * manifest["world_size"]
        if len(manifest["files"]) != expected:
            raise LabError("rollout evidence coverage mismatch")
        for name, sha in manifest["files"].items():
            if digest(contained_file(directory, name)) != sha:
                raise LabError("rollout evidence changed")


@contextlib.contextmanager
def run_lock(directory, rank):
    if rank:
        yield
        return
    import fcntl

    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LabError("pipeline is already running") from exc
        yield


def _evaluation(checkpoint, tokenizer, config, output, split="validation"):
    output = Path(output)
    receipt_path = output.with_suffix(".receipt.json")
    expected = object_hash(
        {
            "checkpoint": digest(checkpoint),
            "tokenizer": digest(tokenizer),
            "dataset": config["dataset"]["manifest_sha256"],
            "split": split,
            "budget": config.get("evaluation_token_budget", 4096),
            "evaluator": source_identity(),
            "case_limit": config.get("evaluation_case_limit"),
            "generation_limit": config.get("evaluation_generation_limit", 8),
            "max_new_tokens": config.get("evaluation_max_new_tokens", 48),
            "device": "cuda"
            if config.get("device") in ("cuda", "auto") and torch.cuda.is_available()
            else "cpu",
        }
    )
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        if receipt["input_identity"] != expected or receipt["sha256"] != digest(output):
            raise LabError("cached evaluation input or output hash mismatch")
        return read_json(output, limit=16 * 1024 * 1024)
    temporary = output.with_suffix(".tmp.json")
    argv = [
        sys.executable,
        "-m",
        "investigation_world.lm_evaluation",
        "--checkpoint",
        str(checkpoint),
        "--tokenizer",
        str(tokenizer),
        "--release",
        config["dataset"]["directory"],
        "--release-sha256",
        config["dataset"]["manifest_sha256"],
        "--split",
        split,
        "--output",
        str(temporary),
        "--text-token-budget",
        str(config.get("evaluation_token_budget", 4096)),
    ]
    if config.get("evaluation_case_limit") is not None:
        argv += ["--case-limit", str(config["evaluation_case_limit"])]
    argv += [
        "--generation-limit",
        str(config.get("evaluation_generation_limit", 8)),
        "--max-new-tokens",
        str(config.get("evaluation_max_new_tokens", 48)),
        "--device",
        "cuda" if config.get("device") in ("cuda", "auto") and torch.cuda.is_available() else "cpu",
    ]
    # New process loads weights and held-out data; no trainer metric argument exists.
    result = subprocess.run(argv, capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise LabError("public evaluator failed: " + result.stderr[-4000:])
    result = read_json(temporary, limit=16 * 1024 * 1024)
    temporary.replace(output)
    write_json(receipt_path, {"input_identity": expected, "sha256": digest(output)})
    return result


def prepare_configuration(config_path):
    """Resolve a source plan before distributed initialization or optimizer creation."""
    config_path = Path(config_path).resolve()
    config = validate_config(read_json(config_path))
    dataset = config["dataset"]
    if "source_plan" in dataset:
        from forge_data.hub import prepare

        plan_path = (config_path.parent / dataset["source_plan"]).resolve()
        cache = (config_path.parent / dataset["cache"]).resolve()
        result = prepare(plan_path, cache)
        config["dataset"] = {
            "directory": str(cache / result["release"]),
            "manifest_sha256": result["manifest_sha256"],
            "source_plan_sha256": result["plan_sha256"],
            "acquisition_sha256": result["acquisition_sha256"],
        }
        config["tokenizer"] = {
            "kind": "artifact",
            "artifact_path": str(cache / result["tokenizer"]["path"]),
            "artifact_sha256": result["tokenizer"]["sha256"],
        }
    else:
        config["dataset"]["directory"] = str((config_path.parent / dataset["directory"]).resolve())
        if config["tokenizer"].get("kind") == "artifact":
            config["tokenizer"]["artifact_path"] = str(
                (config_path.parent / config["tokenizer"]["artifact_path"]).resolve()
            )
    return config


def run_pipeline(config_path=None, output=None, *, resume=False, stop_stage=None, stop_after=None):
    # Data preparation is serialized by a cache lock and precedes process-group timeouts.
    prepared_config = prepare_configuration(config_path) if not resume else None
    world = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    if world > 1 and not dist.is_initialized():
        launch_config = read_json(Path(output) / "pipeline.json") if resume else prepared_config
        use_cuda = launch_config.get("device") in ("cuda", "auto") and torch.cuda.is_available()
        if use_cuda:
            torch.cuda.set_device(local_rank)
        dist.init_process_group("nccl" if use_cuda else "gloo")
    output = Path(output).resolve()
    with run_lock(output, rank):
        if resume:
            config = read_json(output / "pipeline.json")
            protocol = read_json(output / "protocol.json")
            if protocol["configuration_sha256"] != object_hash(config):
                raise LabError("pipeline configuration changed")
            if protocol["source_files"] != source_identity():
                raise LabError("training/evaluator source changed; create a new run")
            if protocol["runtime"] != runtime_identity(config):
                raise LabError("runtime changed; exact replay requires a new run")
            if protocol["world_size"] != world:
                raise LabError("resume world size differs")
        else:
            config = prepared_config
            if (output / "protocol.json").exists():
                raise LabError("pipeline exists; use resume")
            protocol = {
                "schema": "trainlab.pipeline-protocol.v1",
                "configuration_sha256": object_hash(config),
                "source_files": source_identity(),
                "world_size": world,
                "runtime": runtime_identity(config),
                "python": platform.python_version(),
                "torch": torch.__version__,
                "platform": platform.platform(),
                "qualification": "NOT_QUALIFIED",
            }
            if rank == 0:
                write_json(output / "pipeline.json", config)
                write_json(output / "protocol.json", protocol)
        validate_config(config)
        requested = config.get("device", "cpu")
        device = (
            f"cuda:{local_rank}"
            if requested in ("auto", "cuda") and torch.cuda.is_available()
            else "cpu"
        )
        torch.set_num_threads(config.get("cpu_threads", 2))
        torch.use_deterministic_algorithms(config.get("deterministic", True))
        if device.startswith("cuda"):
            os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        release = LanguageRelease(
            config["dataset"]["directory"], config["dataset"]["manifest_sha256"]
        )
        tokens_path = output / "tokenizer.json"
        data_path = output / "tokens"
        if rank == 0 and not (output / "data-receipt.json").exists():
            if data_path.exists():
                shutil.rmtree(data_path)
            fit_tokenizer(release, tokens_path, **config["tokenizer"])
            info = pack_training(release, Tokens(tokens_path), data_path)
            write_json(
                output / "data-receipt.json",
                {
                    "tokenizer_sha256": digest(tokens_path),
                    "packed": info,
                    "dataset_sha256": release.manifest_sha256,
                    "protocol_sha256": object_hash(protocol),
                },
            )
        if world > 1:
            dist.barrier()
        data_receipt = read_json(output / "data-receipt.json")
        if (
            digest(tokens_path) != data_receipt["tokenizer_sha256"]
            or data_receipt["protocol_sha256"] != object_hash(protocol)
            or data_receipt["dataset_sha256"] != release.manifest_sha256
        ):
            raise LabError("tokenizer/data input identity mismatch")
        for item in data_receipt["packed"].values():
            if digest(contained_file(data_path, item["path"])) != item["sha256"]:
                raise LabError("packed token shard changed")
        tokens = Tokens(tokens_path)
        model_config = asdict(ModelConfig(**dict(config["model"], vocab_size=tokens.vocab_size)))
        initial = output / "initial.pt"
        if rank == 0 and not (output / "initial-receipt.json").exists():
            if any((output / s / "receipt.json").exists() for s in STAGES):
                raise LabError("initial receipt missing after stage promotion")
            torch.manual_seed(config["seed"])
            model = create_model(model_config)
            if "parameter_target" in config:
                count = sum(p.numel() for p in model.parameters())
                if (
                    abs(count - config["parameter_target"])
                    > config.get("parameter_tolerance", 0.01) * config["parameter_target"]
                ):
                    raise LabError("actual model exceeds the pinned parameter tolerance")
            atomic_checkpoint(initial, {"model": model.state_dict(), "model_config": model_config})
            write_json(output / "initial-receipt.json", {"sha256": digest(initial)})
        if world > 1:
            dist.barrier()
        if digest(initial) != read_json(output / "initial-receipt.json")["sha256"]:
            raise LabError("initial checkpoint hash mismatch")
        if rank == 0:
            _evaluation(initial, tokens_path, config, output / "baseline-evaluation.json")
        previous, stages = initial, []
        for stage in config["stages"]:
            directory = output / stage["name"]
            receipt_path = directory / "receipt.json"
            identity = object_hash(
                {
                    "protocol": protocol,
                    "data": data_receipt,
                    "stage": stage,
                    "previous_checkpoint": digest(previous),
                }
            )
            if receipt_path.exists():
                receipt = read_json(receipt_path)
                verify_receipt(directory, receipt, identity)
                if rank == 0:
                    print(f"{stage['name']}: verified completed checkpoint; skipping", flush=True)
            else:
                if rank == 0:
                    write_json(output / "state.json", {"status": "running", "stage": stage["name"]})
                metrics = train_stage(
                    model_config,
                    stage,
                    release,
                    tokens,
                    data_path,
                    directory,
                    previous=previous,
                    resume=directory / "resume.pt"
                    if (directory / "checkpoint-index.json").exists()
                    else directory / "checkpoint.pt"
                    if (directory / "checkpoint.pt").exists()
                    else None,
                    seed=config["seed"],
                    device=device,
                    precision=config.get("precision", "fp32"),
                    stop_after=stop_after if stop_stage == stage["name"] else None,
                    checkpoint_every=config.get("checkpoint_every", 25),
                    rank=rank,
                    world_size=world,
                    input_identity=identity,
                )
                if metrics["status"] != "complete":
                    if rank == 0:
                        write_json(
                            output / "state.json", {"status": "paused", "stage": stage["name"]}
                        )
                    return {"status": "paused", "directory": str(output), "stage": stage["name"]}
                if rank == 0:
                    _evaluation(
                        directory / "checkpoint.pt",
                        tokens_path,
                        config,
                        directory / "evaluation.json",
                    )
                    receipt = {
                        "status": "complete",
                        "input_identity": identity,
                        "files": {
                            n: digest(directory / n)
                            for n in (
                                ["checkpoint.pt", "metrics.json", "evaluation.json"]
                                + (["rollout-manifest.json"] if stage["name"] == "rl" else [])
                            )
                        },
                    }
                    write_json(receipt_path, receipt)
            if world > 1:
                dist.barrier()
            previous = directory / "checkpoint.pt"
            stages.append(
                {
                    "name": stage["name"],
                    "metrics": read_json(directory / "metrics.json"),
                    "evaluation": read_json(directory / "evaluation.json", limit=16 * 1024 * 1024),
                }
            )
        if rank == 0:
            bundle = output / "model"
            if not bundle.exists():
                export_model(previous, tokens_path, bundle)
            load_bundle(bundle)
            _evaluation(previous, tokens_path, config, output / "final-test.json", split="test")
            final = read_json(output / "final-test.json", limit=16 * 1024 * 1024)
            report = {
                "schema": "trainlab.fullcycle-report.v1",
                "status": "complete",
                "engineering_lifecycle": "COMPLETED",
                "protocol": protocol,
                "dataset_manifest_sha256": release.manifest_sha256,
                "model_manifest_sha256": digest(bundle / "manifest.json"),
                "baseline": read_json(output / "baseline-evaluation.json", limit=16 * 1024 * 1024),
                "stages": stages,
                "final_public_test": final,
                "total_optimizer_updates": sum(s["metrics"]["optimizer_updates"] for s in stages),
                "hardware": {
                    "device": device,
                    "world_size": world,
                    "name": torch.cuda.get_device_name(local_rank)
                    if device.startswith("cuda")
                    else platform.processor() or "CPU",
                },
                "scientific_qualification": "NOT_QUALIFIED",
                "independent_execution_attestation": "UNKNOWN",
                "limitations": [
                    "Single seed engineering run; no general capability claim.",
                    "Public within-source/group splits; not protected benchmarks.",
                    (
                        "RL uses public math completion rewards; bounded generations do not "
                        "establish general reasoning capability."
                        if any(s.get("rl_mode") == "completion" for s in config["stages"])
                        else "RL uses constrained one-token integer comparisons."
                    ),
                    "No coding or agentic environment capability evaluation.",
                    "Operator FLOPs are counted where supported; total hardware FLOPs and "
                    "scan/elementwise overhead are not measured. GPU claims require GPU evidence.",
                ],
            }
            write_json(output / "report.json", report)
            write_json(output / "report-receipt.json", {"sha256": digest(output / "report.json")})
            write_json(output / "state.json", {"status": "complete", "model": str(bundle)})
            return {
                "status": "complete",
                "directory": str(output),
                "model": str(bundle),
                "updates": report["total_optimizer_updates"],
                "report": str(output / "report.json"),
            }
    return {"status": "worker_complete", "rank": rank}


def verify_pipeline(directory):
    """Recompute all source, dependency, tokenizer, checkpoint and report bindings."""
    directory = Path(directory)
    config = read_json(directory / "pipeline.json")
    protocol = read_json(directory / "protocol.json")
    if protocol["configuration_sha256"] != object_hash(config):
        raise LabError("configuration hash mismatch")
    data = read_json(directory / "data-receipt.json")
    if (
        data["protocol_sha256"] != object_hash(protocol)
        or data["dataset_sha256"] != config["dataset"]["manifest_sha256"]
        or digest(directory / "tokenizer.json") != data["tokenizer_sha256"]
    ):
        raise LabError("data receipt mismatch")
    LanguageRelease(config["dataset"]["directory"], config["dataset"]["manifest_sha256"])
    for item in data["packed"].values():
        if digest(contained_file(directory / "tokens", item["path"])) != item["sha256"]:
            raise LabError("token stream hash mismatch")
    previous = directory / "initial.pt"
    if digest(previous) != read_json(directory / "initial-receipt.json")["sha256"]:
        raise LabError("initial checkpoint mismatch")
    for stage in config["stages"]:
        sd = directory / stage["name"]
        identity = object_hash(
            {
                "protocol": protocol,
                "data": data,
                "stage": stage,
                "previous_checkpoint": digest(previous),
            }
        )
        verify_receipt(sd, read_json(sd / "receipt.json"), identity)
        previous = sd / "checkpoint.pt"
    if digest(directory / "report.json") != read_json(directory / "report-receipt.json")["sha256"]:
        raise LabError("report hash mismatch")
    report = read_json(directory / "report.json", limit=32 * 1024 * 1024)
    for name in ("baseline-evaluation", "final-test"):
        if (
            digest(directory / f"{name}.json")
            != read_json(directory / f"{name}.receipt.json")["sha256"]
        ):
            raise LabError("public evaluation digest mismatch")
    expected_stages = [
        {
            "name": stage["name"],
            "metrics": read_json(directory / stage["name"] / "metrics.json"),
            "evaluation": read_json(
                directory / stage["name"] / "evaluation.json", limit=16 * 1024 * 1024
            ),
        }
        for stage in config["stages"]
    ]
    if (
        report["stages"] != expected_stages
        or report["protocol"] != protocol
        or report["baseline"]
        != read_json(directory / "baseline-evaluation.json", limit=16 * 1024 * 1024)
        or report["total_optimizer_updates"]
        != sum(s["metrics"]["optimizer_updates"] for s in expected_stages)
    ):
        raise LabError("report disagrees with measured stage artifacts")
    load_bundle(directory / "model", expected_sha256=report["model_manifest_sha256"])
    if read_json(directory / "model" / "manifest.json")["checkpoint_sha256"] != digest(previous):
        raise LabError("final export checkpoint mismatch")
    final = read_json(directory / "final-test.json", limit=16 * 1024 * 1024)
    if final != report["final_public_test"] or final["checkpoint_sha256"] != digest(previous):
        raise LabError("final evaluation binding mismatch")
    return {
        "valid": True,
        "stages": STAGES,
        "qualification": "NOT_QUALIFIED",
        "execution_attestation": "UNKNOWN",
    }
