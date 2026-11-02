"""Public-only LM checkpoint evaluator; no TRAIN-001 qualification authority.

This executable recomputes metrics from checkpoint bytes and explicit public
splits. It never consumes trainer scores, accesses sealed panels or attests
execution. It requires the optional TrainLab model-training installation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import time
from pathlib import Path


def evaluate_checkpoint(
    checkpoint,
    tokenizer,
    release_dir,
    release_sha256,
    *,
    split="validation",
    text_token_budget=4096,
    generation_limit=8,
):
    # The public evaluator is an optional TrainLab integration, not a core dependency.
    # Load its installed providers at runtime so a base Veritas install stays usable.
    torch = importlib.import_module("torch")
    F = importlib.import_module("torch.nn.functional")
    LanguageRelease = importlib.import_module("forge_data.language").LanguageRelease
    create_model = importlib.import_module("trainlab.fullcycle.backends").create_model
    inference = importlib.import_module("trainlab.fullcycle.inference")
    inference_benchmark, reply = inference.inference_benchmark, inference.reply
    Tokens = importlib.import_module("trainlab.fullcycle.tokenization").Tokens
    training = importlib.import_module("trainlab.fullcycle.training")
    checkpoint_load, task_reward = training.checkpoint_load, training.task_reward
    digest = importlib.import_module("trainlab.runner").digest

    if split not in ("validation", "test"):
        raise ValueError("evaluator requires explicit public held-out split")
    started = time.perf_counter()
    release = LanguageRelease(release_dir, release_sha256)
    tokens = Tokens(tokenizer)
    saved = checkpoint_load(checkpoint)
    model = create_model(saved["model_config"]).eval()
    model.load_state_dict(saved["model"])
    nll, count, byte_count, instruction_nll, instruction_tokens = 0.0, 0, 0, 0.0, 0
    chats, tasks, preferences = [], [], []
    with torch.no_grad():
        for row in release.iter_rows(split, "text"):
            ids = tokens.encode(row["text"]) + [tokens.eos]
            for start in range(0, len(ids) - 1, model.config.context):
                if count >= text_token_budget:
                    break
                segment = ids[
                    start : start + min(model.config.context, text_token_budget - count) + 1
                ]
                if len(segment) < 2:
                    continue
                x, y = torch.tensor([segment[:-1]]), torch.tensor([segment[1:]])
                nll += F.cross_entropy(
                    model(x).float().flatten(0, 1), y.flatten(), reduction="sum"
                ).item()
                count += y.numel()
                byte_count += len(tokens.decode(segment[1:]).encode("utf-8"))
            if count >= text_token_budget:
                break
        for row in release.iter_rows(split, "conversation"):
            ids, mask = tokens.conversation(row["messages"])
            if len(ids) > model.config.context + 1:
                raise ValueError("held-out conversation exceeds context")
            x, y = torch.tensor([ids[:-1]]), torch.tensor([ids[1:]])
            selected = torch.tensor([mask[1:]])
            loss = F.cross_entropy(
                model(x).float().flatten(0, 1), y.flatten(), reduction="none"
            ).reshape_as(y)
            instruction_nll += (loss * selected).sum().item()
            instruction_tokens += selected.sum().item()
            if len(chats) < generation_limit:
                messages = row["messages"]
                target = messages[-1]["content"] if messages[-1]["role"] == "assistant" else None
                if target is not None:
                    actual = reply(model, tokens, messages[:-1], max_new_tokens=48)
                    chats.append(
                        {
                            "group": row["group"],
                            "actual": actual,
                            "expected": target,
                            "exact_match": actual.strip() == target.strip(),
                        }
                    )
        choices = [tokens.encode(s) for s in ("0", "1")]
        for row in release.iter_rows(split, "task"):
            if any(len(x) != 1 for x in choices):
                raise ValueError("comparison choices must be single symbols")
            ids, _ = tokens.conversation([{"role": "user", "content": row["prompt"]}], prompt=True)
            if len(ids) > model.config.context:
                raise ValueError("evaluation task exceeds context")
            logits = model(torch.tensor([ids]))[0, -1, [x[0] for x in choices]]
            action = str(int(logits.argmax()))
            tasks.append(
                {"group": row["group"], "action": action, "score": task_reward(row, action)}
            )
        for row in release.iter_rows(split, "preference"):
            scores = []
            for answer in (row["chosen"], row["rejected"]):
                ids, mask = tokens.preference(row["prompt"], answer)
                if len(ids) > model.config.context + 1:
                    raise ValueError("held-out preference exceeds context")
                x, y = torch.tensor([ids[:-1]]), torch.tensor([ids[1:]])
                logp = F.log_softmax(model(x).float(), -1).gather(-1, y[..., None]).squeeze(-1)
                scores.append((logp * torch.tensor([mask[1:]])).sum().item())
            preferences.append(
                {
                    "group": row["group"],
                    "chosen_logp": scores[0],
                    "rejected_logp": scores[1],
                    "correct": scores[0] > scores[1],
                }
            )
    loss = nll / count if count else None
    report = {
        "schema": "veritas.public-lm-evaluation.v1",
        "split": split,
        "checkpoint_sha256": digest(checkpoint),
        "tokenizer_sha256": digest(tokenizer),
        "dataset_manifest_sha256": release_sha256,
        "evaluator_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "language": {
            "loss": loss,
            "perplexity": math.exp(loss) if loss is not None else None,
            "bits_per_decoded_utf8_byte": nll / (math.log(2) * byte_count) if byte_count else None,
            "tokens": count,
            "decoded_utf8_bytes": byte_count,
            "scope": "first deterministic held-out token budget; tokenizers may differ",
        },
        "instruction": {
            "assistant_loss": instruction_nll / instruction_tokens if instruction_tokens else None,
            "target_tokens": instruction_tokens,
            "generation_exact_match": sum(r["exact_match"] for r in chats) / len(chats)
            if chats
            else None,
            "generated_cases": len(chats),
        },
        "decision": {
            "accuracy": sum(r["score"] for r in tasks) / len(tasks) if tasks else None,
            "cases": len(tasks),
            "action_space": ["0", "1"],
            "scope": "constructed integer comparison, constrained one-token choice",
        },
        "preference": {
            "accuracy": sum(r["correct"] for r in preferences) / len(preferences)
            if preferences
            else None,
            "cases": len(preferences),
        },
        "inference": inference_benchmark(model, tokens),
        "public_outcomes": {"chat": chats, "decision": tasks, "preference": preferences},
        "evaluation_seconds": time.perf_counter() - started,
        "execution_attestation": "UNKNOWN",
        "qualification": "NOT_QUALIFIED",
        "training_validated": False,
        "coverage": {
            "reasoning": "bounded constructed integer comparison only",
            "coding": "NOT_EVALUATED",
            "agentic_tool_execution": "NOT_EVALUATED",
            "general_instruction_benchmarks": "NOT_EVALUATED",
        },
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--release-sha256", required=True)
    parser.add_argument("--split", choices=["validation", "test"], default="validation")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--text-token-budget", type=int, default=4096)
    args = parser.parse_args()
    importlib.import_module("torch").set_num_threads(2)
    result = evaluate_checkpoint(
        args.checkpoint,
        args.tokenizer,
        args.release,
        args.release_sha256,
        split=args.split,
        text_token_budget=args.text_token_budget,
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "split",
                    "language",
                    "instruction",
                    "decision",
                    "preference",
                    "qualification",
                )
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
