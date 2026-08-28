from __future__ import annotations

import os
from dataclasses import dataclass, field
from secrets import compare_digest
from threading import Lock
from typing import Annotated, Any, Callable
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from investigation_world.core.models import (
    CanonicalWorld,
    InvestigationResult,
)
from investigation_world.tasks.spec import TaskOracle, TaskSpec, generate_task_bundle
from investigation_world.tools.runtime import InvestigationEpisode, InvestigationRuntime
from investigation_world.trajectories.recorder import TrajectoryRecorder
from investigation_world.trajectories.schema import Trajectory


app = FastAPI(title="Investigation World", version="0.5.0")


class EpisodeCreateRequest(BaseModel):
    """Privileged orchestration request. This endpoint is not an agent tool."""

    model_config = ConfigDict(extra="forbid")
    world: CanonicalWorld
    task: TaskSpec | None = None
    oracle: TaskOracle | None = None
    task_seed: int = 0
    task_index: int = Field(default=0, ge=0)
    total_cost: int = Field(default=40, ge=1)
    max_tool_calls: int = Field(default=30, ge=1)


@dataclass
class EpisodeSession:
    episode_id: str
    runtime: InvestigationRuntime
    recorder: TrajectoryRecorder
    trajectory: Trajectory | None = None
    lock: Any = field(default_factory=Lock, repr=False)


_EPISODES: dict[str, EpisodeSession] = {}


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": app.version}


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
        x_veritas_admin_token,
        expected,
    ):
        raise HTTPException(401, "invalid admin token")


def _episode(episode_id: str) -> EpisodeSession:
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
    with session.lock:
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
    request.world.validate()
    if (request.task is None) != (request.oracle is None):
        raise HTTPException(400, "task and oracle must be supplied together")
    if request.task is None or request.oracle is None:
        bundle = generate_task_bundle(
            request.world,
            count=request.task_index + 1,
            seed=request.task_seed,
        )
        instance = bundle[request.task_index]
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
        agent_metadata={"api_version": "0.5.0"},
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
    session = _EPISODES.pop(episode_id, None)
    if session is None:
        raise HTTPException(404, "episode not found")
    with session.lock:
        session.runtime.close()
    return {"deleted": True}


@app.get("/admin/episodes/{episode_id}/trajectory")
def get_trajectory(
    episode_id: str,
    _admin: None = Depends(_require_admin),
):
    session = _episode(episode_id)
    with session.lock:
        trajectory = session.trajectory or session.recorder.t
        return trajectory.model_dump(mode="json")


@app.get("/episodes/{episode_id}/task")
def get_task(episode_id: str):
    return _episode(episode_id).runtime.task.model_dump(mode="json")


@app.post("/episodes/{episode_id}/search/web")
def web_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    return _run_tool(
        session,
        "web_search",
        session.runtime.web_search,
        query,
        limit=limit,
    )


@app.post("/episodes/{episode_id}/search/documents")
def document_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    return _run_tool(
        session,
        "document_search",
        session.runtime.document_search,
        query,
        limit=limit,
    )


@app.post("/episodes/{episode_id}/registry/search")
def registry_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    return _run_tool(
        session,
        "registry_search",
        session.runtime.registry_search,
        query,
        limit=limit,
    )


@app.post("/episodes/{episode_id}/filings/search")
def filing_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    return _run_tool(
        session,
        "filing_search",
        session.runtime.filing_search,
        query,
        limit=limit,
    )


@app.post("/episodes/{episode_id}/archive/search")
def archive_search(episode_id: str, query: str, limit: int = 10):
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
    with session.lock:
        return session.runtime.budget_snapshot()


@app.post("/episodes/{episode_id}/submit")
def submit(episode_id: str, result: InvestigationResult):
    session = _episode(episode_id)
    with session.lock:
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
