"""Hash-verified export, isolated incremental inference and localhost chat."""

from __future__ import annotations

import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import torch

from trainlab.runner import LabError, contained_file, digest, read_json, write_json

from .backends import create_model
from .tokenization import Tokens
from .training import checkpoint_load


def export_model(checkpoint, tokenizer, destination):
    import shutil
    import tempfile

    final_destination = Path(destination)
    if final_destination.exists():
        raise LabError("model export destination already exists")
    destination = Path(tempfile.mkdtemp(prefix=".model-export-", dir=final_destination.parent))
    try:
        saved = checkpoint_load(checkpoint)
        torch.save(saved["model"], destination / "weights.pt")
        shutil.copyfile(tokenizer, destination / "tokenizer.json")
        write_json(destination / "config.json", saved["model_config"])
        write_json(
            destination / "chat-template.json",
            {
                "schema": "trainlab.chat.v1",
                "roles": ["system", "user", "assistant", "tool"],
                "serialization": "BOS + (role-token + content + END)* + assistant-token",
                "session_isolation": "fresh prefill for each request; local incremental state only",
                "tool_execution": "disabled",
            },
        )
        write_json(
            destination / "manifest.json",
            {
                "schema": "trainlab.model.v1",
                "checkpoint_sha256": digest(checkpoint),
                "files": {
                    name: digest(destination / name)
                    for name in (
                        "weights.pt",
                        "tokenizer.json",
                        "config.json",
                        "chat-template.json",
                    )
                },
                "qualification": "NOT_QUALIFIED",
            },
        )
        destination.rename(final_destination)
        return digest(final_destination / "manifest.json")
    finally:
        if destination.exists():
            shutil.rmtree(destination)


def load_bundle(directory, *, device="cpu", expected_sha256=None):
    directory = Path(directory)
    manifest_path = contained_file(directory, "manifest.json")
    if expected_sha256 and digest(manifest_path) != expected_sha256:
        raise LabError("model registry manifest pin mismatch")
    manifest = read_json(manifest_path)
    if manifest.get("schema") != "trainlab.model.v1" or set(manifest["files"]) != {
        "weights.pt",
        "tokenizer.json",
        "config.json",
        "chat-template.json",
    }:
        raise LabError("invalid model export contract")
    for name, sha in manifest["files"].items():
        if digest(contained_file(directory, name)) != sha:
            raise LabError("exported model artifact hash mismatch")
    model = create_model(read_json(directory / "config.json")).to(device).eval()
    model.load_state_dict(
        torch.load(directory / "weights.pt", map_location=device, weights_only=True)
    )
    tokens = Tokens(directory / "tokenizer.json")
    if tokens.vocab_size != model.config.vocab_size:
        raise LabError("export tokenizer/model mismatch")
    return model, tokens


@torch.no_grad()
def stream_reply(model, tokens, messages, *, max_new_tokens=64, temperature=0.0, seed=7):
    if not messages or len(messages) > 100 or not 1 <= max_new_tokens <= 1024:
        raise LabError("bounded nonempty messages and generation required")
    history = list(messages)
    ids, _ = tokens.conversation(history, prompt=True)
    while len(ids) + max_new_tokens > model.config.context and len(history) > 1:
        history.pop(0)
        ids, _ = tokens.conversation(history, prompt=True)
    if len(ids) + max_new_tokens > model.config.context:
        raise LabError("prompt + generation exceeds model context")
    device = next(model.parameters()).device
    generator = torch.Generator(device=device).manual_seed(seed)
    x = torch.tensor([ids], dtype=torch.long, device=device)
    logits, state = model.step(x)
    for _ in range(max_new_tokens):
        scores = logits[0, -1].float().clone()
        scores[list(set(tokens.special.values()) - {tokens.end, tokens.eos})] = -torch.inf
        token = (
            int(scores.argmax())
            if temperature == 0
            else int(
                torch.multinomial(torch.softmax(scores / temperature, -1), 1, generator=generator)
            )
        )
        if token in (tokens.end, tokens.eos):
            break
        yield token
        logits, state = model.step(torch.tensor([[token]], device=device), state)


def reply(model, tokens, messages, **kwargs):
    return tokens.decode(list(stream_reply(model, tokens, messages, **kwargs)))


def inference_benchmark(model, tokens):
    device = next(model.parameters()).device
    x = torch.tensor([[tokens.bos] + tokens.encode("The model reads text.")], device=device)
    n = min(16, model.config.context - x.shape[1])

    def sync():
        if device.type == "cuda":
            torch.cuda.synchronize(device)

    with torch.no_grad():
        model.step(x)  # warmup excluded
        sync()
        start = time.perf_counter()
        logits, state = model.step(x)
        sync()
        prefill = time.perf_counter() - start
        start = time.perf_counter()
        for _ in range(n):
            logits, state = model.step(logits[:, -1].argmax(-1, keepdim=True), state)
        sync()
        decode = time.perf_counter() - start
    if hasattr(state, "tensor_bytes"):
        state_bytes = state.tensor_bytes()
    else:
        state_bytes = sum(t.numel() * t.element_size() for pair in state for t in pair)
    return {
        "prefill_tokens": x.numel(),
        "prefill_seconds": prefill,
        "prefill_tokens_per_second": x.numel() / prefill,
        "decode_tokens": n,
        "decode_seconds": decode,
        "decode_tokens_per_second": n / decode,
        "decode_milliseconds_per_token": 1000 * decode / n,
        "state_bytes_after_decode": state_bytes,
        "replicates": 1,
        "device": str(device),
        "hardware": torch.cuda.get_device_name(device) if device.type == "cuda" else "CPU",
        "measurement_scope": "local warmed single-sequence wall time; no statistical claim",
    }


def serve_chat(bundle, *, port=8787, device="cpu"):
    model, tokens = load_bundle(bundle, device=device)
    lock, secret = threading.Lock(), secrets.token_urlsafe(24)
    html = (
        Path(__file__).with_name("chat.html").read_text().replace("CSRF_TOKEN_PLACEHOLDER", secret)
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path != "/":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(html.encode())

        def do_POST(self):
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if (
                self.path != "/chat"
                or host != f"127.0.0.1:{self.server.server_port}"
                or (origin and urlparse(origin).netloc != host)
                or self.headers.get("X-Chat-Token") != secret
            ):
                self.send_error(403)
                return
            streaming = False
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    raise ValueError("request too large")
                value = json.loads(self.rfile.read(size))
                messages = value["messages"]
                if (
                    not isinstance(messages, list)
                    or len(messages) > 100
                    or any(
                        set(m) != {"role", "content"}
                        or m["role"] not in ("user", "assistant")
                        or not isinstance(m["content"], str)
                        for m in messages
                    )
                ):
                    raise ValueError("invalid messages")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                streaming = True
                generated = []
                with lock:
                    for token in stream_reply(model, tokens, messages, max_new_tokens=48):
                        generated.append(token)
                        self.wfile.write(
                            (
                                "data: " + json.dumps({"text": tokens.decode(generated)}) + "\n\n"
                            ).encode()
                        )
                        self.wfile.flush()
                self.wfile.write(b'data: {"done":true}\n\n')
            except (ValueError, KeyError, TypeError) as exc:
                if not streaming:
                    self.send_error(400, str(exc))
                    return
                self.wfile.write(("data: " + json.dumps({"error": str(exc)}) + "\n\n").encode())

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"Local model chat: http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
