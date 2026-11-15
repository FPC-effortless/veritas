from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import time
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any

if __package__ in (None, ""):
    from training_value_diagnostics import content_identity, interpretation, score_by_id
else:
    from .training_value_diagnostics import content_identity, interpretation, score_by_id


def _panel_hash(episode_ids: list[str]) -> str:
    payload = json.dumps(sorted(episode_ids), separators=(",", ":")).encode("utf-8")
    return "PANEL-" + hashlib.sha256(payload).hexdigest()[:24].upper()


def _paired_summary(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_by_id = score_by_id(before)
    after_by_id = score_by_id(after)
    if set(before_by_id) != set(after_by_id):
        raise ValueError("before/after held-out panels do not match")
    episode_ids = sorted(before_by_id)
    deltas = [after_by_id[episode_id] - before_by_id[episode_id] for episode_id in episode_ids]
    n = len(deltas)
    center = mean(deltas) if deltas else 0.0
    deviation = stdev(deltas) if n > 1 else 0.0
    error = deviation / math.sqrt(n) if n > 1 else 0.0

    from investigation_world.observatory.aggregation import critical_95

    margin = critical_95(n) * error
    improved = sum(delta > 0 for delta in deltas)
    unchanged = sum(delta == 0 for delta in deltas)
    regressed = sum(delta < 0 for delta in deltas)
    return {
        "n": n,
        "panel_id": _panel_hash(episode_ids),
        "mean_delta": round(center, 6),
        "median_delta": round(median(deltas), 6) if deltas else 0.0,
        "stddev_delta": round(deviation, 6),
        "standard_error": round(error, 6),
        "ci95_low": round(center - margin, 6),
        "ci95_high": round(center + margin, 6),
        "improved": improved,
        "unchanged": unchanged,
        "regressed": regressed,
        "proportion_improved": round(improved / n, 6) if n else 0.0,
        "proportion_regressed": round(regressed / n, 6) if n else 0.0,
        "episode_deltas": [
            {
                "episode_id": episode_id,
                "before": round(before_by_id[episode_id], 6),
                "after": round(after_by_id[episode_id], 6),
                "delta": round(after_by_id[episode_id] - before_by_id[episode_id], 6),
            }
            for episode_id in episode_ids
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run hardened Veritas SFT training-value evaluation with an explicit training RNG seed "
            "and paired held-out transfer statistics"
        )
    )
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--training-seed", type=int, required=True)
    parser.add_argument("--train-examples", type=int, default=24)
    parser.add_argument("--heldout-examples", type=int, default=100)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=5e-4)
    parser.add_argument("--max-length", type=int, default=1536)
    parser.add_argument("--max-new-tokens", type=int, default=192)
    parser.add_argument("--audit-examples", type=int, default=2)
    parser.add_argument(
        "--minimum-reference-score",
        type=float,
        default=None,
        help="Explicit target-sanity threshold; omission leaves interpretation unassessed",
    )
    args = parser.parse_args()
    if args.minimum_reference_score is not None and (
        not math.isfinite(args.minimum_reference_score) or not 0 < args.minimum_reference_score <= 1
    ):
        parser.error("minimum-reference-score must be finite and in (0,1]")
    if args.audit_examples < 0:
        parser.error("audit-examples must be nonnegative")

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from investigation_world.training_value import (
        build_diagnostic_examples,
        build_heldout_diagnostic_episodes,
        score_diagnostic_generator,
    )

    random.seed(args.training_seed)
    torch.manual_seed(args.training_seed)
    torch.set_num_threads(min(4, max(1, torch.get_num_threads())))
    started = time.time()

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        dtype=torch.float32,
        low_cpu_mem_usage=True,
    )
    model.eval()

    def render_prompt(prompt: str) -> str:
        messages = [
            {
                "role": "system",
                "content": "Follow the requested JSON schema exactly. Return JSON only.",
            },
            {"role": "user", "content": prompt},
        ]
        if getattr(tokenizer, "chat_template", None):
            return tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        return messages[0]["content"] + "\n\n" + messages[1]["content"] + "\n\n"

    generation_seconds = 0.0
    audit: dict[str, list[dict[str, str]]] = {}
    audit_phase = ""

    def generate(prompt: str) -> str:
        nonlocal generation_seconds
        rendered = render_prompt(prompt)
        encoded = tokenizer(
            rendered, return_tensors="pt", truncation=True, max_length=args.max_length
        )
        tick = time.time()
        with torch.inference_mode():
            output = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        generation_seconds += time.time() - tick
        generated = output[0][encoded["input_ids"].shape[-1] :]
        text = tokenizer.decode(generated, skip_special_tokens=True)
        bucket = audit.setdefault(audit_phase, [])
        if len(bucket) < args.audit_examples:
            bucket.append({"prompt": prompt, "output": text})
        return text

    train_rows = build_diagnostic_examples(count=args.train_examples)
    train_episodes = [row["episode"] for row in train_rows]
    heldout = build_heldout_diagnostic_episodes(count=args.heldout_examples)
    train_ids = [item.episode_id for item in train_episodes]
    heldout_ids = [item.episode_id for item in heldout]
    if set(train_ids) & set(heldout_ids):
        raise ValueError("train and held-out episode identities overlap")
    train_content = content_identity(train_episodes)
    heldout_content = content_identity(heldout)
    if {r["sha256"] for r in train_content} & {r["sha256"] for r in heldout_content}:
        raise ValueError("train and held-out exact episode contents overlap")
    train_panel_id = _panel_hash(train_ids)
    heldout_panel_id = _panel_hash(heldout_ids)

    target_by_prompt = {str(row["prompt"]): str(row["target"]) for row in train_rows}

    def reference_generate(prompt: str) -> str:
        return target_by_prompt[prompt]

    reference_train = score_diagnostic_generator(reference_generate, train_episodes)

    audit_phase = "train_before"
    train_before = score_diagnostic_generator(generate, train_episodes)
    audit_phase = "heldout_before"
    heldout_before = score_diagnostic_generator(generate, heldout)

    lora = LoraConfig(
        task_type="CAUSAL_LM",
        r=8,
        lora_alpha=16,
        lora_dropout=0.0,
        target_modules=["q_proj", "v_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora)
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.learning_rate)

    losses: list[float] = []
    optimizer.zero_grad(set_to_none=True)
    accumulation = 4
    model.train()
    for epoch in range(args.epochs):
        order = list(range(len(train_rows)))
        random.Random(args.training_seed + epoch).shuffle(order)
        for step_index, row_index in enumerate(order):
            row = train_rows[row_index]
            prompt_text = render_prompt(str(row["prompt"]))
            target_text = str(row["target"])
            full_text = prompt_text + target_text + (tokenizer.eos_token or "")
            prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
            encoded = tokenizer(
                full_text,
                return_tensors="pt",
                truncation=True,
                max_length=args.max_length,
            )
            labels = encoded["input_ids"].clone()
            prompt_len = min(len(prompt_ids), labels.shape[-1])
            labels[:, :prompt_len] = -100
            output = model(**encoded, labels=labels)
            loss = output.loss / accumulation
            loss.backward()
            losses.append(float(output.loss.detach()))
            if (step_index + 1) % accumulation == 0 or step_index + 1 == len(order):
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)

    model.eval()
    audit_phase = "train_after"
    train_after = score_diagnostic_generator(generate, train_episodes)
    audit_phase = "heldout_after"
    heldout_after = score_diagnostic_generator(generate, heldout)

    train_gain = round(train_after["mean"] - train_before["mean"], 6)
    heldout_gain = round(heldout_after["mean"] - heldout_before["mean"], 6)
    paired_heldout = _paired_summary(heldout_before, heldout_after)
    if paired_heldout["panel_id"] != heldout_panel_id:
        raise RuntimeError("paired held-out panel identity changed during scoring")

    diagnosis_record = interpretation(
        reference_train,
        train_before,
        train_after,
        heldout_before,
        heldout_after,
        minimum_reference_score=args.minimum_reference_score,
    )
    diagnosis = diagnosis_record["diagnosis"]

    report: dict[str, Any] = {
        "schema_version": "0.3.2",
        "experiment": "diagnostic_lora_sft_hardened_paired_transfer",
        "verifier_contract": "grounded-companyworld-v0.9.1",
        "model": args.model,
        "training_seed": args.training_seed,
        "generation_mode": "deterministic_greedy",
        "train_world_id": "CW-TRAINING",
        "heldout_world_id": "CW-HELDOUT",
        "train_panel_id": train_panel_id,
        "heldout_panel_id": heldout_panel_id,
        "train_episode_ids": train_ids,
        "heldout_episode_ids": heldout_ids,
        "train_examples": len(train_rows),
        "heldout_examples": len(heldout),
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "lora": {"r": 8, "alpha": 16, "target_modules": ["q_proj", "v_proj"]},
        "reference_target_sanity": reference_train,
        "train_before": train_before,
        "train_after": train_after,
        "heldout_before": heldout_before,
        "heldout_after": heldout_after,
        "train_absolute_improvement": train_gain,
        "heldout_absolute_improvement": heldout_gain,
        "paired_heldout": paired_heldout,
        "diagnosis": diagnosis,
        "interpretation": diagnosis_record,
        "split_integrity": {
            "train_contents": train_content,
            "heldout_contents": heldout_content,
            "exact_ids_and_serialized_contents_disjoint": True,
            "semantic_or_near_duplicate_disjointness": "NOT_ESTABLISHED",
            "scope": "Generated episode serialization only; renamed structures can remain equivalent.",
        },
        "audit_coverage": {
            "requested_per_phase": args.audit_examples,
            "observed_per_phase": {key: len(value) for key, value in audit.items()},
            "selection": "FIRST_N_NOT_RANDOMIZED",
            "complete_output_replay": "NOT_ESTABLISHED",
        },
        "parse_semantics": "Nonempty decoded JSON object, not schema validity or correct claims",
        "training_qualification": "NOT_QUALIFIED_USE_CANONICAL_TRAIN_001",
        "tiny_overfit_control": "NOT_PERFORMED_BY_THIS_RUNNER",
        "mean_training_loss": round(sum(losses) / len(losses), 6) if losses else None,
        "audit": audit,
        "runtime": {
            "wall_seconds": round(time.time() - started, 3),
            "generation_seconds": round(generation_seconds, 3),
            "device": "cpu",
            "torch_threads": torch.get_num_threads(),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
