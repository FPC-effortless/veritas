from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from investigation_world.commercial.voice_qualification import (
    build_voice_qualification_report,
    load_voice_qualification_suite,
)
from investigation_world.commercial.voice_runner import (
    VoiceAgentResult,
    VoiceAgentSession,
    compare_voice_configurations,
)
from investigation_world.operational.models import EpisodeSubmission

SYSTEM_PROMPT = """You are operating a customer-service workflow in an executable world.
Return exactly one JSON object per turn. Never invent hidden state.

Commands:
{"type":"search","system":"CRM","query":"text","limit":10}
{"type":"search_all","query":"text","limit":10}
{"type":"open_record","record_id":"..."}
{"type":"act","action_name":"...","parameters":{...}}
{"type":"submit","conclusion":"...","claimed_state":{},"evidence_ids":[],"confidence":0.0}

Use search/open to gather evidence, then use only public actions. Submit when complete.
"""


class EndpointClient:
    def __init__(
        self,
        endpoint: str,
        api_key: str | None,
        timeout: float,
        max_tokens: int,
        input_cost_per_million: float | None,
        output_cost_per_million: float | None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million
        self.calls = 0
        self.request_seconds = 0.0

    def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
    ) -> tuple[str, float | None]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": self.max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        started = time.time()
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(
                "utf-8",
                errors="replace",
            )[:1000]
            raise RuntimeError(
                f"model endpoint returned HTTP {exc.code}: {detail}"
            ) from exc

        self.request_seconds += time.time() - started
        self.calls += 1

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "endpoint response is not OpenAI chat-completions compatible"
            ) from exc

        return str(content), self._cost(body)

    def _cost(self, body: dict[str, Any]) -> float | None:
        if (
            self.input_cost_per_million is None
            or self.output_cost_per_million is None
        ):
            return None

        usage = body.get("usage") or {}
        input_tokens = usage.get(
            "prompt_tokens",
            usage.get("input_tokens"),
        )
        output_tokens = usage.get(
            "completion_tokens",
            usage.get("output_tokens"),
        )
        if not isinstance(input_tokens, int) or not isinstance(
            output_tokens,
            int,
        ):
            return None

        cost = (
            input_tokens * self.input_cost_per_million
            + output_tokens * self.output_cost_per_million
        ) / 1_000_000
        return float(cost)


def _json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("model command must be a JSON object")
    return parsed


def _integer(value: Any, default: int = 10) -> int:
    if isinstance(value, int):
        return max(1, min(50, value))
    return default


def _submission(command: dict[str, Any]) -> EpisodeSubmission:
    claimed_state = command.get("claimed_state")
    evidence_ids = command.get("evidence_ids")
    confidence = command.get("confidence", 0.5)
    return EpisodeSubmission(
        conclusion=str(command.get("conclusion", "")),
        claimed_state=(
            claimed_state
            if isinstance(claimed_state, dict)
            else {}
        ),
        evidence_ids=(
            [str(item) for item in evidence_ids]
            if isinstance(evidence_ids, list)
            else []
        ),
        confidence=(
            float(confidence)
            if isinstance(confidence, int | float)
            else 0.5
        ),
    )


def _execute(
    session: VoiceAgentSession,
    command: dict[str, Any],
) -> tuple[dict[str, Any], EpisodeSubmission | None]:
    command_type = str(command.get("type", ""))

    if command_type == "search":
        result = session.search(
            str(command.get("system", "")),
            str(command.get("query", "")),
            _integer(command.get("limit")),
        )
        return {"ok": True, "result": result}, None

    if command_type == "search_all":
        result = session.search_all(
            str(command.get("query", "")),
            _integer(command.get("limit")),
        )
        return {"ok": True, "result": result}, None

    if command_type == "open_record":
        result = session.open_record(
            str(command.get("record_id", "")),
        )
        return {"ok": True, "result": result}, None

    if command_type == "act":
        parameters = command.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
        result = session.act(
            str(command.get("action_name", "")),
            **parameters,
        )
        return {"ok": True, "result": result}, None

    if command_type == "submit":
        submission = _submission(command)
        return {"ok": True, "submitted": True}, submission

    return {
        "ok": False,
        "error": (
            "unknown command type; use search, search_all, open_record, "
            "act, or submit"
        ),
    }, None


