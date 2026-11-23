from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from investigation_world import __version__
from investigation_world.evidence.projector import project
from investigation_world.tools import server
from investigation_world.world.generator import WorldFactory, WorldGenerationConfig

AUTH = {"x-veritas-admin-token": "constructed-test-token"}


async def _asgi_request(
    method, url, *, payload=None, headers=None, chunks=None, root_path="", body_reads=None,
):
    parsed = urlsplit(url)
    body = json.dumps(payload).encode() if payload is not None else b""
    source = list(chunks) if chunks is not None else [body]
    messages = []
    supplied_headers = {"content-type": "application/json", **(headers or {})}
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "root_path": root_path, "path": parsed.path,
        "raw_path": parsed.path.encode(), "query_string": parsed.query.encode(),
        "headers": [(key.encode(), value.encode()) for key, value in supplied_headers.items()],
        "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 8000),
    }

    async def receive():
        if body_reads is not None:
            body_reads.append(True)
        if source:
            chunk = source.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(source)}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await server.app(scope, receive, send)
    status = next(row["status"] for row in messages if row["type"] == "http.response.start")
    encoded = b"".join(row.get("body", b"") for row in messages)
    return status, json.loads(encoded) if encoded else None


def request(method, url, **kwargs):
    return asyncio.run(_asgi_request(method, url, **kwargs))


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch):
    monkeypatch.setenv("VERITAS_ADMIN_TOKEN", AUTH["x-veritas-admin-token"])
    yield
    for session in list(server._EPISODES.values()):
        session.runtime.close()
    server._EPISODES.clear()


@pytest.fixture
def world():
    return project(WorldFactory.generate(
        17, WorldGenerationConfig(num_people=24, num_organizations=12, num_addresses=12),
    ), seed=17)[0]


def create(world):
    status, payload = request(
        "POST", "/admin/episodes", headers=AUTH,
        payload={"world": world.model_dump(mode="json"), "task_seed": 1},
    )
    assert status == 200, payload
    return payload["episode_id"]


def test_health_binds_software_identity_and_readiness_requires_admin(monkeypatch):
    status, payload = request("GET", "/healthz")
    assert status == 200
    assert payload["version"] == __version__
    monkeypatch.delenv("VERITAS_ADMIN_TOKEN")
    assert request("GET", "/readyz")[0] == 503
    monkeypatch.setenv("VERITAS_ADMIN_TOKEN", AUTH["x-veritas-admin-token"])
    assert request("GET", "/readyz")[0] == 200


@pytest.mark.parametrize("field", ["task_index", "total_cost", "max_tool_calls"])
def test_creation_rejects_unbounded_work(world, field):
    with pytest.raises(ValidationError):
        server.EpisodeCreateRequest(world=world, **{field: 10**9})


def test_capacity_returns_backpressure_and_delete_frees_slot(world, monkeypatch):
    monkeypatch.setattr(server, "MAX_EPISODES", 1)
    identifier = create(world)
    status, _ = request("POST", "/admin/episodes", headers=AUTH,
                        payload={"world": world.model_dump(mode="json")})
    assert status == 503
    assert len(server._EPISODES) == 1
    assert request("DELETE", f"/admin/episodes/{identifier}", headers=AUTH)[0] == 200
    assert create(world) != identifier


def test_concurrent_delete_cannot_leave_tool_using_closed_database(world, monkeypatch):
    identifier = create(world)
    original = server._episode
    selected = threading.Event()
    proceed = threading.Event()
    responses = []

    def paused_lookup(value):
        session = original(value)
        if selected.is_set():
            return session
        selected.set()
        if not proceed.wait(5):
            raise RuntimeError("test barrier timed out")
        return session

    monkeypatch.setattr(server, "_episode", paused_lookup)
    worker = threading.Thread(target=lambda: responses.append(request(
        "POST", f"/episodes/{identifier}/search/web?query=Aster",
    )))
    worker.start()
    try:
        assert selected.wait(5)
        assert request("DELETE", f"/admin/episodes/{identifier}", headers=AUTH)[0] == 200
    finally:
        proceed.set()
        worker.join(5)
    assert not worker.is_alive()
    assert responses and responses[0][0] == 404


def test_deletion_does_not_free_capacity_before_busy_session_is_closed(world, monkeypatch):
    monkeypatch.setattr(server, "MAX_EPISODES", 1)
    identifier = create(world)
    session = server._EPISODES[identifier]
    underlying = session.lock
    waiting = threading.Event()

    class ObservedLock:
        def __enter__(self):
            waiting.set()
            underlying.acquire()

        def __exit__(self, *_):
            underlying.release()

    session.lock = ObservedLock()
    underlying.acquire()
    worker = threading.Thread(target=lambda: server.delete_episode(identifier))
    worker.start()
    try:
        assert waiting.wait(5)
        assert identifier in server._EPISODES
        status, _ = request("POST", "/admin/episodes", headers=AUTH,
                            payload={"world": world.model_dump(mode="json")})
        assert status == 503
    finally:
        underlying.release()
        worker.join(5)
    assert not worker.is_alive()
    assert identifier not in server._EPISODES
    assert session.removed


