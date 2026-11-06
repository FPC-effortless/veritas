from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from investigation_world.observatory.execution import (
    ModelProviderAdapter,
    ModelRequest,
    ModelResponse,
    ProviderUsage,
)


class ProviderHTTPError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"provider HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


def _join_endpoint(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith(path):
        return base
    return f"{base}/{path.lstrip('/')}"


def _validated_http_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("provider endpoint must use http or https")
    if not parsed.netloc or parsed.hostname is None:
        raise ValueError("provider endpoint must include a network host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("provider endpoint must not embed credentials in the URL")
    return url


def _json_post(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_s: float,
) -> tuple[dict[str, Any], float]:
    endpoint = _validated_http_url(url)
    body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    started = time.perf_counter()
    try:
        # B310 is suppressed only after the URL is constrained above to http(s) with a host.
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise ProviderHTTPError(exc.code, raw) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"provider request failed: {exc.reason}") from exc
    latency = max(0.0, time.perf_counter() - started)
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("provider returned a non-object JSON response")
    return decoded, latency


def _estimated_cost(model_config: dict[str, Any], input_tokens: int, output_tokens: int) -> float:
    input_rate = float(model_config.get("input_cost_per_million", 0.0) or 0.0)
    output_rate = float(model_config.get("output_cost_per_million", 0.0) or 0.0)
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000.0


def _openai_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str):
        return direct
    parts: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts)


def _chat_output_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message", {})
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        return "\n".join(parts)
    return str(content) if content is not None else ""


class OpenAIResponsesProvider(ModelProviderAdapter):
    """Dependency-free adapter for the OpenAI Responses API."""

    provider_id = "openai"

    def __init__(
        self,
        *,
        base_url: str = "https://api.openai.com/v1",
        api_key_env: str = "OPENAI_API_KEY",
        timeout_s: float = 120.0,
    ):
        self.base_url = base_url
        self.api_key_env = api_key_env
        self.timeout_s = timeout_s

    def invoke(self, request: ModelRequest) -> ModelResponse:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"missing provider credential environment variable {self.api_key_env}")
        body: dict[str, Any] = {}
        provider_parameters = request.model.config.get("provider_parameters", {})
        if isinstance(provider_parameters, dict):
            body.update(provider_parameters)
        body.update(request.parameters)
        body["model"] = request.model.model_id
        body["input"] = request.payload
        body["store"] = False
        endpoint = request.model.endpoint or _join_endpoint(self.base_url, "responses")
        response, latency = _json_post(
            endpoint,
            body,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_s=self.timeout_s,
        )
        usage = response.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
        return ModelResponse(
            request_id=request.request_id,
            output=_openai_output_text(response),
            latency_s=latency,
            usage=ProviderUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=_estimated_cost(request.model.config, input_tokens, output_tokens),
            ),
            metadata={
                "response_id": response.get("id"),
                "status": response.get("status"),
                "provider_model": response.get("model"),
            },
        )


class OpenAICompatibleChatProvider(ModelProviderAdapter):
    """Chat-completions adapter for hosted routers, TGI/HUGS, vLLM, and similar servers."""

    def __init__(
        self,
        provider_id: str,
        *,
        base_url: str,
        api_key_env: str | None = None,
        timeout_s: float = 120.0,
        extra_headers: dict[str, str] | None = None,
    ):
        self.provider_id = provider_id
        self.base_url = base_url
        self.api_key_env = api_key_env
        self.timeout_s = timeout_s
        self.extra_headers = extra_headers or {}

    def invoke(self, request: ModelRequest) -> ModelResponse:
        if isinstance(request.payload, list):
            messages = request.payload
        elif isinstance(request.payload, dict) and "messages" in request.payload:
            messages = request.payload["messages"]
        else:
            messages = [{"role": "user", "content": str(request.payload)}]
        body: dict[str, Any] = {}
        provider_parameters = request.model.config.get("provider_parameters", {})
        if isinstance(provider_parameters, dict):
            body.update(provider_parameters)
        body.update(request.parameters)
        body["model"] = request.model.model_id
        body["messages"] = messages
        endpoint = request.model.endpoint or _join_endpoint(self.base_url, "chat/completions")
        headers = dict(self.extra_headers)
        if self.api_key_env:
            api_key = os.environ.get(self.api_key_env)
            if not api_key:
                raise RuntimeError(
                    f"missing provider credential environment variable {self.api_key_env}"
                )
            headers["Authorization"] = f"Bearer {api_key}"
        response, latency = _json_post(
            endpoint,
            body,
            headers=headers,
            timeout_s=self.timeout_s,
        )
        usage = response.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
        output_tokens = int(
            usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
        )
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
        return ModelResponse(
            request_id=request.request_id,
            output=_chat_output_text(response),
            latency_s=latency,
            usage=ProviderUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=_estimated_cost(request.model.config, input_tokens, output_tokens),
            ),
            metadata={
                "response_id": response.get("id"),
                "provider_model": response.get("model"),
            },
        )


class HuggingFaceInferenceProvider(OpenAICompatibleChatProvider):
    """Hugging Face Inference Providers through its OpenAI-compatible router."""

    def __init__(self, *, timeout_s: float = 120.0):
        super().__init__(
            "huggingface",
            base_url="https://router.huggingface.co/v1",
            api_key_env="HF_TOKEN",
            timeout_s=timeout_s,
        )


class SubprocessModelProvider(ModelProviderAdapter):
    """Safe argv-based local/CLI adapter. No shell interpolation is performed."""

    def __init__(
        self,
        provider_id: str,
        command: list[str],
        *,
        timeout_s: float = 120.0,
        cwd: str | Path | None = None,
        json_stdin: bool = False,
    ):
        if not command:
            raise ValueError("subprocess provider command must not be empty")
        self.provider_id = provider_id
        self.command = list(command)
        self.timeout_s = timeout_s
        self.cwd = Path(cwd) if cwd is not None else None
        self.json_stdin = json_stdin

    def invoke(self, request: ModelRequest) -> ModelResponse:
        argv = [item.replace("{model}", request.model.model_id) for item in self.command]
        stdin_payload: str
        if self.json_stdin:
            stdin_payload = json.dumps(
                {
                    "model": request.model.model_id,
                    "payload": request.payload,
                    "parameters": request.parameters,
                },
                default=str,
            )
        else:
            stdin_payload = str(request.payload)
        started = time.perf_counter()
        completed = subprocess.run(
            argv,
            input=stdin_payload,
            text=True,
            capture_output=True,
            timeout=self.timeout_s,
            cwd=str(self.cwd) if self.cwd is not None else None,
            check=False,
        )
        latency = max(0.0, time.perf_counter() - started)
        if completed.returncode != 0:
            raise RuntimeError(
                f"subprocess provider exited {completed.returncode}: {completed.stderr[:500]}"
            )
        return ModelResponse(
            request_id=request.request_id,
            output=completed.stdout.strip(),
            latency_s=latency,
            metadata={"returncode": completed.returncode},
        )
