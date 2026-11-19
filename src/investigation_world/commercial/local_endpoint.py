"""Enforce same-device loopback transport for customer-model evaluation."""

from __future__ import annotations

import ipaddress
import json
import math
from typing import Any, BinaryIO
from urllib.parse import urlsplit
from urllib.request import (
    build_opener,
    HTTPRedirectHandler,
    OpenerDirector,
    ProxyHandler,
)


MAX_REQUEST_BODY_BYTES = 1024 * 1024


class RequestBodyTooLarge(ValueError):
    """Raised before reading a local request body that exceeds the configured cap."""


def read_bounded_json_object(
    stream: BinaryIO,
    content_length_values: list[str] | None,
    *,
    max_bytes: int = MAX_REQUEST_BODY_BYTES,
) -> dict[str, Any]:
    """Read one bounded, unambiguous JSON object from an HTTP request stream."""
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("request body limit must be a positive integer")
    if content_length_values is None or len(content_length_values) != 1:
        raise ValueError("exactly one Content-Length header is required")

    content_length = content_length_values[0]
    if (
        not content_length
        or not content_length.isascii()
        or not content_length.isdecimal()
    ):
        raise ValueError("Content-Length must be canonical decimal digits")
    if len(content_length) > 1 and content_length.startswith("0"):
        raise ValueError("Content-Length must not contain leading zeroes")
    if len(content_length) > len(str(max_bytes)):
        raise RequestBodyTooLarge("request body exceeds 1 MiB limit")

    length = int(content_length)
    if length == 0:
        raise ValueError("request body must not be empty")
    if length > max_bytes:
        raise RequestBodyTooLarge("request body exceeds 1 MiB limit")

    body = stream.read(length)
    if type(body) is not bytes or len(body) != length:
        raise ValueError("request body is truncated")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key}")
            result[key] = value
        return result

    def reject_constant(token: str) -> None:
        raise ValueError(f"non-finite JSON constant is not allowed: {token}")

    try:
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("request body must be valid bounded UTF-8 JSON") from exc

    def reject_nonfinite(value: Any) -> None:
        if type(value) is float and not math.isfinite(value):
            raise ValueError("request JSON numbers must be finite")
        if isinstance(value, dict):
            for child in value.values():
                reject_nonfinite(child)
        elif isinstance(value, list):
            for child in value:
                reject_nonfinite(child)

    reject_nonfinite(payload)
    if type(payload) is not dict:
        raise ValueError("request body must be a JSON object")
    return payload


def validate_loopback_host(host: str) -> str:
    """Accept literal loopback IPs; reject DNS names and non-loopback hosts."""
    if type(host) is not str or not host or "%" in host:
        raise ValueError("host must be a literal loopback IP address")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("host must be a literal loopback IP address") from exc
    if host not in {"127.0.0.1", "::1"} or str(address) != host:
        raise ValueError("host must be exactly 127.0.0.1 or ::1 loopback literal in canonical form")
    if not address.is_loopback:
        raise ValueError("host must be a loopback IP address")
    return host


def validate_local_chat_endpoint(endpoint: str) -> str:
    """Validate the exact local chat endpoint before loading private evaluation data."""
    if type(endpoint) is not str or not endpoint or len(endpoint) > 2048:
        raise ValueError("endpoint must be a bounded URL")
    if any(ord(character) <= 0x20 for character in endpoint):
        raise ValueError("endpoint must not contain whitespace or control characters")
    try:
        parsed = urlsplit(endpoint)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("endpoint URL is malformed") from exc
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("endpoint scheme must be http or https")
    if not parsed.netloc or host is None:
        raise ValueError("endpoint host is required")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("credentials must not be embedded in endpoint URLs")
    if parsed.query or parsed.fragment:
        raise ValueError("endpoint query strings and fragments are not allowed")
    if parsed.path != "/v1/chat/completions":
        raise ValueError("endpoint path must be /v1/chat/completions")
    canonical_host = validate_loopback_host(host)
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("endpoint port must be between 1 and 65535")
    authority_host = f"[{canonical_host}]" if ":" in canonical_host else canonical_host
    expected_netloc = authority_host + (f":{port}" if port is not None else "")
    if parsed.netloc != expected_netloc:
        raise ValueError(
            "endpoint authority must be a canonical loopback IP and optional port"
        )
    return endpoint


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def build_offline_local_opener() -> OpenerDirector:
    """Build a direct opener with environment proxies and HTTP redirects disabled."""
    return build_opener(ProxyHandler({}), _RejectRedirects())
