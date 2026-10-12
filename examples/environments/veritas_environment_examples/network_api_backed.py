from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen

from investigation_world.authoring import EnvironmentBuilder
from investigation_world.operational import ActionKind, WorldDomain

from ._common import execute_episode, require_perfect


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        payload = json.dumps({"service": "api", "status": "degraded", "target": "healthy"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def build_environment(base_url: str):
    with urlopen(f"{base_url}/health", timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8"))
    service = str(payload["service"])
    status = str(payload["status"])
    target = str(payload["target"])
    return (
        EnvironmentBuilder(
            name="network-api-backed",
            domain=WorldDomain.DEVOPS_INCIDENT_RESPONSE,
            objective="Recover a service using evidence fetched from an API.",
            role="site_reliability_engineer",
        )
        .system("API")
        .action(
            "recover_service",
            kind=ActionKind.EXECUTE,
            system="API",
            description="Recover the degraded service.",
            parameters=("service",),
        )
        .record(
            "api-rec-001",
            system="API",
            record_type="health_response",
            object_id=service,
            fields={"status": status, "target": target},
            searchable_text=f"{service} {status} {target}",
        )
        .initial_state(**{f"{service}.status": status})
        .target(service, "status", target)
        .transition(
            "recover_service",
            required_parameters={"service": service},
            set_state={f"{service}.status": target},
            observable_result={"accepted": True},
        )
        .require_action("recover_service")
        .require_evidence("api-rec-001")
        .metadata(public={"backend": "http_api"})
        .success("The API reports a recoverable service and runtime state reaches healthy.")
        .build()
    )


def run_demo():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        result = execute_episode(
            build_environment(f"http://{host}:{port}"),
            actions=(("recover_service", {"service": "api"}),),
            evidence_ids=("api-rec-001",),
            claimed_state={"api.status": "healthy"},
            conclusion="API evidence supported recovery of the service.",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return require_perfect(result)
