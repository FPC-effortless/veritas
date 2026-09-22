from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Veritas foundry transfer-training experiment")
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-candidates", type=int, default=16)
    parser.add_argument("--train-examples", type=int, default=48)
    parser.add_argument("--eval-per-split", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--max-new-tokens", type=int, default=192)
    args = parser.parse_args()

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from investigation_world.training_value import (
        build_training_rows,
        build_transfer_suite,
        score_generator,
        select_frontier_examples,
    )

    torch.manual_seed(11)
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
    generation_calls = 0

    def generate(prompt: str) -> str:
        nonlocal generation_seconds, generation_calls
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
        generation_calls += 1
        generated = output[0][encoded["input_ids"].shape[-1] :]
        return tokenizer.decode(generated, skip_special_tokens=True)

    suites = build_transfer_suite(
        train_candidates=args.train_candidates,
        eval_per_split=args.eval_per_split,
    )
    frontier = select_frontier_examples(generate, suites["train_pool"])
    selected = frontier.pop("episodes")
    train_rows = build_training_rows(selected, target_count=args.train_examples)

    before = {
        "selected_train": score_generator(generate, selected),
        "iid": score_generator(generate, suites["iid"]),
        "ood": score_generator(generate, suites["ood"]),
        "adversarial": score_generator(generate, suites["adversarial"]),
    }

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
    accumulation = 4
    optimizer.zero_grad(set_to_none=True)
    model.train()
    for _epoch in range(args.epochs):
        for row_index, row in enumerate(train_rows):
            prompt_text = render_prompt(str(row["prompt"]))
            target_text = str(row["target"])
            full_text = prompt_text + target_text + (tokenizer.eos_token or "")
            prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
            encoded = tokenizer(full_text, return_tensors="pt", truncation=True, max_length=args.max_length)
            labels = encoded["input_ids"].clone()
            labels[:, : min(len(prompt_ids), labels.shape[-1])] = -100
            output = model(**encoded, labels=labels)
            (output.loss / accumulation).backward()
            losses.append(float(output.loss.detach()))
            if (row_index + 1) % accumulation == 0 or row_index + 1 == len(train_rows):
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)

    model.eval()
    after = {
        "selected_train": score_generator(generate, selected),
        "iid": score_generator(generate, suites["iid"]),
        "ood": score_generator(generate, suites["ood"]),
        "adversarial": score_generator(generate, suites["adversarial"]),
    }
    gains = {
        split: round(after[split]["mean"] - before[split]["mean"], 6)
        for split in before
    }
    heldout_positive = any(gains[split] > 0 for split in ("iid", "ood", "adversarial"))
    report = {
        "schema_version": "0.2.0",
        "experiment": "foundry_lora_sft_transfer",
        "model": args.model,
        "distribution": {
            "train_world": "CW-FOUNDRY-TRAIN",
            "iid_world": "CW-FOUNDRY-IID",
            "ood_world": "CW-FOUNDRY-OOD",
            "adversarial_world": "CW-FOUNDRY-ADVERSARIAL",
            "train_candidates": len(suites["train_pool"]),
            "selected_frontier": len(selected),
            "eval_per_split": args.eval_per_split,
        },
        "frontier": frontier,
        "train_examples": len(train_rows),
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "before": before,
        "after": after,
        "absolute_gain": gains,
        "positive_heldout_transfer": heldout_positive,
        "mean_training_loss": round(sum(losses) / len(losses), 6) if losses else None,
        "interpretation": (
            "Verifier-measured held-out capability improved."
            if heldout_positive
            else "Training loss may have changed, but no verifier-measured held-out capability gain was demonstrated."
        ),
        "runtime": {
            "wall_seconds": round(time.time() - started, 3),
            "generation_seconds": round(generation_seconds, 3),
            "generation_calls": generation_calls,
            "device": "cpu",
            "torch_threads": torch.get_num_threads(),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
