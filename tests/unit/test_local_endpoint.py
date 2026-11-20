from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from investigation_world.commercial.local_endpoint import (
    MAX_REQUEST_BODY_BYTES,
    RequestBodyTooLarge,
    build_offline_local_opener,
    read_bounded_json_object,
    validate_local_chat_endpoint,
    validate_loopback_host,
)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_literal_loopback_hosts_are_accepted(host: str) -> None:
    assert validate_loopback_host(host)


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "example.com",
        "0.0.0.0",
        "127.0.0.2",
        "127.255.255.254",
        "0:0:0:0:0:0:0:1",
        "192.168.1.10",
        "203.0.113.8",
    ],
)
def test_dns_and_non_loopback_hosts_are_rejected(host: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        validate_loopback_host(host)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:8765/v1/chat/completions",
        "https://[::1]:8765/v1/chat/completions",
    ],
)
def test_local_chat_endpoint_accepts_literal_loopback(endpoint: str) -> None:
    assert validate_local_chat_endpoint(endpoint) == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://customer.example/v1/chat/completions",
        "http://127.0.0.2:8765/v1/chat/completions",
        "http://[0:0:0:0:0:0:0:1]:8765/v1/chat/completions",
        "http://192.168.1.10:8765/v1/chat/completions",
        "http://localhost:8765/v1/chat/completions",
        "ftp://127.0.0.1/v1/chat/completions",
        "http://127.0.0.1:8765/v1/chat/completions?token=secret",
        "http://127.0.0.1:8765/v1/chat/completions#fragment",
        "http://127.0.0.1:8765/v1/chat/completions?",
        "http://127.0.0.1:8765/v1/chat/completions#",
        "HTTP://127.0.0.1:8765/v1/chat/completions",
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


def test_opener_ignores_environment_proxy_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy_names = (
        "HTTP_PROXY",
        "http_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    )
    for name in proxy_names:
        monkeypatch.setenv(name, "http://203.0.113.10:3128")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")

    class DirectHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"direct")

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), DirectHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/health"
        with build_offline_local_opener().open(url, timeout=2) as response:
            assert response.status == 200
            assert response.read() == b"direct"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
    target_thread = Thread(target=target.serve_forever, daemon=True)
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


def parse_request_body(
    raw: bytes,
    content_length_values: list[str] | None = None,
    *,
    max_bytes: int = MAX_REQUEST_BODY_BYTES,
) -> dict[str, object]:
    headers = (
        content_length_values
        if content_length_values is not None
        else [str(len(raw))]
    )
    return read_bounded_json_object(BytesIO(raw), headers, max_bytes=max_bytes)


def test_request_body_accepts_exact_configured_limit() -> None:
    prefix = b'{"value":"'
    suffix = b'"}'
    raw = prefix + b"a" * (MAX_REQUEST_BODY_BYTES - len(prefix) - len(suffix)) + suffix
    payload = parse_request_body(raw)
    assert isinstance(payload["value"], str)
    assert len(payload["value"]) == MAX_REQUEST_BODY_BYTES - len(prefix) - len(suffix)


def test_request_body_rejects_oversize_before_reading() -> None:
    raw = b'{"ok":true}'
    stream = BytesIO(raw)
    with pytest.raises(RequestBodyTooLarge, match="1 MiB"):
        read_bounded_json_object(stream, [str(len(raw))], max_bytes=len(raw) - 1)
    assert stream.tell() == 0


@pytest.mark.parametrize(
    "headers",
    [[], ["10", "10"], ["-1"], ["0"], ["01"], ["١"]],
)
def test_request_body_rejects_missing_duplicate_or_noncanonical_lengths(
    headers: list[str],
) -> None:
    with pytest.raises(ValueError):
        read_bounded_json_object(BytesIO(b'{"ok":true}'), headers)


def test_request_body_rejects_truncated_body() -> None:
    with pytest.raises(ValueError, match="truncated"):
        read_bounded_json_object(BytesIO(b"{}"), ["3"])


def test_request_body_rejects_invalid_utf8_and_non_object_json() -> None:
    with pytest.raises(ValueError, match="valid bounded UTF-8 JSON"):
        read_bounded_json_object(BytesIO(b"\xff"), ["1"])
    with pytest.raises(ValueError, match="JSON object"):
        read_bounded_json_object(BytesIO(b"[]"), ["2"])


def test_request_body_rejects_duplicate_nested_keys() -> None:
    raw = b'{"outer":{"value":1,"value":2}}'
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        read_bounded_json_object(BytesIO(raw), [str(len(raw))])


@pytest.mark.parametrize("raw", [b'{"value":NaN}', b'{"value":1e999}'])
def test_request_body_rejects_nonfinite_json_numbers(raw: bytes) -> None:
    with pytest.raises(ValueError, match="non-finite|finite"):
        read_bounded_json_object(BytesIO(raw), [str(len(raw))])
