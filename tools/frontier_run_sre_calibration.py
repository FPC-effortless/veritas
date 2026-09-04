from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from investigation_world.commercial.sre_evaluation import (  # noqa: E402
    evaluate_sre_generator,
    sanitize_sre_evaluation,
)
from investigation_world.commercial.sre_release import load_sealed_sre_release  # noqa: E402
from investigation_world.frontier.models import stable_content_hash  # noqa: E402
from investigation_world.frontier.sre_runner import (  # noqa: E402
    build_gemini_generate_content_body,
    build_openai_compatible_body,
    classification_stage_prompt,
    evidence_stage_prompt,
    extract_gemini_text,
    extract_openai_compatible_text,
    observation_from_sre_report,
)


DIRECT_SYSTEM = "Return only the requested JSON classification."
EVIDENCE_SYSTEM = (
    "Extract only decision-relevant evidence from the supplied early incident record. "
    "Do not provide a final causal class and do not invent later resolution evidence."
)


class ModelTransport:
    def __init__(
        self,
        *,
        kind: str,
        model: str,
        endpoint: str | None,
        api_key: str | None,
        timeout: float,
        max_output_tokens: int,
    ) -> None:
        self.kind = kind
        self.model = model
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.calls = 0
        self.request_seconds = 0.0

        if kind == "gemini":
            escaped_model = urllib.parse.quote(model, safe="-._")
            self.endpoint = endpoint or (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{escaped_model}:generateContent"
            )
            if not api_key:
                raise RuntimeError("Gemini transport requires an API key")
            self.headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            }
        elif kind == "openai-compatible":
            if not endpoint:
                raise RuntimeError("--endpoint is required for openai-compatible transport")
            self.endpoint = endpoint
            self.headers = {"Content-Type": "application/json"}
            if api_key:
                self.headers["Authorization"] = f"Bearer {api_key}"
        else:
            raise ValueError(f"unsupported transport: {kind}")

    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str,
        json_output: bool,
        max_output_tokens: int | None = None,
    ) -> str:
        limit = max_output_tokens or self.max_output_tokens
        if self.kind == "gemini":
            body = build_gemini_generate_content_body(
                prompt,
                system_instruction=system_instruction,
                max_output_tokens=limit,
                json_output=json_output,
            )
        else:
            body = build_openai_compatible_body(
                prompt,
                model=self.model,
                system_instruction=system_instruction,
                max_output_tokens=limit,
            )

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers=self.headers,
            method="POST",
        )
        tick = time.time()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(
                f"{self.kind} endpoint returned HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{self.kind} endpoint request failed: {exc.reason}") from exc
        finally:
            self.request_seconds += time.time() - tick
        self.calls += 1

        if self.kind == "gemini":
            return extract_gemini_text(payload)
        return extract_openai_compatible_text(payload)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen SRE private panel through a zero-capital-compatible "
            "Frontier calibration transport"
        )
    )
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument(
        "--transport",
        choices=("gemini", "openai-compatible"),
        required=True,
    )
    parser.add_argument("--endpoint")
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--model-snapshot",
        required=True,
        help=(
            "immutable provider snapshot/version when available; if a provider exposes "
            "only a moving alias, record that alias explicitly and do not overclaim immutability"
        ),
    )
    parser.add_argument(
        "--tier",
        required=True,
        choices=("weak", "medium", "strong", "frontier"),
        help="must be declared before inspecting this run's score",
    )
    parser.add_argument(
        "--harness",
        choices=("direct-json", "evidence-two-stage"),
        default="direct-json",
    )
    parser.add_argument("--comparison-group-id")
    parser.add_argument("--api-key-env")
    parser.add_argument(
        "--allow-external-private-data",
        action="store_true",
        help=(
            "explicit opt-in required before the sealed private SRE panel may be sent "
            "to a non-local endpoint; do not use this merely to obtain a free API tier"
        ),
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-output-tokens", type=int, default=64)
    parser.add_argument("--evidence-output-tokens", type=int, default=256)
    parser.add_argument("--output", type=Path, required=True, help="private operator report")
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--observation-output", type=Path, required=True)

    parser.add_argument("--expected-candidate-id")
    parser.add_argument("--expected-evidence-manifest-id")
    parser.add_argument("--expected-report-id")
    parser.add_argument("--expected-panel-id")
    parser.add_argument("--expected-private-release-manifest-id")
    args = parser.parse_args()

    if args.transport == "gemini":
        endpoint_for_policy = args.endpoint or "https://generativelanguage.googleapis.com"
        endpoint_is_local = False
    else:
        endpoint_for_policy = args.endpoint or ""
        host = (urlparse(endpoint_for_policy).hostname or "").casefold()
        endpoint_is_local = host in {"localhost", "127.0.0.1", "::1"}

    if not endpoint_is_local and not args.allow_external_private_data:
        raise RuntimeError(
            "Refusing to send the sealed private SRE panel to an external endpoint by default. "
            "Use a local/private open-weight endpoint for the zero-capital track. "
            "Only pass --allow-external-private-data after independently verifying the "
            "provider/account data-use terms and intentionally accepting that disclosure."
        )

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

    env_name = args.api_key_env or (
        "GEMINI_API_KEY" if args.transport == "gemini" else "VERITAS_MODEL_API_KEY"
    )
    transport = ModelTransport(
        kind=args.transport,
        model=args.model,
        endpoint=args.endpoint,
        api_key=os.getenv(env_name),
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
    )

    started = time.time()

    def generate(prompt: str) -> str:
        if args.harness == "direct-json":
            return transport.generate(
                prompt,
                system_instruction=DIRECT_SYSTEM,
                json_output=True,
            )
        normalized = transport.generate(
            evidence_stage_prompt(prompt),
            system_instruction=EVIDENCE_SYSTEM,
            json_output=False,
            max_output_tokens=args.evidence_output_tokens,
        )
        return transport.generate(
            classification_stage_prompt(prompt, normalized),
            system_instruction=DIRECT_SYSTEM,
            json_output=True,
        )

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
            f"model evaluation case-count mismatch: expected {sealed_private_count}, "
            f"got {report['private_cases']}"
        )

    report["evaluation_panel_fingerprint"] = report["panel_id"]
    report["panel_id"] = qualification.panel_id
    report["evidence_manifest_id"] = candidate.evidence_manifest.manifest_id
    report["qualification_report_id"] = qualification.report_id
    report["private_release_manifest_id"] = release.private_release_manifest.manifest_id
    report["providers"] = sorted({case.provider for case in release.cases})
    report["runtime"] = {
        "wall_seconds": round(time.time() - started, 3),
        "request_seconds": round(transport.request_seconds, 3),
        "model_calls": transport.calls,
        "transport": args.transport,
        "endpoint_host": urlparse(transport.endpoint).netloc,
        "generation": args.harness,
        "api_key_env": env_name,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    public_report = sanitize_sre_evaluation(report)
    args.public_output.parent.mkdir(parents=True, exist_ok=True)
    args.public_output.write_text(
        json.dumps(public_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    comparison_group_id = args.comparison_group_id or (
        "FRCMPGRP-"
        + stable_content_hash(
            {
                "candidate_id": candidate.candidate_id,
                "panel_id": qualification.panel_id,
                "model_identity": args.model,
                "model_snapshot": args.model_snapshot,
            }
        )[:24].upper()
    )
    observation = observation_from_sre_report(
        report,
        tier=args.tier,
        model_snapshot=args.model_snapshot,
        harness_identity=f"sre-{args.harness}-v1:{args.transport}",
        comparison_group_id=comparison_group_id,
        input_artifact_hash=hashlib.sha256(args.qualification.read_bytes()).hexdigest(),
        configuration={
            "zero_capital_track": True,
            "private_data_egress": not endpoint_is_local,
            "external_private_data_explicitly_allowed": args.allow_external_private_data,
            "api_key_env": env_name,
            "endpoint_host": urlparse(transport.endpoint).netloc,
        },
    )
    args.observation_output.parent.mkdir(parents=True, exist_ok=True)
    args.observation_output.write_text(
        json.dumps(observation.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "model": report["model"],
                "model_snapshot": args.model_snapshot,
                "tier": args.tier,
                "harness": args.harness,
                "candidate_id": report["candidate_id"],
                "panel_id": report["panel_id"],
                "private_cases": report["private_cases"],
                "accuracy": report["accuracy"],
                "ci95_low": report["ci95_low"],
                "ci95_high": report["ci95_high"],
                "parse_failures": report["parse_failures"],
                "model_calls": transport.calls,
                "observation_id": observation.observation_id,
                "comparison_group_id": comparison_group_id,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