def test_idle_expiry_and_lifespan_shutdown_close_sessions(world, monkeypatch):
    identifier = create(world)
    session = server._EPISODES[identifier]
    monkeypatch.setattr(server, "EPISODE_IDLE_SECONDS", 1)
    session.last_access -= 2
    assert request("GET", f"/episodes/{identifier}/task")[0] == 404
    assert session.removed

    async def lifecycle():
        async with server.app.router.lifespan_context(server.app):
            second = server.create_episode(server.EpisodeCreateRequest(world=world))["episode_id"]
            return server._EPISODES[second]

    second_session = asyncio.run(lifecycle())
    assert second_session.removed
    assert not server._EPISODES


@pytest.mark.parametrize("headers", [{}, {"content-length": "0"}])
def test_actual_body_bytes_are_bounded_without_trusting_content_length(headers):
    status, _ = request(
        "POST", "/episodes/constructed/submit", headers=headers,
        chunks=[b"a" * (128 * 1024), b"b" * (129 * 1024)],
    )
    assert status == 413


def test_oversized_admin_body_and_invalid_lengths_are_rejected_early():
    assert request("POST", "/admin/episodes", headers={
        **AUTH, "content-length": str(9 * 1024 * 1024),
    })[0] == 413
    assert request("POST", "/admin/episodes", headers={**AUTH, "content-length": "bad"})[0] == 400
    # Authentication is decided before body parsing, even for malformed input.
    assert request("POST", "/admin/episodes", chunks=[b"not-json"])[0] == 401


def test_mounted_admin_route_keeps_early_auth_and_admin_body_limit():
    reads = []
    status, _ = request(
        "POST", "/veritas/admin/episodes", root_path="/veritas",
        chunks=[b"not-json"], body_reads=reads,
    )
    assert status == 401
    assert reads == []
    # A validly authenticated 300 KiB request reaches schema validation under
    # the 8 MiB admin limit; it must not be cut off by the 256 KiB agent limit.
    status, _ = request(
        "POST", "/veritas/admin/episodes", root_path="/veritas", headers=AUTH,
        payload={"constructed_invalid_field": "a" * (300 * 1024)},
    )
    assert status == 422
    assert request("GET", "/veritas-other/admin/episodes", root_path="/veritas")[0] == 404


def test_query_bounds_and_invalid_world_are_client_errors(world):
    identifier = create(world)
    assert request("POST", f"/episodes/{identifier}/search/web?query=" + "a" * 4097)[0] == 422
    invalid = world.model_dump(mode="json")
    invalid["relationships"][0]["subject_id"] = "constructed-missing-entity"
    assert request("POST", "/admin/episodes", headers=AUTH, payload={"world": invalid})[0] == 400


def test_stale_reference_is_rejected_by_every_session_reader(world):
    identifier = create(world)
    session = server._EPISODES[identifier]
    server.delete_episode(identifier)
    with pytest.raises(HTTPException) as error:
        with server._session_access(session):
            raise AssertionError("stale session reached body")
    assert error.value.status_code == 404


def test_optimized_python_retains_world_invariants_and_api_rejection():
    code = """
import asyncio
from datetime import date
from fastapi import HTTPException
from investigation_world.core.models import CanonicalWorld, Relationship, Predicate
from investigation_world.tools.server import app, create_episode, EpisodeCreateRequest
world = CanonicalWorld(world_id='constructed', seed=0, relationships=[
    Relationship(relationship_id='r', subject_id='missing', object_id='also-missing',
                 predicate=Predicate.OWNS, valid_from=date(2020, 1, 1))
])
try:
    world.validate()
except AssertionError:
    pass
else:
    raise SystemExit('optimized world validation accepted a dangling relationship')
try:
    create_episode(EpisodeCreateRequest(world=world))
except HTTPException as error:
    if error.status_code != 400:
        raise SystemExit('wrong API rejection')
else:
    raise SystemExit('API accepted invalid world')
async def check():
    async with app.router.lifespan_context(app):
        pass
asyncio.run(check())
print('optimized validation and startup passed')
"""
    result = subprocess.run(
        [sys.executable, "-O", "-c", code], capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": str(Path(server.__file__).resolve().parents[2])},
    )
    assert result.returncode == 0, result.stderr
    assert "optimized validation and startup passed" in result.stdout


def test_container_enforces_one_worker_and_bounded_transport():
    dockerfile = Path("Dockerfile").read_text()
    command = json.loads(next(
        line[4:] for line in dockerfile.splitlines() if line.startswith("CMD ")
    ))
    assert command[command.index("--workers") + 1] == "1"
    assert command[command.index("--limit-concurrency") + 1] == "64"
    assert "--no-access-log" in command
