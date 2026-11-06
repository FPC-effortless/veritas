from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from investigation_world.commercial.sre_evaluation import (
    evaluate_sre_generator,
    sanitize_sre_evaluation,
)
from investigation_world.commercial.sre_release import load_sealed_sre_release


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate a local Hugging Face model on an exact sealed Veritas SRE private panel"
    )
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True, help="private operator report including per-case rows")
    parser.add_argument("--public-output", type=Path, help="optional aggregate-only report safe for artifacts/buyers")
    parser.add_argument("--expected-candidate-id")
    parser.add_argument("--expected-evidence-manifest-id")
    parser.add_argument("--expected-report-id")
    parser.add_argument("--expected-panel-id")
    parser.add_argument("--expected-private-release-manifest-id")
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--max-new-tokens", type=int, default=48)
    args = parser.parse_args()

    release = load_sealed_sre_release(
        args.qualification,
        expected_candidate_id=args.expected_candidate_id,
        expected_evidence_manifest_id=args.expected_evidence_manifest_id,
        expected_report_id=args.expected_report_id,
        expected_panel_id=args.expected_panel_id,
        expected_private_release_manifest_id=args.expected_private_release_manifest_id,
    )
    candidate = release.candidate
    qualification = release.qualification

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

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
        release.cases,
        generate,
        model_name=args.model,
        candidate_id=candidate.candidate_id,
        benchmark_version=candidate.version,
    )
    sealed_private_count = len(release.private_release_manifest.private_test_scenario_ids)
    if report["private_cases"] != sealed_private_count:
        raise RuntimeError(
            f"model evaluation case-count mismatch: expected {sealed_private_count}, got {report['private_cases']}"
        )
    # The evaluator's scenario-only digest remains useful as an execution fingerprint, but the
    # authoritative panel identity is the qualification protocol's sealed QPANEL identifier.
    report["evaluation_panel_fingerprint"] = report["panel_id"]
    report["panel_id"] = qualification.panel_id

    report["evidence_manifest_id"] = candidate.evidence_manifest.manifest_id
    report["qualification_report_id"] = qualification.report_id
    report["private_release_manifest_id"] = release.private_release_manifest.manifest_id
    report["providers"] = sorted({case.provider for case in release.cases})
    report["runtime"] = {
        "wall_seconds": round(time.time() - started, 3),
        "device": "cpu",
        "torch_threads": torch.get_num_threads(),
        "generation": "deterministic_greedy",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if args.public_output:
        public_report = sanitize_sre_evaluation(report)
        args.public_output.parent.mkdir(parents=True, exist_ok=True)
        args.public_output.write_text(json.dumps(public_report, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "model": report["model"],
        "candidate_id": report["candidate_id"],
        "panel_id": report["panel_id"],
        "evidence_manifest_id": report["evidence_manifest_id"],
        "qualification_report_id": report["qualification_report_id"],
        "private_release_manifest_id": report["private_release_manifest_id"],
        "private_cases": report["private_cases"],
        "accuracy": report["accuracy"],
        "balanced_accuracy": report["balanced_accuracy"],
        "macro_f1": report["macro_f1"],
        "majority_baseline_accuracy": report["majority_baseline_accuracy"],
        "accuracy_lift_over_majority": report["accuracy_lift_over_majority"],
        "ci95_low": report["ci95_low"],
        "ci95_high": report["ci95_high"],
        "parse_failures": report["parse_failures"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
