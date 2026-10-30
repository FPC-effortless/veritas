"""Authenticated, bounded WSGI hosting for trusted-operator deployments."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import signal
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlsplit

from .runner import LabError, read_json
from .server import SECURITY_HEADERS, Workspace, local_request

ITERATIONS = 600_000


def create_credentials(destination: Path, username: str, password: str) -> None:
    """Create one operator credential file. Rotate by replacing it while stopped."""
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", username):
        raise LabError("username must contain 1-64 letters, digits, or _.@-")
    if not 12 <= len(password) <= 512:
        raise LabError("password must contain 12-512 characters")
    salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    document = {
        "schema": "trainlab.auth.v1",
        "username": username,
        "salt": salt.hex(),
        "password_hash": hashed.hex(),
    }
    try:
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise LabError("credentials destination already exists") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(document, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


class ProductionApp:
    """Shared trusted workspace; authentication is not tenant/job isolation."""

    def __init__(
        self,
        runs: Path,
        experiments: Path | None,
        *,
        auth_file: Path | None,
        public_origin: str | None,
        port=8765,
        log_limit=16 * 1024 * 1024,
    ):
        if auth_file is None:
            raise LabError("production hosting requires an operator credentials file")
        if public_origin is not None:
            parsed = urlsplit(public_origin)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.netloc != parsed.netloc.lower()
            ):
                raise LabError(
                    "public origin must be an HTTPS origin without credentials or a path"
                )
        if auth_file.is_symlink() or (os.name == "posix" and auth_file.stat().st_mode & 0o077):
            raise LabError("credentials must be a private regular file (chmod 600)")
        auth = read_json(auth_file, 4096)
        if (
            not isinstance(auth, dict)
            or set(auth) != {"schema", "username", "salt", "password_hash"}
            or auth["schema"] != "trainlab.auth.v1"
            or not isinstance(auth["username"], str)
            or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", auth["username"])
            or not isinstance(auth["salt"], str)
            or not re.fullmatch("[a-f0-9]{32}", auth["salt"])
            or not isinstance(auth["password_hash"], str)
            or not re.fullmatch("[a-f0-9]{64}", auth["password_hash"])
        ):
            raise LabError("invalid operator credentials file")
        self.auth = auth
        self.public_origin = public_origin
        self.port = port
        self.workspace = Workspace(runs, experiments, log_limit=log_limit)

    def close(self):
        self.workspace.close()

    def authorized(self, header):
        try:
            if not header.startswith("Basic ") or len(header) > 4096:
                return False
            username, password = (
                base64.b64decode(header[6:], validate=True).decode("utf-8").split(":", 1)
            )
            if len(password) > 512:
                return False
            hashed = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), bytes.fromhex(self.auth["salt"]), ITERATIONS
            ).hex()
            return hmac.compare_digest(hashed, self.auth["password_hash"]) and hmac.compare_digest(
                username.encode(), self.auth["username"].encode()
            )
        except (ValueError, UnicodeError, binascii.Error):
            return False

    def __call__(self, environ, start_response):
        headers = {
            "Host": environ.get("HTTP_HOST", ""),
            "Origin": environ.get("HTTP_ORIGIN"),
            "Content-Type": environ.get("CONTENT_TYPE", ""),
            "X-TrainLab-Token": environ.get("HTTP_X_TRAINLAB_TOKEN", ""),
        }
        path = environ.get("PATH_INFO", "/")
        query = environ.get("QUERY_STRING", "")
        extra = {}
        if not local_request(headers, self.port, self.public_origin):
            status, data, mime = (
                403,
                {"error": "Configured host and same-origin access required."},
                "application/json",
            )
        elif path == "/healthz" and environ["REQUEST_METHOD"] == "GET":
            status, data, mime = self.workspace.dispatch("GET", path, headers)
        elif not self.authorized(environ.get("HTTP_AUTHORIZATION", "")):
            status, data, mime = (
                401,
                {"error": "Operator authentication required."},
                "application/json",
            )
            extra["WWW-Authenticate"] = 'Basic realm="TrainLab", charset="UTF-8"'
        else:
            try:
                size = int(environ.get("CONTENT_LENGTH") or "0")
                if not 0 <= size <= 4096:
                    raise LabError("request body too large")
                body = environ["wsgi.input"].read(size)
                if len(body) != size:
                    raise LabError("incomplete request")
                status, data, mime = self.workspace.dispatch(
                    environ["REQUEST_METHOD"], path + ("?" + query if query else ""), headers, body
                )
            except (ValueError, OSError):
                status, data, mime = (
                    400,
                    {"error": "Invalid or incomplete request."},
                    "application/json",
                )
        if mime == "application/json":
            data = json.dumps(data, allow_nan=False).encode()
        response_headers = {
            **SECURITY_HEADERS,
            **extra,
            "Content-Type": mime,
            "Content-Length": str(len(data)),
        }
        if self.public_origin:
            response_headers["Strict-Transport-Security"] = "max-age=31536000"
        start_response(f"{status} {HTTPStatus(status).phrase}", list(response_headers.items()))
        return [data]


def serve_production(
    runs: Path,
    experiments: Path | None,
    *,
    auth_file: Path,
    public_origin: str | None,
    host="127.0.0.1",
    port=8765,
):
    if host not in ("127.0.0.1", "localhost") and not public_origin:
        raise LabError("remote binding requires an HTTPS public origin and TLS reverse proxy")
    try:
        from waitress import create_server
    except ImportError as error:
        raise LabError("install trainlab-local[server] to enable production hosting") from error
    application = ProductionApp(
        runs, experiments, auth_file=auth_file, public_origin=public_origin, port=port
    )
    server = None
    previous = None
    try:
        server = create_server(
            application,
            host=host,
            port=port,
            threads=8,
            connection_limit=64,
            channel_timeout=15,
            cleanup_interval=5,
            max_request_body_size=4096,
            max_request_header_size=16384,
            expose_tracebacks=False,
            clear_untrusted_proxy_headers=True,
        )
        application.port = server.effective_port

        def terminate(signum, frame):
            raise KeyboardInterrupt

        previous = signal.signal(signal.SIGTERM, terminate)
        print(
            f"TrainLab production server listening on {host}:{server.effective_port}; "
            "trusted operators only; TLS reverse proxy required for remote access.",
            flush=True,
        )
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)
        application.close()
        if server is not None:
            server.close()
            server.task_dispatcher.shutdown(timeout=5)
