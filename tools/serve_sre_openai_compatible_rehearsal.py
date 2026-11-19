from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from investigation_world.commercial.local_endpoint import (
    RequestBodyTooLarge,
    read_bounded_json_object,
    validate_loopback_host,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Serve a local authenticated OpenAI-compatible endpoint for the Veritas "
            "pilot dress rehearsal"
        )
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--host", default="127.0.0.1", help="literal loopback IP only")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--api-key-env", default="VERITAS_REHEARSAL_API_KEY")
    args = parser.parse_args()
    try:
        args.host = validate_loopback_host(args.host)
    except ValueError as exc:
        parser.error(str(exc))
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    expected_api_key = os.getenv(args.api_key_env)
    if not expected_api_key:
        raise RuntimeError(f"{args.api_key_env} must be configured")

    # Set offline flags before importing model libraries; weights must be pre-staged.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.float32,
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    model.eval()
    generation_lock = threading.Lock()

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    class Handler(BaseHTTPRequestHandler):
        server_version = "VeritasRehearsalEndpoint/1.0"

        def log_message(self, format: str, *values: Any) -> None:  # noqa: A002
            # Never log prompts, headers, or credentials during a private-panel
            # rehearsal.
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
                if self.headers.get_all("Transfer-Encoding"):
                    raise ValueError("transfer-encoded request bodies are unsupported")
                payload = read_bounded_json_object(
                    self.rfile,
                    self.headers.get_all("Content-Length"),
                )
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
            except RequestBodyTooLarge as exc:
                self._json(
                    413,
                    {"error": "request_too_large", "detail": str(exc)[:200]},
                )
                return
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": "bad_request", "detail": str(exc)[:200]})
                return
            except Exception as exc:  # pragma: no cover - defensive endpoint boundary
                self._json(
                    500,
                    {"error": "generation_failed", "detail": type(exc).__name__},
                )
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

    address = ipaddress.ip_address(args.host)
    server_type = ThreadingHTTPServer
    bind_address = (args.host, args.port)
    if address.version == 6:
        class IPv6ThreadingHTTPServer(ThreadingHTTPServer):
            address_family = socket.AF_INET6

        server_type = IPv6ThreadingHTTPServer
        bind_address = (args.host, args.port, 0, 0)
    server = server_type(bind_address, Handler)
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
