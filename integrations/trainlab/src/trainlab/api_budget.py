"""Bound trusted evaluation API calls and retain redacted attempt receipts."""

from __future__ import annotations

import http.client
import math
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from .experiment_diagnostics import _number
from .prediction_artifacts import _hash, _require
from .runner import LabError, write_json

_RETRYABLE = {"HTTP_ERROR", "RESPONSE_LIMIT"}


class ApiBudget:
    """Single-owner, synchronous POST meter for one trusted endpoint."""

    def __init__(
        self,
        endpoint,
        root,
        *,
        endpoint_sha256,
        max_calls,
        min_interval,
        io_timeout,
        max_response_bytes,
    ):
        _require(
            type(endpoint) is str
            and 1 <= len(endpoint) <= 2000
            and all(33 <= ord(char) <= 126 for char in endpoint)
            and "\\" not in endpoint,
            "bounded absolute HTTP endpoint required",
        )
        try:
            parsed = urlsplit(endpoint)
            port = parsed.port
        except ValueError as exc:
            raise LabError("invalid HTTP endpoint") from exc
        _require(
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and "#" not in endpoint
            and (port is None or port > 0)
            and (parsed.scheme == "https" or parsed.hostname in ("127.0.0.1", "::1")),
            "HTTPS or loopback HTTP endpoint required",
        )
        _require(
            _hash(endpoint_sha256)
            and type(max_calls) is int
            and 1 <= max_calls <= 1000
            and _number(min_interval, 0, 3600)
            and _number(io_timeout, 0.01, 60)
            and type(max_response_bytes) is int
            and 1 <= max_response_bytes <= 16 * 1024**2,
            "bounded request limits and endpoint identity required",
        )
        self._root = Path(root).resolve()
        try:
            self._root.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise LabError("new receipt directory required") from exc
        self._transport = (
            http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        )
        self._host = parsed.hostname
        self._port = port
        self._target = parsed.path or "/"
        if parsed.query:
            self._target += "?" + parsed.query
        self._owner = threading.get_ident()
        self._active = False
        self._interval_ns = math.ceil(min_interval * 10**9)
        self._last_start = None
        self._io_timeout = io_timeout
        self._max_response_bytes = max_response_bytes
        self._max_calls = max_calls
        self._receipt = {
            "schema": "trainlab.api-budget.v1",
            "state": "OPEN",
            "endpoint_sha256": endpoint_sha256,
            "endpoint_identity": "CALLER_DECLARED",
            "limits": {
                "max_calls": max_calls,
                "min_interval_ns": self._interval_ns,
                "socket_io_timeout_seconds": io_timeout,
                "max_response_bytes": max_response_bytes,
            },
            "attempts": [],
        }
        self._save()

    def _save(self):
        write_json(self._root / "api-receipt.json", self._receipt)

    def _pace(self):
        if self._last_start is None:
            return
        deadline = self._last_start + self._interval_ns
        while (remaining := deadline - time.monotonic_ns()) > 0:
            time.sleep(remaining / 10**9)

    def post(self, body, *, bearer=None, retry_of=None):
        """Perform one explicitly authorized attempt and return its bounded body."""
        _require(
            threading.get_ident() == self._owner and not self._active,
            "request session requires one synchronous owner",
        )
        _require(self._receipt["state"] == "OPEN", "prior POST outcome unresolved")
        _require(type(body) is bytes and len(body) <= 1024**2, "bounded request bytes required")
        _require(
            bearer is None
            or (
                type(bearer) is str
                and 1 <= len(bearer) <= 4096
                and all(33 <= ord(char) <= 126 for char in bearer)
            ),
            "invalid bearer credential",
        )
        attempts = self._receipt["attempts"]
        _require(len(attempts) < self._max_calls, "API call budget exhausted")
        _require(
            retry_of is None
            or (
                type(retry_of) is int
                and 0 <= retry_of < len(attempts)
                and attempts[retry_of]["state"] in _RETRYABLE
            ),
            "retry requires an earlier observed failed response",
        )

        headers = {"Content-Type": "application/octet-stream"}
        if bearer is not None:
            headers["Authorization"] = "Bearer " + bearer
        connection = self._transport(self._host, self._port, timeout=self._io_timeout)
        row = {
            "id": len(attempts),
            "retry_of": retry_of,
            "state": "STARTED",
            "intent_ns": time.monotonic_ns(),
            "wire_started_ns": None,
            "elapsed_seconds": None,
            "http_status": None,
            "request_body_bytes": len(body),
            "response_body_bytes_read": None,
        }
        self._active = True
        attempts.append(row)
        self._receipt["state"] = "UNRESOLVED"
        try:
            self._save()
            self._pace()
            self._last_start = row["wire_started_ns"] = time.monotonic_ns()
            try:
                connection.request("POST", self._target, body=body, headers=headers)
                with connection.getresponse() as response:
                    row["http_status"] = status = response.status
                    if not 200 <= status <= 599:
                        raise http.client.HTTPException("no supported final HTTP response")
                    declared_length = response.length
                    payload = response.read(self._max_response_bytes + 1)
                    if declared_length is not None and len(payload) < min(
                        declared_length, self._max_response_bytes + 1
                    ):
                        raise http.client.IncompleteRead(payload)
            except (OSError, http.client.HTTPException) as exc:
                row["state"] = "OUTCOME_UNKNOWN"
                raise LabError("POST transport failed; remote outcome unknown") from exc
            row["response_body_bytes_read"] = len(payload)
            if len(payload) > self._max_response_bytes:
                payload = None
                row["state"] = "RESPONSE_LIMIT"
            else:
                row["state"] = "SUCCEEDED" if 200 <= status < 300 else "HTTP_ERROR"
        finally:
            connection.close()
            if row["wire_started_ns"] is not None:
                row["elapsed_seconds"] = (time.monotonic_ns() - row["wire_started_ns"]) / 10**9
            if row["state"] == "STARTED" and row["wire_started_ns"] is not None:
                row["state"] = "OUTCOME_UNKNOWN"
            known = row["state"] in {"SUCCEEDED", *_RETRYABLE}
            if known:
                self._receipt["state"] = "OPEN"
            try:
                self._save()
            except BaseException:
                self._receipt["state"] = "UNRESOLVED"
                raise
            finally:
                self._active = False
        return {**row, "response": payload}
