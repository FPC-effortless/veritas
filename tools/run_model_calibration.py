from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real LLM against the fixed CompanyWorld calibration slice")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=320)
    parser.add_argument("--max-input-tokens", type=int, default=7168)
    parser.add_argument("--dtype", choices=("float32", "bfloat16", "float16"), default="float32")
    parser.add_argument("--trust-remote-code", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from investigation_world.calibration import run_full_context_calibration

    dtype = {
        "float32": torch.float32,
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
    }[args.dtype]

    started = time.time()
    tokenizer = AutoTokenizer.from_pretrained(
        args.model,
        trust_remote_code=args.trust_remote_code,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        dtype=dtype,
        low_cpu_mem_usage=True,
        trust_remote_code=args.trust_remote_code,
    )
    model.eval()

    generation_seconds = 0.0
    calls = 0

    def generate(prompt: str) -> str:
        nonlocal generation_seconds, calls
        messages = [
            {
                "role": "system",
                "content": "Follow the requested JSON schema exactly. Return JSON only.",
            },
            {"role": "user", "content": prompt},
        ]
        if getattr(tokenizer, "chat_template", None):
            rendered = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            rendered = messages[0]["content"] + "\n\n" + messages[1]["content"]
        encoded = tokenizer(
            rendered,
            return_tensors="pt",
            truncation=True,
            max_length=args.max_input_tokens,
        )
        tick = time.time()
        with torch.inference_mode():
            output = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        generation_seconds += time.time() - tick
        calls += 1
        generated = output[0][encoded["input_ids"].shape[-1] :]
        return tokenizer.decode(generated, skip_special_tokens=True)

    report = run_full_context_calibration(generate, model_name=args.model)
    report["runtime"] = {
        "wall_seconds": round(time.time() - started, 3),
        "generation_seconds": round(generation_seconds, 3),
        "model_calls": calls,
        "device": "cpu",
        "torch_threads": torch.get_num_threads(),
        "dtype": args.dtype,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
