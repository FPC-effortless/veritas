"""Real optimizer updates, reference DPO, bounded on-policy GRPO and replay state."""

from __future__ import annotations

import contextlib
import copy
import math
import os
import signal
import time
from pathlib import Path

import numpy as np
import torch
import torch.distributed as dist
from torch.nn import functional as F
from torch.nn.parallel import DistributedDataParallel

from trainlab.runner import LabError, contained_file, digest, read_json, write_json

from .backends import configuration, create_model
from .tokenization import RecordSource


def atomic_checkpoint(path, value):
    path = Path(path)
    temp = path.with_suffix(".tmp")
    try:
        with temp.open("wb") as f:
            torch.save(value, f)
            f.flush()
            os.fsync(f.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def checkpoint_load(path):
    return torch.load(path, map_location="cpu", weights_only=True)


def batch_sequences(examples, count, context, pad, generator, device):
    choices = torch.randint(len(examples), (count,), generator=generator).tolist()
    selected = [examples[i] for i in choices]
    # Reject target truncation instead of silently training prompt-only batches.
    if any(len(ids) > context + 1 for ids, _ in selected):
        raise LabError("conversation exceeds context; increase context or curate shorter rows")
    length = max(len(ids) for ids, _ in selected)
    x = torch.full((count, length), pad, dtype=torch.long)
    mask = torch.zeros((count, length), dtype=torch.bool)
    for i, (ids, loss_mask) in enumerate(selected):
        x[i, : len(ids)] = torch.tensor(ids)
        mask[i, : len(ids)] = torch.tensor(loss_mask)
    return x[:, :-1].to(device), x[:, 1:].to(device), mask[:, 1:].to(device)


def sequence_logp(model, batch):
    x, y, mask = batch
    logp = F.log_softmax(model(x).float(), -1).gather(-1, y[..., None]).squeeze(-1)
    return (logp * mask).sum(-1), mask.sum(-1)


def dpo_loss(chosen, rejected, ref_chosen, ref_rejected, beta):
    return -F.logsigmoid(beta * ((chosen - rejected) - (ref_chosen - ref_rejected))).mean()


def task_reward(row, completion):
    """Public bounded verifier; no eval-label file or caller-supplied reward."""
    if row["verifier"] == "gsm8k-exact-v1":
        from forge_data.verifiers import verify_math

        return verify_math(row, completion)
    if row["verifier"] != "integer-comparison-v1":
        raise LabError("unsupported rollout verifier")
    expected = "0" if row["left"] > row["right"] else "1"
    return float(completion == expected)


def validate_stage(stage, checkpoint_every=25):
    for key, value in {
        "steps": stage.get("steps"),
        "batch_size": stage.get("batch_size"),
        "gradient_accumulation": stage.get("gradient_accumulation", 1),
        "checkpoint_every": checkpoint_every,
    }.items():
        if type(value) is not int or value < 1:
            raise LabError(f"{key} must be a positive integer")
    if stage.get("name") not in ("pretrain", "midtrain", "sft", "dpo", "rl"):
        raise LabError("unsupported training stage")
    group = stage.get("group_size", 8)
    if type(group) is not int or group < 2:
        raise LabError("GRPO group_size must be at least two")
    for key, default, lower, upper in (
        ("learning_rate", None, 0, 1),
        ("beta", 0.1, 0, 100),
        ("gradient_clip", 1.0, 0, 1e6),
        ("clip_epsilon", 0.2, 0, 1),
    ):
        value = stage.get(key, default)
        if type(value) not in (float, int) or not math.isfinite(value) or not lower < value < upper:
            raise LabError(f"invalid stage {key}")
    for key, default in (("weight_decay", 0.01), ("kl_beta", 0.02), ("replay_weight", 0.0)):
        value = stage.get(key, default)
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise LabError(f"invalid stage {key}")
    if stage.get("rl_mode", "comparison") not in ("comparison", "completion"):
        raise LabError("unsupported RL trajectory mode")
    for key in ("sequence_length", "max_new_tokens"):
        if key in stage and (type(stage[key]) is not int or stage[key] < 1):
            raise LabError(f"{key} must be a positive integer")
    if stage.get("lr_schedule", "constant") not in ("constant", "cosine"):
        raise LabError("invalid learning-rate schedule")
    warmup = stage.get("warmup_steps", 0)
    if type(warmup) is not int or not 0 <= warmup < stage["steps"]:
        raise LabError("warmup must be a nonnegative update count below stage length")
    if not 0 <= stage.get("min_lr_ratio", 0.1) <= 1:
        raise LabError("invalid minimum learning-rate ratio")
    betas = stage.get("betas", [0.9, 0.999])
    if len(betas) != 2 or any(type(v) not in (int, float) or not 0 <= v < 1 for v in betas):
        raise LabError("invalid AdamW betas")
    temperature = stage.get("temperature", 1.0)
    if (
        type(temperature) not in (int, float)
        or not math.isfinite(temperature)
        or not 0 < temperature <= 2
    ):
        raise LabError("invalid policy sampling temperature")
    if "max_seconds" in stage:
        value = stage["max_seconds"]
        if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
            raise LabError("max_seconds must be positive and finite")


def learning_rate_at(stage, step):
    base = stage["learning_rate"]
    if stage.get("lr_schedule", "constant") == "constant":
        return base
    warmup = stage.get("warmup_steps", 0)
    if step < warmup:
        return base * (step + 1) / warmup
    progress = (step - warmup) / max(1, stage["steps"] - warmup - 1)
    minimum = stage.get("min_lr_ratio", 0.1)
    return base * (minimum + (1 - minimum) * 0.5 * (1 + math.cos(math.pi * progress)))


def train_stage(
    model_config,
    stage,
    release,
    tokens,
    packed,
    output,
    *,
    previous=None,
    resume=None,
    seed=7,
    device="cpu",
    precision="fp32",
    stop_after=None,
    checkpoint_every=25,
    rank=0,
    world_size=1,
    input_identity=None,
):
    validate_stage(stage, checkpoint_every)
    if stop_after is not None and (type(stop_after) is not int or stop_after < 1):
        raise LabError("stop_after must be a positive update count")
    stage_name = stage["name"]
    if stage_name not in ("pretrain", "midtrain", "sft", "dpo", "rl"):
        raise LabError("unsupported training stage")
    output = Path(output)
    if rank == 0:
        output.mkdir(parents=True, exist_ok=True)
    if world_size > 1:
        dist.barrier()
    torch.manual_seed(seed)
    model = create_model(model_config).to(device)
    model_config = configuration(model)
    if previous:
        model.load_state_dict(checkpoint_load(previous)["model"])
    reference = copy.deepcopy(model).eval() if stage_name in ("dpo", "rl") else None
    if reference is not None:
        reference.requires_grad_(False)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=stage["learning_rate"],
        weight_decay=stage.get("weight_decay", 0.01),
        betas=tuple(stage.get("betas", [0.9, 0.999])),
    )
    if precision not in ("fp32", "bf16", "fp16"):
        raise LabError("unknown precision")
    if model_config["backend"] in ("tac098", "tac104") and precision != "fp32":
        raise LabError("native TAC mixed precision is not qualified; use fp32")
    if precision != "fp32" and not str(device).startswith("cuda"):
        raise LabError("mixed precision requires CUDA in this adapter")
    scaler = torch.amp.GradScaler("cuda", enabled=precision == "fp16")
    generator = torch.Generator().manual_seed(seed + rank * 100003)
    step, trained_tokens, target_tokens, rollouts = 0, 0, 0, 0
    losses, rewards, active_seconds, runtime = [], [], 0.0, {}
    if resume:
        index = read_json(output / "checkpoint-index.json")
        resume = contained_file(output, index["file"])
        if (
            digest(resume) != index["sha256"]
            or index.get("input_identity") != input_identity
            or index["previous_sha256"] != (digest(previous) if previous else None)
        ):
            raise LabError("resume checkpoint or parent hash mismatch")
        saved = checkpoint_load(resume)
        if saved["model_config"] != model_config or saved["stage"] != stage:
            raise LabError("resume model or stage configuration mismatch")
        if saved["world_size"] != world_size:
            raise LabError("exact replay requires identical world size")
        model.load_state_dict(saved["model"])
        optimizer.load_state_dict(saved["optimizer"])
        scaler.load_state_dict(saved["scaler"])
        if reference is not None:
            reference.load_state_dict(saved["reference"])
        runtime = saved["runtimes"][rank]
        generator.set_state(runtime["data_rng"])
        torch.set_rng_state(runtime["torch_rng"])
        if str(device).startswith("cuda"):
            torch.cuda.set_rng_state(runtime["cuda_rng"], device)
        step, trained_tokens, target_tokens = (
            saved["step"],
            saved["trained_tokens"],
            saved["target_tokens"],
        )
        rollouts, losses, rewards = saved["rollouts"], saved["losses"], saved["rewards"]
        active_seconds = saved["active_seconds"]
    network = (
        DistributedDataParallel(
            model,
            device_ids=[torch.device(device).index] if str(device).startswith("cuda") else None,
        )
        if world_size > 1
        else model
    )
    model.train()
    batch_size = stage["batch_size"]
    context = stage.get("sequence_length", model.config.context)
    if context > model.config.context:
        raise LabError("stage sequence length exceeds model context")
    accumulation = stage.get("gradient_accumulation", 1)
    examples, preferences, tasks, memory = [], [], [], None
    if stage_name == "pretrain" or stage.get("replay_weight", 0) > 0:
        memory = np.memmap(packed / "train.bin", mode="r", dtype="<u4")
        if len(memory) <= context:
            raise LabError("pretraining stream shorter than context")
    if stage_name in ("midtrain", "sft"):
        examples = RecordSource(packed, "conversation", all_tokens=stage_name == "midtrain")
        if not examples:
            raise LabError("missing TRAIN conversations")
    elif stage_name == "dpo":
        preferences = RecordSource(packed, "preference")
        if not preferences:
            raise LabError("missing TRAIN preferences")
    elif stage_name == "rl":
        tasks = RecordSource(packed, "task")
        if not tasks:
            raise LabError("missing TRAIN rollout tasks")
        if stage.get("rl_mode", "comparison") == "comparison":
            choice_ids = [tokens.encode(s) for s in ("0", "1")]
            if any(len(ids) != 1 for ids in choice_ids):
                raise LabError("bounded comparison rollout requires single-symbol choices")
            choice_ids = torch.tensor([ids[0] for ids in choice_ids], device=device)
    rollout_directory = output / "rollouts"
    if stage_name == "rl":
        rollout_directory.mkdir(exist_ok=True)
        # Discard uncommitted work beyond the last recovered complete update.
        for p in rollout_directory.glob(f"step-*-rank-{rank}.json"):
            if int(p.name.split("-")[1]) > step:
                p.unlink()
    from torch.utils.flop_counter import FlopCounterMode

    counter = FlopCounterMode(display=False)
    prior_flops = runtime.get("counted_flops", 0)
    started = time.perf_counter()
    previous_handlers, interrupted = {}, [False]

    def request_stop(signum, frame):
        interrupted[0] = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[sig] = signal.signal(sig, request_stop)

    def sync():
        if str(device).startswith("cuda"):
            torch.cuda.synchronize(device)

    def save():
        sync()
        current = {
            "counted_flops": prior_flops + counter.get_total_flops(),
            "data_rng": generator.get_state(),
            "torch_rng": torch.get_rng_state(),
            "cuda_rng": torch.cuda.get_rng_state(device)
            if str(device).startswith("cuda")
            else None,
        }
        runtimes = [None] * world_size
        if world_size > 1:
            dist.all_gather_object(runtimes, current)
        else:
            runtimes = [current]
        if rank == 0:
            old_index = (
                read_json(output / "checkpoint-index.json")
                if (output / "checkpoint-index.json").exists()
                else None
            )
            blob = output / f"checkpoint-step-{step:08d}.pt"
            atomic_checkpoint(
                blob,
                {
                    "schema": "trainlab.checkpoint.v1",
                    "model_config": configuration(model),
                    "model": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "reference": reference.state_dict() if reference is not None else None,
                    "scaler": scaler.state_dict(),
                    "stage": stage,
                    "world_size": world_size,
                    "step": step,
                    "trained_tokens": trained_tokens,
                    "target_tokens": target_tokens,
                    "rollouts": rollouts,
                    "losses": losses,
                    "rewards": rewards,
                    "active_seconds": active_seconds + time.perf_counter() - started,
                    "runtimes": runtimes,
                },
            )
        if rank == 0:
            write_json(
                output / "checkpoint-index.json",
                {
                    "file": blob.name,
                    "sha256": digest(blob),
                    "previous_sha256": digest(previous) if previous else None,
                    "step": step,
                    "input_identity": input_identity,
                },
            )
            # Commit pointer before publishing the compatibility alias. An interruption
            # always leaves either the old or the new complete checkpoint selected.
            alias = output / ".resume-link.tmp"
            alias.unlink(missing_ok=True)
            os.link(blob, alias)
            alias.replace(output / "resume.pt")
            keep = {blob.name, old_index["file"] if old_index else blob.name}
            for obsolete in output.glob("checkpoint-step-*.pt"):
                if obsolete.name not in keep:
                    obsolete.unlink()
        if world_size > 1:
            dist.barrier()

    counter.__enter__()
    try:
        while step < stage["steps"]:
            for group in optimizer.param_groups:
                group["lr"] = learning_rate_at(stage, step)
            optimizer.zero_grad(set_to_none=True)
            update_loss, update_reward, update_rollouts = 0.0, [], []
            for micro in range(accumulation):
                amp = (
                    torch.autocast(
                        "cuda", dtype=torch.bfloat16 if precision == "bf16" else torch.float16
                    )
                    if precision != "fp32"
                    else contextlib.nullcontext()
                )
                with amp:
                    if stage_name == "pretrain":
                        starts = torch.randint(
                            len(memory) - context, (batch_size,), generator=generator
                        ).tolist()
                        sequences = torch.tensor(
                            np.stack(
                                [
                                    np.asarray(memory[s : s + context + 1], dtype=np.int64)
                                    for s in starts
                                ]
                            ),
                            device=device,
                        )
                        logits = network(sequences[:, :-1])
                        loss = F.cross_entropy(
                            logits.float().flatten(0, 1), sequences[:, 1:].flatten()
                        )
                        used, targets = batch_size * context, batch_size * context
                    elif stage_name in ("midtrain", "sft"):
                        batch = batch_sequences(
                            examples, batch_size, context, tokens.pad, generator, device
                        )
                        logp, counts = sequence_logp(network, batch)
                        if not counts.sum():
                            raise LabError("no assistant targets")
                        denominator = counts.sum().clone()
                        if world_size > 1:
                            dist.all_reduce(denominator, op=dist.ReduceOp.SUM)
                        loss = -logp.sum() * world_size / denominator
                        used, targets = batch[0].numel(), int(counts.sum())
                    elif stage_name == "dpo":
                        indices = torch.randint(
                            len(preferences), (batch_size,), generator=generator
                        ).tolist()
                        pairs = [preferences[i] for i in indices]
                        chosen = [tokens.preference(r["prompt"], r["chosen"]) for r in pairs]
                        rejected = [tokens.preference(r["prompt"], r["rejected"]) for r in pairs]
                        # Ordered batches use every selected preference once.
                        order = torch.Generator().manual_seed(0)

                        def ordered_batch(values):
                            # Singleton conversion preserves chosen/rejected pairing.
                            pieces = [
                                batch_sequences([v], 1, context, tokens.pad, order, device)
                                for v in values
                            ]
                            length = max(p[0].shape[1] for p in pieces)
                            return tuple(
                                torch.cat(
                                    [
                                        F.pad(
                                            p[j],
                                            (0, length - p[j].shape[1]),
                                            value=tokens.pad if j < 2 else False,
                                        )
                                        for p in pieces
                                    ]
                                )
                                for j in range(3)
                            )

                        bc, br = ordered_batch(chosen), ordered_batch(rejected)
                        pc, _ = sequence_logp(network, bc)
                        pr, _ = sequence_logp(network, br)
                        with torch.no_grad():
                            rc, _ = sequence_logp(reference, bc)
                            rr, _ = sequence_logp(reference, br)
                        loss = dpo_loss(pc, pr, rc, rr, stage.get("beta", 0.1))
                        used, targets = (
                            bc[0].numel() + br[0].numel(),
                            int(bc[2].sum() + br[2].sum()),
                        )
                    elif stage_name == "rl" and stage.get("rl_mode") == "completion":
                        from .rl import completion_grpo

                        selected = [
                            tasks[i]
                            for i in torch.randint(
                                len(tasks), (batch_size,), generator=generator
                            ).tolist()
                        ]
                        loss, used, targets, n, records, sampled_rewards = completion_grpo(
                            network, model, reference, selected, tokens, generator, stage
                        )
                        update_reward.extend(sampled_rewards)
                        update_rollouts.extend(
                            {"step": step + 1, "micro": micro, **r} for r in records
                        )
                        rollouts += n
                    else:
                        group_size = stage.get("group_size", 8)
                        rows = [
                            tasks[i]
                            for i in torch.randint(
                                len(tasks), (batch_size,), generator=generator
                            ).tolist()
                        ]
                        total, used, targets = [], 0, 0
                        # One-token constrained policy is explicit: legal responses are 0 or 1.
                        # Rewards come only after actual categorical policy sampling.
                        for row in rows:
                            ids, _ = tokens.conversation(
                                [{"role": "user", "content": row["prompt"]}], prompt=True
                            )
                            if len(ids) > context:
                                raise LabError("rollout prompt exceeds context")
                            x = torch.tensor([ids], device=device)
                            with torch.no_grad():
                                old = F.log_softmax(model(x)[0, -1, choice_ids].float(), -1)
                                actions = torch.multinomial(
                                    old.exp().cpu(),
                                    group_size,
                                    replacement=True,
                                    generator=generator,
                                ).to(device)
                                values = torch.tensor(
                                    [task_reward(row, str(a)) for a in actions.tolist()],
                                    device=device,
                                )
                                advantages = (values - values.mean()) / values.std(
                                    unbiased=False
                                ).clamp_min(1e-4)
                                ref = F.log_softmax(reference(x)[0, -1, choice_ids].float(), -1)
                            logp = F.log_softmax(network(x)[0, -1, choice_ids].float(), -1)
                            ratio = (logp[actions] - old[actions]).exp()
                            epsilon = stage.get("clip_epsilon", 0.2)
                            policy = -torch.minimum(
                                ratio * advantages,
                                ratio.clamp(1 - epsilon, 1 + epsilon) * advantages,
                            ).mean()
                            kl = (logp.exp() * (logp - ref)).sum()
                            total.append(policy + stage.get("kl_beta", 0.02) * kl)
                            update_rollouts.append(
                                {
                                    "step": step + 1,
                                    "micro": micro,
                                    "group": row["group"],
                                    "prompt": row["prompt"],
                                    "left": row["left"],
                                    "right": row["right"],
                                    "verifier": row["verifier"],
                                    "actions": actions.tolist(),
                                    "old_log_probabilities": old.tolist(),
                                    "rewards": values.tolist(),
                                    "sampling": "categorical; legal actions 0 and 1",
                                }
                            )
                            update_reward.extend(values.tolist())
                            used += len(ids) * 2
                            targets += group_size
                            rollouts += group_size
                        loss = torch.stack(total).mean()
                    if stage_name != "pretrain" and stage.get("replay_weight", 0) > 0:
                        positions = torch.randint(
                            len(memory) - context, (batch_size,), generator=generator
                        ).tolist()
                        replay = torch.tensor(
                            np.stack(
                                [
                                    np.asarray(memory[s : s + context + 1], dtype=np.int64)
                                    for s in positions
                                ]
                            ),
                            device=device,
                        )
                        replay_logits = network(replay[:, :-1])
                        replay_loss = F.cross_entropy(
                            replay_logits.float().flatten(0, 1), replay[:, 1:].flatten()
                        )
                        loss = loss + stage["replay_weight"] * replay_loss
                        used += replay[:, :-1].numel()
                        targets += replay[:, 1:].numel()
                    if not torch.isfinite(loss):
                        raise LabError("nonfinite training loss")
                    scaler.scale(loss / accumulation).backward()
                if world_size > 1:
                    counters = torch.tensor([used, targets], dtype=torch.long, device=device)
                    dist.all_reduce(counters, op=dist.ReduceOp.SUM)
                    used, targets = counters.tolist()
                trained_tokens += used
                target_tokens += targets
                update_loss += loss.detach().float().item() / accumulation
            scaler.unscale_(optimizer)
            grad = torch.nn.utils.clip_grad_norm_(
                model.parameters(), stage.get("gradient_clip", 1.0)
            )
            if not torch.isfinite(grad):
                raise LabError("nonfinite gradient; checkpoint remains at last complete update")
            old_scale = scaler.get_scale()
            scaler.step(optimizer)
            scaler.update()
            if scaler.get_scale() < old_scale:
                raise LabError(
                    "overflow skipped optimizer step; resume last checkpoint with safer precision"
                )
            step += 1
            if stage_name == "rl":
                write_json(
                    rollout_directory / f"step-{step:08d}-rank-{rank}.json",
                    {"policy_rollouts": update_rollouts},
                )
            losses.append(update_loss)
            if update_reward:
                rewards.append(sum(update_reward) / len(update_reward))
            stop = interrupted[0] or (stop_after is not None and step >= stop_after)
            if stage.get("max_seconds") and time.perf_counter() - started >= stage["max_seconds"]:
                stop = True
            if world_size > 1:
                flag = torch.tensor(int(stop), device=device)
                dist.all_reduce(flag, op=dist.ReduceOp.MAX)
                stop = bool(flag.item())
            if step % checkpoint_every == 0 or stop or step == stage["steps"]:
                save()
            if rank == 0 and (
                step == 1 or step % checkpoint_every == 0 or stop or step == stage["steps"]
            ):
                print(f"{stage_name} {step}/{stage['steps']} loss={update_loss:.4f}", flush=True)
            if stop:
                break
    finally:
        counter.__exit__(None, None, None)
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
    sync()
    elapsed = active_seconds + time.perf_counter() - started
    counted_flops = prior_flops + counter.get_total_flops()
    if world_size > 1:
        value = torch.tensor(counted_flops, dtype=torch.int64, device=device)
        dist.all_reduce(value, op=dist.ReduceOp.SUM)
        counted_flops = value.item()
    if rank == 0 and stage_name == "rl" and step == stage["steps"]:
        write_json(
            output / "rollout-manifest.json",
            {
                "files": {
                    str(p.relative_to(output)): digest(p)
                    for p in sorted(rollout_directory.glob("*.json"))
                },
                "expected_updates": step,
                "world_size": world_size,
            },
        )
    if rank == 0 and step == stage["steps"]:
        index = read_json(output / "checkpoint-index.json")
        blob = contained_file(output, index["file"])
        final = output / "checkpoint.pt"
        if final.exists() and digest(final) != index["sha256"]:
            raise LabError("completed checkpoint differs from committed pointer")
        if not final.exists():
            alias = output / ".final-link.tmp"
            alias.unlink(missing_ok=True)
            os.link(blob, alias)
            alias.replace(final)
        (output / "resume.pt").unlink(missing_ok=True)
    if world_size > 1:
        dist.barrier()
    metrics = {
        "stage": stage_name,
        "status": "complete" if step == stage["steps"] else "paused",
        "optimizer_updates": step,
        "forward_token_positions": trained_tokens,
        "target_tokens": target_tokens,
        "policy_rollouts_per_rank": rollouts,
        "active_seconds": elapsed,
        "tokens_per_second": trained_tokens / max(elapsed, 1e-9),
        "milliseconds_per_update": 1000 * elapsed / max(step, 1),
        "loss_first": losses[0] if losses else None,
        "loss_last": losses[-1] if losses else None,
        "mean_rollout_reward": sum(rewards) / len(rewards) if rewards else None,
        "parameters": sum(p.numel() for p in model.parameters()),
        "replay_weight": stage.get("replay_weight", 0.0),
        "last_learning_rate": optimizer.param_groups[0]["lr"],
        "rl_mode": stage.get("rl_mode") if stage_name == "rl" else None,
        "precision": precision,
        "world_size": world_size,
        "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated(device)
        if str(device).startswith("cuda")
        else None,
        "gpu_hours": elapsed * world_size / 3600 if str(device).startswith("cuda") else 0,
        "actual_training_flops": None,
        "counted_training_operator_flops": counted_flops,
        "flop_counter_scope": "PyTorch FlopCounterMode supported operators across executed "
        "forward/backward/rollout/reference work; elementwise/scan overhead may be omitted",
        "estimated_6N_forward_token_flops": 6
        * sum(p.numel() for p in model.parameters())
        * trained_tokens,
        "flop_note": "parameter heuristic; excludes reference/rollout "
        "forwards, attention and scan overhead; not measured FLOPs",
    }
    if rank == 0:
        write_json(output / "metrics.json", metrics)
    return metrics
