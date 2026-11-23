from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from secrets import compare_digest
from threading import Lock
from time import monotonic
from typing import Annotated, Any, Callable
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from starlette._utils import get_route_path
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from investigation_world import __version__
from investigation_world.core.models import (
    CanonicalWorld,
    InvestigationResult,
)
from investigation_world.tasks.spec import TaskOracle, TaskSpec, generate_task_bundle
from investigation_world.tools.runtime import InvestigationEpisode, InvestigationRuntime
from investigation_world.trajectories.recorder import TrajectoryRecorder
from investigation_world.trajectories.schema import Trajectory

MAX_EPISODES = 16
EPISODE_IDLE_SECONDS = 3600
MAX_ADMIN_BODY = 8 * 1024 * 1024
MAX_AGENT_BODY = 256 * 1024
BODY_TIMEOUT_SECONDS = 15


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        with _EPISODES_LOCK:
            sessions = list(_EPISODES.values())
            _EPISODES.clear()
        for session in sessions:
            with session.lock:
                session.removed = True
                session.runtime.close()


class _RequestLimits:
    """Bound bytes before JSON parsing, including chunked/understated bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def reject(status: int, detail: str) -> None:
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)

        if len(scope.get("query_string", b"")) > 16384 or len(scope.get("path", "")) > 4096:
            await reject(414, "request URL is too long")
            return
        headers = list(scope.get("headers", []))
        admin = get_route_path(scope).startswith("/admin/")
        if admin:
            token = next((v for k, v in headers if k.lower() == b"x-veritas-admin-token"), None)
            try:
                _require_admin(token.decode("latin-1") if token is not None else None)
            except HTTPException as error:
                await reject(error.status_code, str(error.detail))
                return
        limit = MAX_ADMIN_BODY if admin else MAX_AGENT_BODY
        lengths = [value for key, value in headers if key.lower() == b"content-length"]
        if lengths:
            raw = lengths[0]
            if len(lengths) != 1 or len(raw) > 20 or not raw.isdigit():
                await reject(400, "invalid Content-Length")
                return
            if int(raw) > limit:
                await reject(413, "request body exceeds the supported limit")
                return
        body = bytearray()
        try:
            async with asyncio.timeout(BODY_TIMEOUT_SECONDS):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > limit:
                        await reject(413, "request body exceeds the supported limit")
                        return
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await reject(408, "request body timed out")
            return
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def private_send(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [
                    *message.get("headers", []), (b"cache-control", b"no-store"),
                ]}
            await send(message)

        await self.app(scope, bounded_receive, private_send)


app = FastAPI(title="Investigation World", version=__version__, lifespan=_lifespan)
app.add_middleware(_RequestLimits)


class EpisodeCreateRequest(BaseModel):
    """Privileged orchestration request. This endpoint is not an agent tool."""

    model_config = ConfigDict(extra="forbid")
    world: CanonicalWorld
    task: TaskSpec | None = None
    oracle: TaskOracle | None = None
    task_seed: int = 0
    task_index: int = Field(default=0, ge=0, le=255)
    total_cost: int = Field(default=40, ge=1, le=1024)
    max_tool_calls: int = Field(default=30, ge=1, le=256)


@dataclass
class EpisodeSession:
    episode_id: str
    runtime: InvestigationRuntime
    recorder: TrajectoryRecorder
    trajectory: Trajectory | None = None
    lock: Any = field(default_factory=Lock, repr=False)
    last_access: float = field(default_factory=monotonic)
    removed: bool = False


_EPISODES: dict[str, EpisodeSession] = {}
_EPISODES_LOCK = Lock()


def _reap_expired() -> None:
    now = monotonic()
    with _EPISODES_LOCK:
        for identifier, session in list(_EPISODES.items()):
            if now - session.last_access < EPISODE_IDLE_SECONDS:
                continue
            if not session.lock.acquire(blocking=False):
                continue
            try:
                if now - session.last_access >= EPISODE_IDLE_SECONDS:
                    session.removed = True
                    session.runtime.close()
                    del _EPISODES[identifier]
            finally:
                session.lock.release()


@contextmanager
def _session_access(session: EpisodeSession) -> Iterator[None]:
    with session.lock:
        if session.removed:
            raise HTTPException(404, "episode not found")
        session.last_access = monotonic()
        try:
            yield
        finally:
            session.last_access = monotonic()


@app.get("/healthz")
def healthz():
    _reap_expired()
    with _EPISODES_LOCK:
        count = len(_EPISODES)
    return {"status": "ok", "version": app.version, "episodes": count, "capacity": MAX_EPISODES}


@app.get("/readyz")
def readyz():
    payload = healthz()
    ready = bool(os.getenv("VERITAS_ADMIN_TOKEN"))
    return JSONResponse(
        {**payload, "status": "ready" if ready else "admin_not_configured"},
        status_code=200 if ready else 503,
    )


def _require_admin(
    x_veritas_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = os.getenv("VERITAS_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(
            503,
            "admin API disabled: VERITAS_ADMIN_TOKEN is not configured",
        )
    if x_veritas_admin_token is None or not compare_digest(
        x_veritas_admin_token.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        raise HTTPException(401, "invalid admin token")


def _episode(episode_id: str) -> EpisodeSession:
    _reap_expired()
    with _EPISODES_LOCK:
        session = _EPISODES.get(episode_id)
    if session is None:
        raise HTTPException(404, "episode not found")
    return session


def _run_tool(
    session: EpisodeSession,
    recorder_tool: str,
    function: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    with _session_access(session):
        try:
            result = function(*args, **kwargs)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            message = str(error)
            status = 429 if "budget exhausted" in message else 409
            raise HTTPException(status, message) from error
        session.recorder.tool_call(
            recorder_tool,
            {
                "args": list(args),
                "kwargs": kwargs,
                "result": result,
            },
        )
        return result


@app.post("/admin/episodes")
def create_episode(
    request: EpisodeCreateRequest,
    _admin: None = Depends(_require_admin),
):
    """Create an isolated episode from privileged state without exposing filesystem access."""
    _reap_expired()
    # Creation is serialized so simultaneous requests cannot overbook capacity.
    # ponytail: one process/16 ephemeral episodes; distributed persistence belongs
    # in an external orchestrator rather than duplicating a service backend here.
    with _EPISODES_LOCK:
        if len(_EPISODES) >= MAX_EPISODES:
            raise HTTPException(503, "episode capacity exhausted; finalize and delete a session")
        try:
            request.world.validate()
        except (AssertionError, ValueError) as error:
            raise HTTPException(400, "invalid world invariants") from error
        if (request.task is None) != (request.oracle is None):
            raise HTTPException(400, "task and oracle must be supplied together")
        if request.task is None or request.oracle is None:
            try:
                bundle = generate_task_bundle(
                    request.world,
                    count=request.task_index + 1,
                    seed=request.task_seed,
                )
                instance = bundle[request.task_index]
            except (ValueError, IndexError) as error:
                raise HTTPException(400, "world cannot supply the requested task") from error
            task = instance.public
            oracle = instance.oracle
        else:
            task = request.task
            oracle = request.oracle
        if task.world_id != request.world.world_id:
            raise HTTPException(400, "task/world mismatch")
        if task.task_id != oracle.task_id:
            raise HTTPException(400, "task/oracle mismatch")

        episode_id = uuid4().hex
        runtime = InvestigationEpisode(
            world=request.world,
            task=task,
            oracle=oracle,
            total_cost=request.total_cost,
            max_tool_calls=request.max_tool_calls,
        ).runtime()
        recorder = TrajectoryRecorder(
            run_id=episode_id,
            task_id=task.task_id,
            world_id=request.world.world_id,
            world_seed=request.world.seed,
            objective=task.objective,
            agent_metadata={"api_version": app.version},
        )
        _EPISODES[episode_id] = EpisodeSession(
            episode_id=episode_id,
            runtime=runtime,
            recorder=recorder,
        )
        return {
            "episode_id": episode_id,
            "task": task.model_dump(mode="json"),
        }


@app.delete("/admin/episodes/{episode_id}")
def delete_episode(
    episode_id: str,
    _admin: None = Depends(_require_admin),
):
    session = _episode(episode_id)
    with session.lock:
        with _EPISODES_LOCK:
            if _EPISODES.get(episode_id) is not session:
                raise HTTPException(404, "episode not found")
            session.removed = True
            session.runtime.close()
            del _EPISODES[episode_id]
    return {"deleted": True}


@app.get("/admin/episodes/{episode_id}/trajectory")
def get_trajectory(
    episode_id: str,
    _admin: None = Depends(_require_admin),
):
    session = _episode(episode_id)
    with _session_access(session):
        trajectory = session.trajectory or session.recorder.t
        return trajectory.model_dump(mode="json")


@app.get("/episodes/{episode_id}/task")
def get_task(episode_id: str):
    session = _episode(episode_id)
    with _session_access(session):
        return session.runtime.task.model_dump(mode="json")


@app.post("/episodes/{episode_id}/search/web")
def web_search(
    episode_id: str, query: Annotated[str, Query(max_length=4096)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    session = _episode(episode_id)
    return _run_tool(
        session,
        "web_search",
        session.runtime.web_search,
        query,
        limit=limit,
    )


@app.post("/episodes/{episode_id}/search/documents")
def document_search(
    episode_id: str, query: Annotated[str, Query(max_length=4096)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    session = _episode(episode_id)
    return _run_tool(
        session,
        "document_search",
        session.runtime.document_search,
        query,
        limit=limit,
    )


@app.post("/episodes/{episode_id}/registry/search")
def registry_search(
    episode_id: str, query: Annotated[str, Query(max_length=4096)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    session = _episode(episode_id)
    return _run_tool(
        session,
        "registry_search",
        session.runtime.registry_search,
        query,
        limit=limit,
    )


@app.post("/episodes/{episode_id}/filings/search")
def filing_search(
    episode_id: str, query: Annotated[str, Query(max_length=4096)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    session = _episode(episode_id)
    return _run_tool(
        session,
        "filing_search",
        session.runtime.filing_search,
        query,
        limit=limit,
    )


@app.post("/episodes/{episode_id}/archive/search")
def archive_search(
    episode_id: str, query: Annotated[str, Query(max_length=4096)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    session = _episode(episode_id)
    return _run_tool(
        session,
        "archive_lookup",
        session.runtime.archive_search,
        query,
        limit=limit,
    )


@app.get("/episodes/{episode_id}/documents/{document_id}")
def get_document(episode_id: str, document_id: str):
    session = _episode(episode_id)
    return _run_tool(
        session,
        "open_page",
        session.runtime.open_document,
        document_id,
    )


@app.get("/episodes/{episode_id}/budget")
def get_budget(episode_id: str):
    session = _episode(episode_id)
    with _session_access(session):
        return session.runtime.budget_snapshot()


@app.post("/episodes/{episode_id}/submit")
def submit(episode_id: str, result: InvestigationResult):
    session = _episode(episode_id)
    with _session_access(session):
        try:
            verification = session.runtime.submit(result)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        payload = verification.model_dump(mode="json")
        session.recorder.action(
            {
                "action_type": "submit",
                "payload": result.model_dump(mode="json"),
            }
        )
        session.trajectory = session.recorder.finish(
            findings=result.model_dump(mode="json"),
            verifier_result=payload,
            budget=session.runtime.budget_snapshot(),
        )
        return payload
