from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CompanyWorld calibration against an OpenAI-compatible endpoint")
    parser.add_argument("--endpoint", required=True, help="Full /v1/chat/completions-compatible URL")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api-key-env", default="VERITAS_MODEL_API_KEY")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-new-tokens", type=int, default=320)
    args = parser.parse_args()

    from investigation_world.calibration import run_full_context_calibration

    api_key = os.getenv(args.api_key_env)
    endpoint = args.endpoint
    started = time.time()
    request_seconds = 0.0
    calls = 0

    def generate(prompt: str) -> str:
        nonlocal request_seconds, calls
        payload = {
            "model": args.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Follow the requested JSON schema exactly. Return JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": args.max_new_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        tick = time.time()
        try:
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"model endpoint returned HTTP {exc.code}: {detail}") from exc
        request_seconds += time.time() - tick
        calls += 1
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("model endpoint response is not OpenAI chat-completions compatible") from exc
        return str(content)

    report = run_full_context_calibration(generate, model_name=args.model)
    report["runtime"] = {
        "wall_seconds": round(time.time() - started, 3),
        "request_seconds": round(request_seconds, 3),
        "model_calls": calls,
        "transport": "openai-compatible-http",
        "endpoint_host": urlparse(endpoint).netloc,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
