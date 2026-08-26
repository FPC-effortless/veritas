from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from investigation_world.commercial.sre_evaluation import evaluate_sre_generator
from investigation_world.qualification import (
    STATUSPAGE_INCIDENT_ENDPOINTS,
    compile_sre_candidate,
    parse_statuspage_incidents,
)
from investigation_world.qualification.cluster_split import repartition_candidate_by_near_duplicates


def _load_cases(snapshot_dir: Path, providers: list[str], version: str, early_updates: int):
    incidents = []
    for provider in providers:
        path = snapshot_dir / f"{provider}-incidents.json"
        if not path.exists():
            raise FileNotFoundError(f"missing frozen SRE snapshot: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        incidents.extend(
            parse_statuspage_incidents(
                provider,
                payload,
                endpoint=STATUSPAGE_INCIDENT_ENDPOINTS[provider],
                early_update_count=early_updates,
            )
        )
    candidate, cases = compile_sre_candidate(incidents, version=version)
    candidate, split_map = repartition_candidate_by_near_duplicates(candidate)
    cases = [
        case.model_copy(
            update={
                "scenario": case.scenario.model_copy(
                    update={"split": split_map[case.scenario.scenario_id]}
                )
            }
        )
        for case in cases
    ]
    return candidate, cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a local Hugging Face model on a frozen Veritas SRE private panel")
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="sre-commercial-v1")
    parser.add_argument("--providers", nargs="+", required=True)
    parser.add_argument("--expected-candidate-id")
    parser.add_argument("--early-updates", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--max-new-tokens", type=int, default=48)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    unknown = sorted(set(args.providers) - set(STATUSPAGE_INCIDENT_ENDPOINTS))
    if unknown:
        raise ValueError(f"unknown SRE providers: {unknown}")

    candidate, cases = _load_cases(args.snapshot_dir, args.providers, args.version, args.early_updates)
    if args.expected_candidate_id and candidate.candidate_id != args.expected_candidate_id:
        raise RuntimeError(
            f"candidate mismatch: expected {args.expected_candidate_id}, got {candidate.candidate_id}"
        )

    started = time.time()
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float32, low_cpu_mem_usage=True)
    model.eval()
    torch.set_num_threads(min(4, max(1, torch.get_num_threads())))

    def generate(prompt: str) -> str:
        messages = [
            {"role": "system", "content": "Return only the requested JSON classification."},
            {"role": "user", "content": prompt},
        ]
        if getattr(tokenizer, "chat_template", None):
            rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            rendered = messages[0]["content"] + "\n\n" + messages[1]["content"]
        encoded = tokenizer(rendered, return_tensors="pt", truncation=True, max_length=args.max_length)
        with torch.inference_mode():
            output = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        generated = output[0][encoded["input_ids"].shape[-1] :]
        return tokenizer.decode(generated, skip_special_tokens=True)

    report = evaluate_sre_generator(
        cases,
        generate,
        model_name=args.model,
        candidate_id=candidate.candidate_id,
        benchmark_version=args.version,
    )
    report["evidence_manifest_id"] = candidate.evidence_manifest.manifest_id
    report["providers"] = args.providers
    report["runtime"] = {
        "wall_seconds": round(time.time() - started, 3),
        "device": "cpu",
        "torch_threads": torch.get_num_threads(),
        "generation": "deterministic_greedy",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "model": report["model"],
        "candidate_id": report["candidate_id"],
        "panel_id": report["panel_id"],
        "private_cases": report["private_cases"],
        "accuracy": report["accuracy"],
        "ci95_low": report["ci95_low"],
        "ci95_high": report["ci95_high"],
        "parse_failures": report["parse_failures"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
