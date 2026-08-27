from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from investigation_world.commercial.sre_evaluation import (
    evaluate_sre_generator,
    sanitize_sre_evaluation,
)
from investigation_world.commercial.sre_release import load_sealed_sre_release


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate an OpenAI-compatible endpoint on an exact sealed Veritas SRE private panel"
    )
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True, help="private operator report including per-case rows")
    parser.add_argument("--public-output", type=Path, help="optional aggregate-only report safe for artifacts/buyers")
    parser.add_argument("--expected-candidate-id")
    parser.add_argument("--expected-evidence-manifest-id")
    parser.add_argument("--expected-report-id")
    parser.add_argument("--expected-panel-id")
    parser.add_argument("--expected-private-release-manifest-id")
    parser.add_argument("--api-key-env", default="VERITAS_MODEL_API_KEY")
    parser.add_argument("--timeout", type=float, default=120.0)
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

    api_key = os.getenv(args.api_key_env)
    request_seconds = 0.0
    calls = 0
    started = time.time()

    def generate(prompt: str) -> str:
        nonlocal request_seconds, calls
        body = {
            "model": args.model,
            "messages": [
                {"role": "system", "content": "Return only the requested JSON classification."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": args.max_new_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            args.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        tick = time.time()
        try:
            with urllib.request.urlopen(request, timeout=args.timeout) as response:  # nosec B310
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"model endpoint returned HTTP {exc.code}: {detail}") from exc
        request_seconds += time.time() - tick
        calls += 1
        try:
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("model endpoint is not OpenAI chat-completions compatible") from exc

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
    # Preserve a scenario-only execution fingerprint while publishing the qualification protocol's
    # sealed QPANEL identifier as the authoritative panel identity.
    report["evaluation_panel_fingerprint"] = report["panel_id"]
    report["panel_id"] = qualification.panel_id

    report["evidence_manifest_id"] = candidate.evidence_manifest.manifest_id
    report["qualification_report_id"] = qualification.report_id
    report["private_release_manifest_id"] = release.private_release_manifest.manifest_id
    report["providers"] = sorted({case.provider for case in release.cases})
    report["runtime"] = {
        "wall_seconds": round(time.time() - started, 3),
        "request_seconds": round(request_seconds, 3),
        "model_calls": calls,
        "transport": "openai-compatible-http",
        "endpoint_host": urlparse(args.endpoint).netloc,
        "generation": "temperature-0",
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
