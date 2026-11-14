import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from trainlab.api_budget import ApiBudget
from trainlab.runner import LabError, read_json


class RequestBudgetTests(unittest.TestCase):
    def setUp(self):
        requests = self.requests = []
        responses = self.responses = []
        release_response = self.release_response = threading.Event()
        observed_eof = self.observed_eof = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                requests.append((self.path, body, self.headers.get("Authorization")))
                status, reply, *options = responses.pop(0)
                if options == ["hold"]:
                    release_response.wait(5)
                    self.close_connection = True
                    return
                if status is None:
                    self.close_connection = True
                    return
                if options == ["early-hints"]:
                    self.send_response_only(103)
                    self.end_headers()
                    self.wfile.flush()
                    options = []
                self.send_response(status)
                if options == ["transfer-encoding"]:
                    self.send_header("Transfer-Encoding", "chunked")
                else:
                    self.send_header("Content-Length", str(len(reply) + bool(options)))
                if options == ["conflicting-length"]:
                    self.send_header("Content-Length", str(len(reply)))
                self.send_header("Location", "/redirected")
                self.end_headers()
                self.wfile.write(reply)
                if options == ["hold-body"]:
                    self.wfile.flush()
                    self.connection.settimeout(2)
                    try:
                        if self.connection.recv(1) == b"":
                            observed_eof.set()
                    except TimeoutError:
                        pass

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        task = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
        task.start()
        self.addCleanup(server.server_close)
        self.addCleanup(task.join)
        self.addCleanup(server.shutdown)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "receipt"
        self.endpoint = f"http://127.0.0.1:{server.server_port}/model?private=query"

    def session(self, **limits):
        return ApiBudget(
            self.endpoint,
            self.root,
            endpoint_sha256="a" * 64,
            **{
                "max_calls": 3,
                "min_interval": 0.025,
                "io_timeout": 1,
                "max_response_bytes": 16,
                **limits,
            },
        )

    def test_limits_count_failures_and_explicit_retry_but_never_follow_redirect(self):
        self.responses.extend([(429, b"try again"), (200, b"secret reply"), (302, b"move")])
        meter = self.session()
        first = meter.post(b"secret request", bearer="secret-token")
        self.assertEqual(first["http_status"], 429)
        second = meter.post(b"secret request", retry_of=first["id"])
        self.assertEqual(second["response"], b"secret reply")
        self.assertEqual(meter.post(b"third")["http_status"], 302)
        with self.assertRaisesRegex(LabError, "call budget"):
            meter.post(b"fourth")
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(self.requests[0][2], "Bearer secret-token")
        self.assertTrue(all(path == "/model?private=query" for path, _, _ in self.requests))
        receipt_file = self.root / "api-receipt.json"
        attempts = read_json(receipt_file)["attempts"]
        self.assertEqual(
            [row["state"] for row in attempts], ["HTTP_ERROR", "SUCCEEDED", "HTTP_ERROR"]
        )
        self.assertEqual(attempts[1]["retry_of"], 0)
        self.assertGreaterEqual(
            attempts[1]["wire_started_ns"] - attempts[0]["wire_started_ns"], 25000000
        )
        self.assertNotIn("secret", receipt_file.read_text())
        self.assertNotIn("private=query", receipt_file.read_text())

    def test_uncertain_post_stops_session_and_directory_cannot_be_reused(self):
        self.responses.append((None, b""))
        session = self.session()
        with self.assertRaisesRegex(LabError, "unknown"):
            session.post(b"secret")
        with self.assertRaisesRegex(LabError, "unresolved"):
            session.post(b"new")
        with self.assertRaisesRegex(LabError, "new receipt directory"):
            self.session()
        receipt = read_json(self.root / "api-receipt.json")
        self.assertEqual(receipt["attempts"][0]["state"], "OUTCOME_UNKNOWN")
        self.assertEqual(receipt["state"], "UNRESOLVED")
        self.assertEqual(len(self.requests), 1)

    def test_response_cap_and_retry_preflight(self):
        self.responses.extend([(200, b"x" * 100), (200, b"short")])
        session = self.session()
        with self.assertRaisesRegex(LabError, "retry"):
            session.post(b"request", retry_of=0)
        capped = session.post(b"request")
        self.assertEqual(capped["state"], "RESPONSE_LIMIT")
        self.assertIsNone(capped["response"])
        self.assertEqual(session.post(b"request", retry_of=0)["response"], b"short")

    def test_truncated_declared_body_remains_unresolved(self):
        self.responses.append((200, b"short", "truncated"))
        session = self.session()
        with self.assertRaisesRegex(LabError, "unknown"):
            session.post(b"request")
        attempt = read_json(self.root / "api-receipt.json")["attempts"][0]
        self.assertEqual(attempt["state"], "OUTCOME_UNKNOWN")
        self.assertEqual(attempt["http_status"], 200)

    def test_conflicting_response_length_is_rejected(self):
        self.responses.append((200, b"body", "conflicting-length"))
        session = self.session()
        with self.assertRaisesRegex(LabError, "unknown"):
            session.post(b"request")
        attempt = read_json(self.root / "api-receipt.json")["attempts"][0]
        self.assertEqual(attempt["state"], "OUTCOME_UNKNOWN")
        self.assertIsNone(attempt["response_body_bytes_read"])

    def test_unsupported_transfer_encoding_is_rejected(self):
        self.responses.append((200, b"4\r\nbody\r\n0\r\n\r\n", "transfer-encoding"))
        session = self.session()
        with self.assertRaisesRegex(LabError, "unknown"):
            session.post(b"request")
        attempt = read_json(self.root / "api-receipt.json")["attempts"][0]
        self.assertEqual(attempt["state"], "OUTCOME_UNKNOWN")

    def test_relative_receipt_root_is_pinned_at_creation(self):
        self.responses.append((200, b"ok"))
        original = self.root.parent
        other = original / "other"
        unrelated = other / self.root.name / "api-receipt.json"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text("unrelated")
        current = Path.cwd()
        try:
            os.chdir(original)
            self.root = Path(self.root.name)
            session = self.session()
            os.chdir(other)
            self.assertEqual(session.post(b"request")["response"], b"ok")
        finally:
            os.chdir(current)
        self.assertEqual(unrelated.read_text(), "unrelated")
        self.assertEqual(len(read_json(original / self.root / "api-receipt.json")["attempts"]), 1)

    def test_interruption_seals_started_attempt(self):
        session = self.session()
        with (
            patch("http.client.HTTPConnection.request", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            session.post(b"secret")
        receipt = read_json(self.root / "api-receipt.json")
        self.assertEqual(receipt["state"], "UNRESOLVED")
        self.assertEqual(receipt["attempts"][0]["state"], "OUTCOME_UNKNOWN")

    def test_interim_response_is_not_retryable_final_failure(self):
        self.responses.append((200, b"actual result", "early-hints"))
        session = self.session()
        with self.assertRaisesRegex(LabError, "unknown"):
            session.post(b"request")
        receipt = read_json(self.root / "api-receipt.json")
        self.assertEqual(receipt["state"], "UNRESOLVED")
        self.assertEqual(receipt["attempts"][0]["http_status"], 103)
        with self.assertRaisesRegex(LabError, "unresolved"):
            session.post(b"request", retry_of=0)
        self.assertEqual(len(self.requests), 1)

    def test_socket_timeout_with_pending_local_response(self):
        self.responses.append((200, b"delayed", "hold"))
        session = self.session(io_timeout=0.05)
        try:
            with self.assertRaisesRegex(LabError, "unknown") as failure:
                session.post(b"request")
            self.assertIsInstance(failure.exception.__cause__, TimeoutError)
        finally:
            self.release_response.set()
        self.assertEqual(read_json(self.root / "api-receipt.json")["state"], "UNRESOLVED")

    def test_partial_body_timeout_closes_server_socket_with_error_retained(self):
        self.responses.append((200, b"partial", "hold-body"))
        session = self.session(io_timeout=0.05)
        try:
            session.post(b"request")
        except LabError as exc:
            failure = exc
        else:
            self.fail("partial response should time out")
        self.assertIsInstance(failure.__cause__, TimeoutError)
        self.assertTrue(self.observed_eof.wait(1))
        self.assertEqual(read_json(self.root / "api-receipt.json")["state"], "UNRESOLVED")
