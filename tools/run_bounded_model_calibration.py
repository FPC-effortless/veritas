from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded real-LLM CompanyWorld calibration screen")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--max-input-tokens", type=int, default=4096)
    parser.add_argument("--episodes-per-level", type=int, default=2)
    parser.add_argument("--dtype", choices=["float32", "bfloat16"], default="bfloat16")
    parser.add_argument("--trust-remote-code", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    import torch
    import transformers
    from packaging.version import Version
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from investigation_world.calibration.bounded import run_bounded_calibration

    dtype = torch.bfloat16 if args.dtype == "bfloat16" else torch.float32
    started = time.time()
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=args.trust_remote_code)

    # Transformers introduced the generic `dtype=` loading keyword after the
    # Phi-compatible 4.43 release. Preserve compatibility with both API eras
    # without changing benchmark prompts or scoring semantics.
    dtype_kwarg = "torch_dtype" if Version(transformers.__version__) < Version("4.45.0") else "dtype"
    model_kwargs = {
        dtype_kwarg: dtype,
        "low_cpu_mem_usage": True,
        "trust_remote_code": args.trust_remote_code,
    }
    model = AutoModelForCausalLM.from_pretrained(args.model, **model_kwargs)
    model.eval()

    generation_seconds = 0.0
    calls = 0

    def generate(prompt: str) -> str:
        nonlocal generation_seconds, calls
        messages = [
            {"role": "system", "content": "Follow the requested JSON schema exactly. Return JSON only."},
            {"role": "user", "content": prompt},
        ]
        if getattr(tokenizer, "chat_template", None):
            rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            rendered = messages[0]["content"] + "\n\n" + messages[1]["content"]
        encoded = tokenizer(rendered, return_tensors="pt", truncation=True, max_length=args.max_input_tokens)
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
        generated = output[0][encoded["input_ids"].shape[-1]:]
        return tokenizer.decode(generated, skip_special_tokens=True)

    report = run_bounded_calibration(
        generate,
        model_name=args.model,
        episodes_per_level=args.episodes_per_level,
    )
    report["runtime"] = {
        "wall_seconds": round(time.time() - started, 3),
        "generation_seconds": round(generation_seconds, 3),
        "model_calls": calls,
        "device": "cpu",
        "dtype": args.dtype,
        "transformers_version": transformers.__version__,
        "max_new_tokens": args.max_new_tokens,
        "max_input_tokens": args.max_input_tokens,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
