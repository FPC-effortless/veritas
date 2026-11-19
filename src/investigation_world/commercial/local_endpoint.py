"""Enforce same-device loopback transport for customer-model evaluation."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


def validate_loopback_host(host: str) -> str:
    """Accept only a literal loopback IP; DNS names and non-loopback hosts fail closed."""
    if type(host) is not str or not host or "%" in host:
        raise ValueError("host must be a literal loopback IP address")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("host must be a literal loopback IP address") from exc
    if not address.is_loopback:
        raise ValueError("host must resolve syntactically to a loopback IP address")
    return str(address)


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
        raise ValueError("endpoint authority must be a canonical loopback IP and optional port")
    return endpoint


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def build_offline_local_opener():
    """Build a direct opener with environment proxies and HTTP redirects disabled."""
    return build_opener(ProxyHandler({}), _RejectRedirects())
