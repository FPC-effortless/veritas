from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve a local authenticated OpenAI-compatible endpoint for the Veritas pilot dress rehearsal"
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--api-key-env", default="VERITAS_REHEARSAL_API_KEY")
    args = parser.parse_args()

    expected_api_key = os.getenv(args.api_key_env)
    if not expected_api_key:
        raise RuntimeError(f"{args.api_key_env} must be configured")

    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.float32,
        low_cpu_mem_usage=True,
    )
    model.eval()
    generation_lock = threading.Lock()

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    class Handler(BaseHTTPRequestHandler):
        server_version = "VeritasRehearsalEndpoint/1.0"

        def log_message(self, format: str, *values: Any) -> None:  # noqa: A002
            # Never log prompts, headers, or credentials during a private-panel rehearsal.
            return

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/healthz":
                self._json(404, {"error": "not_found"})
                return
            self._json(200, {"status": "ok", "model": args.model})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/chat/completions":
                self._json(404, {"error": "not_found"})
                return
            if self.headers.get("Authorization") != f"Bearer {expected_api_key}":
                self._json(401, {"error": "unauthorized"})
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                messages = payload["messages"]
                if not isinstance(messages, list) or not messages:
                    raise ValueError("messages must be a non-empty list")
                max_tokens = int(payload.get("max_tokens", 48))
                if max_tokens <= 0 or max_tokens > 256:
                    raise ValueError("max_tokens out of rehearsal bounds")

                rendered = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
                inputs = tokenizer(rendered, return_tensors="pt")
                with generation_lock, torch.inference_mode():
                    output = model.generate(
                        **inputs,
                        max_new_tokens=max_tokens,
                        do_sample=False,
                        pad_token_id=tokenizer.pad_token_id,
                    )
                prompt_tokens = int(inputs["input_ids"].shape[1])
                generated = output[0][prompt_tokens:]
                content = tokenizer.decode(generated, skip_special_tokens=True).strip()
                completion_tokens = int(generated.shape[0])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": "bad_request", "detail": str(exc)[:200]})
                return
            except Exception as exc:  # pragma: no cover - defensive endpoint boundary
                self._json(500, {"error": "generation_failed", "detail": type(exc).__name__})
                return

            self._json(
                200,
                {
                    "id": f"veritas-rehearsal-{time.time_ns()}",
                    "object": "chat.completion",
                    "model": args.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    },
                },
            )

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        json.dumps(
            {
                "status": "ready",
                "host": args.host,
                "port": args.port,
                "model": args.model,
                "authentication": "bearer-required",
            },
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
