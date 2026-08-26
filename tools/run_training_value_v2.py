from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a Veritas SFT diagnostic separating training fit from held-out transfer"
    )
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-examples", type=int, default=24)
    parser.add_argument("--heldout-examples", type=int, default=12)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--max-length", type=int, default=1536)
    parser.add_argument("--max-new-tokens", type=int, default=192)
    parser.add_argument("--audit-examples", type=int, default=2)
    args = parser.parse_args()

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from investigation_world.training_value import (
        build_diagnostic_examples,
        build_heldout_diagnostic_episodes,
        score_diagnostic_generator,
    )

    torch.manual_seed(7)
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
            {"role": "system", "content": "Follow the requested JSON schema exactly. Return JSON only."},
            {"role": "user", "content": prompt},
        ]
        if getattr(tokenizer, "chat_template", None):
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        return messages[0]["content"] + "\n\n" + messages[1]["content"] + "\n\n"

    generation_seconds = 0.0
    audit: dict[str, list[dict[str, str]]] = {}
    audit_phase = ""

    def generate(prompt: str) -> str:
        nonlocal generation_seconds
        rendered = render_prompt(prompt)
        encoded = tokenizer(rendered, return_tensors="pt", truncation=True, max_length=args.max_length)
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
    for _epoch in range(args.epochs):
        for row_index, row in enumerate(train_rows):
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
            if (row_index + 1) % accumulation == 0 or row_index + 1 == len(train_rows):
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)

    model.eval()
    audit_phase = "train_after"
    train_after = score_diagnostic_generator(generate, train_episodes)
    audit_phase = "heldout_after"
    heldout_after = score_diagnostic_generator(generate, heldout)

    train_gain = round(train_after["mean"] - train_before["mean"], 6)
    heldout_gain = round(heldout_after["mean"] - heldout_before["mean"], 6)

    if train_gain <= 0:
        diagnosis = "no_detected_training_fit"
    elif heldout_gain <= 0:
        diagnosis = "training_fit_without_detected_transfer"
    else:
        diagnosis = "training_fit_with_heldout_transfer"

    report: dict[str, Any] = {
        "schema_version": "0.2.0",
        "experiment": "diagnostic_lora_sft_fit_vs_transfer",
        "model": args.model,
        "train_world_id": "CW-TRAINING",
        "heldout_world_id": "CW-HELDOUT",
        "train_episode_ids": [item.episode_id for item in train_episodes],
        "heldout_episode_ids": [item.episode_id for item in heldout],
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
        "diagnosis": diagnosis,
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
