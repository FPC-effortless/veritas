from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

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
    parser = argparse.ArgumentParser(description="Evaluate an OpenAI-compatible model endpoint on a frozen Veritas SRE private panel")
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="sre-commercial-v1")
    parser.add_argument("--providers", nargs="+", required=True)
    parser.add_argument("--expected-candidate-id")
    parser.add_argument("--early-updates", type=int, default=2)
    parser.add_argument("--api-key-env", default="VERITAS_MODEL_API_KEY")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-new-tokens", type=int, default=48)
    args = parser.parse_args()

    unknown = sorted(set(args.providers) - set(STATUSPAGE_INCIDENT_ENDPOINTS))
    if unknown:
        raise ValueError(f"unknown SRE providers: {unknown}")

    candidate, cases = _load_cases(args.snapshot_dir, args.providers, args.version, args.early_updates)
    if args.expected_candidate_id and candidate.candidate_id != args.expected_candidate_id:
        raise RuntimeError(
            f"candidate mismatch: expected {args.expected_candidate_id}, got {candidate.candidate_id}"
        )

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
        "request_seconds": round(request_seconds, 3),
        "model_calls": calls,
        "transport": "openai-compatible-http",
        "endpoint_host": urlparse(args.endpoint).netloc,
        "generation": "temperature-0",
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
