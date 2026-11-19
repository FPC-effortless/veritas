from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request

import pytest

from investigation_world.commercial.local_endpoint import (
    build_offline_local_opener,
    validate_local_chat_endpoint,
    validate_loopback_host,
)


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1"])
def test_literal_loopback_hosts_are_accepted(host: str) -> None:
    assert validate_loopback_host(host)


@pytest.mark.parametrize(
    "host", ["localhost", "example.com", "0.0.0.0", "192.168.1.10", "203.0.113.8"]
)
def test_dns_and_non_loopback_hosts_are_rejected(host: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        validate_loopback_host(host)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:8765/v1/chat/completions",
        "https://[::1]:8765/v1/chat/completions",
        "http://127.0.0.2/v1/chat/completions",
    ],
)
def test_local_chat_endpoint_accepts_literal_loopback(endpoint: str) -> None:
    assert validate_local_chat_endpoint(endpoint) == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://customer.example/v1/chat/completions",
        "http://192.168.1.10:8765/v1/chat/completions",
        "http://localhost:8765/v1/chat/completions",
        "ftp://127.0.0.1/v1/chat/completions",
        "http://127.0.0.1:8765/v1/chat/completions?token=secret",
        "http://127.0.0.1:8765/v1/chat/completions#fragment",
        "http://user:secret@127.0.0.1:8765/v1/chat/completions",
        "http://127.0.0.1:0/v1/chat/completions",
        "http://127.0.0.1:8765/other",
        "http://127.0.0.1:8765\\@evil.example/v1/chat/completions",
        "http://127.0.0.1:08765/v1/chat/completions",
    ],
)
def test_remote_or_ambiguous_endpoints_are_rejected(endpoint: str) -> None:
    with pytest.raises(ValueError):
        validate_local_chat_endpoint(endpoint)


def test_opener_ignores_environment_proxy_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://203.0.113.10:3128")
    monkeypatch.setenv("http_proxy", "http://203.0.113.10:3128")
    opener = build_offline_local_opener()
    proxy_handlers = [handler for handler in opener.handlers if isinstance(handler, ProxyHandler)]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}


def test_opener_does_not_follow_redirects() -> None:
    redirected_requests: list[str] = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            redirected_requests.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
    target_thread = Thread(target.serve_forever, daemon=True)
    target_thread.start()

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{target.server_port}/v1/chat/completions",
            )
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    redirect_thread = Thread(target=redirect.serve_forever, daemon=True)
    redirect_thread.start()
    try:
        request = Request(
            f"http://127.0.0.1:{redirect.server_port}/v1/chat/completions",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            build_offline_local_opener().open(request, timeout=2)
        assert error.value.code == 302
        assert redirected_requests == []
    finally:
        redirect.shutdown()
        redirect.server_close()
        target.shutdown()
        target.server_close()
        redirect_thread.join(timeout=2)
        target_thread.join(timeout=2)