def make_endpoint_driver(
    client: EndpointClient,
    model: str,
    *,
    max_turns: int,
):
    def driver(session: VoiceAgentSession) -> VoiceAgentResult:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Public operational task:\n"
                    + json.dumps(
                        session.public_payload(),
                        sort_keys=True,
                    )
                ),
            },
        ]
        total_cost = 0.0
        has_cost = False

        for _ in range(max_turns):
            content, cost = client.complete(model, messages)
            if cost is not None:
                total_cost += cost
                has_cost = True
            messages.append(
                {"role": "assistant", "content": content}
            )
            try:
                command = _json_object(content)
                result, submission = _execute(session, command)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                result = {
                    "ok": False,
                    "error": f"invalid command: {exc}",
                }
                submission = None

            if submission is not None:
                return VoiceAgentResult(
                    submission=submission,
                    cost_usd=total_cost if has_cost else None,
                )

            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Tool result:\n"
                        + json.dumps(result, sort_keys=True)
                    ),
                }
            )

        return VoiceAgentResult(
            submission=EpisodeSubmission(
                conclusion="Agent did not submit before the turn limit.",
                confidence=0.0,
            ),
            cost_usd=total_cost if has_cost else None,
        )

    return driver


def _configuration(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "configuration must use NAME=MODEL"
        )
    name, model = value.split("=", 1)
    if not name.strip() or not model.strip():
        raise argparse.ArgumentTypeError(
            "configuration must use non-empty NAME=MODEL"
        )
    return name.strip(), model.strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run Voice Operations qualification against an "
            "OpenAI-compatible endpoint using a sealed suite."
        )
    )
    parser.add_argument(
        "--endpoint",
        required=True,
        help="Full /v1/chat/completions-compatible URL",
    )
    parser.add_argument(
        "--configuration",
        action="append",
        type=_configuration,
        required=True,
        help="Repeat as NAME=MODEL; at least three are required.",
    )
    parser.add_argument(
        "--suite",
        type=Path,
        required=True,
        help="Evaluator-only sealed voice suite JSON artifact.",
    )
    parser.add_argument(
        "--suite-sha256",
        required=True,
        help="Out-of-band SHA-256 digest for the exact sealed suite bytes.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--api-key-env",
        default="VERITAS_MODEL_API_KEY",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--max-turns", type=int, default=18)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--input-cost-per-million", type=float)
    parser.add_argument("--output-cost-per-million", type=float)
    args = parser.parse_args()

    configurations = dict(args.configuration)
    if len(configurations) < 3:
        parser.error("at least three distinct configurations are required")

    suite = load_voice_qualification_suite(
        args.suite,
        expected_sha256=args.suite_sha256,
    )
    client = EndpointClient(
        endpoint=args.endpoint,
        api_key=os.getenv(args.api_key_env),
        timeout=args.timeout,
        max_tokens=args.max_tokens,
        input_cost_per_million=args.input_cost_per_million,
        output_cost_per_million=args.output_cost_per_million,
    )
    drivers = {
        name: make_endpoint_driver(
            client,
            model,
            max_turns=args.max_turns,
        )
        for name, model in configurations.items()
    }

    started = time.time()
    runs, summaries = compare_voice_configurations(
        suite,
        drivers,
        attempts=args.attempts,
    )
    output = {
        "schema_version": "veritas-voice-qualification-run-v3",
        "suite": {
            "sha256": args.suite_sha256.lower(),
            "scenarios": len(suite),
            "attempts": args.attempts,
            "configurations": configurations,
        },
        "summaries": [
            item.model_dump(mode="json")
            for item in summaries
        ],
        "runs": [
            item.model_dump(mode="json")
            for item in runs
        ],
        "runtime": {
            "wall_seconds": round(time.time() - started, 3),
            "request_seconds": round(client.request_seconds, 3),
            "model_calls": client.calls,
            "transport": "openai-compatible-http",
            "endpoint_host": urlparse(args.endpoint).netloc,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        build_voice_qualification_report(summaries, runs),
        encoding="utf-8",
    )
    print(json.dumps(output["summaries"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
