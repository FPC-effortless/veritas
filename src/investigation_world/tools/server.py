from __future__ import annotations

import os
from dataclasses import dataclass
from secrets import compare_digest
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from investigation_world.core.models import CanonicalWorld, InvestigationResult, PublicDocument, SourceType
from investigation_world.search.index import FrozenSearchIndex
from investigation_world.tasks.spec import TaskOracle, TaskSpec, generate_task_bundle
from investigation_world.tools.budget import BudgetManager
from investigation_world.trajectories.recorder import TrajectoryRecorder
from investigation_world.trajectories.schema import Trajectory
from investigation_world.verifier.aggregate import verify


app = FastAPI(title="Investigation World", version="0.4.0")


class EpisodeCreateRequest(BaseModel):
    """Privileged orchestration request. This endpoint is not an agent tool."""

    model_config = ConfigDict(extra="forbid")
    world: CanonicalWorld
    task: TaskSpec | None = None
    oracle: TaskOracle | None = None
    task_seed: int = 0
    task_index: int = 0
    total_cost: int = Field(default=40, ge=1)
    max_tool_calls: int = Field(default=30, ge=1)


@dataclass
class EpisodeSession:
    episode_id: str
    world: CanonicalWorld
    search_index: FrozenSearchIndex
    budget: BudgetManager
    task: TaskSpec
    oracle: TaskOracle
    recorder: TrajectoryRecorder
    trajectory: Trajectory | None = None


_EPISODES: dict[str, EpisodeSession] = {}


def _require_admin(
    x_veritas_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = os.getenv("VERITAS_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(503, "admin API disabled: VERITAS_ADMIN_TOKEN is not configured")
    if x_veritas_admin_token is None or not compare_digest(x_veritas_admin_token, expected):
        raise HTTPException(401, "invalid admin token")


def _episode(episode_id: str) -> EpisodeSession:
    session = _EPISODES.get(episode_id)
    if session is None:
        raise HTTPException(404, "episode not found")
    return session


def _charge(session: EpisodeSession, tool: str) -> None:
    try:
        session.budget.charge(tool)
    except ValueError as error:
        raise HTTPException(429, str(error)) from error


def _record_tool(session: EpisodeSession, tool: str, **observation) -> None:
    session.recorder.tool_call(tool, observation)


def _public_document(session: EpisodeSession, document_id: str) -> PublicDocument:
    document = next(
        (candidate for candidate in session.world.documents if candidate.document_id == document_id),
        None,
    )
    if document is None:
        raise HTTPException(404, "document not found")
    source_types = {source.source_id: source.source_type for source in session.world.sources}
    return PublicDocument(
        document_id=document.document_id,
        title=document.title,
        body=document.body,
        published_at=document.published_at,
        source_type=source_types.get(document.source_id, SourceType.DIRECTORY),
        url=document.url,
        cites_document_ids=document.cites_document_ids,
    )


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
            count=max(1, request.task_index + 1),
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
    search_index = FrozenSearchIndex()
    search_index.build(request.world)
    recorder = TrajectoryRecorder(
        run_id=episode_id,
        task_id=task.task_id,
        world_id=request.world.world_id,
        world_seed=request.world.seed,
        objective=task.objective,
        agent_metadata={"api_version": "0.4.0"},
    )
    _EPISODES[episode_id] = EpisodeSession(
        episode_id=episode_id,
        world=request.world,
        search_index=search_index,
        budget=BudgetManager(
            total_cost=request.total_cost,
            max_tool_calls=request.max_tool_calls,
        ),
        task=task,
        oracle=oracle,
        recorder=recorder,
    )
    return {"episode_id": episode_id, "task": task.model_dump(mode="json")}


@app.delete("/admin/episodes/{episode_id}")
def delete_episode(
    episode_id: str,
    _admin: None = Depends(_require_admin),
):
    session = _EPISODES.pop(episode_id, None)
    if session is None:
        raise HTTPException(404, "episode not found")
    session.search_index.db.close()
    return {"deleted": True}


@app.get("/admin/episodes/{episode_id}/trajectory")
def get_trajectory(
    episode_id: str,
    _admin: None = Depends(_require_admin),
):
    session = _episode(episode_id)
    trajectory = session.trajectory or session.recorder.t
    return trajectory.model_dump(mode="json")


@app.get("/episodes/{episode_id}/task")
def get_task(episode_id: str):
    return _episode(episode_id).task.model_dump(mode="json")


@app.post("/episodes/{episode_id}/search/web")
def web_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    _charge(session, "web_search")
    results = session.search_index.search(
        query,
        limit,
        source_types=[SourceType.NEWS, SourceType.COMPANY_SITE, SourceType.DIRECTORY],
    )
    _record_tool(session, "web_search", query=query, limit=limit, results=results)
    return results


@app.post("/episodes/{episode_id}/search/documents")
def document_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    _charge(session, "document_search")
    results = session.search_index.search(query, limit)
    _record_tool(session, "document_search", query=query, limit=limit, results=results)
    return results


@app.post("/episodes/{episode_id}/registry/search")
def registry_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    _charge(session, "registry_search")
    results = session.search_index.search(query, limit, source_types=[SourceType.REGISTRY])
    _record_tool(session, "registry_search", query=query, limit=limit, results=results)
    return results


@app.post("/episodes/{episode_id}/filings/search")
def filing_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    _charge(session, "filing_search")
    results = session.search_index.search(query, limit, source_types=[SourceType.FILING])
    _record_tool(session, "filing_search", query=query, limit=limit, results=results)
    return results


@app.post("/episodes/{episode_id}/archive/search")
def archive_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    _charge(session, "archive_lookup")
    results = session.search_index.search(query, limit, source_types=[SourceType.ARCHIVE])
    _record_tool(session, "archive_lookup", query=query, limit=limit, results=results)
    return results


@app.get("/episodes/{episode_id}/documents/{document_id}")
def get_document(episode_id: str, document_id: str):
    session = _episode(episode_id)
    _charge(session, "open_page")
    document = _public_document(session, document_id).model_dump(mode="json")
    _record_tool(session, "open_page", document_id=document_id, document=document)
    return document


@app.get("/episodes/{episode_id}/budget")
def get_budget(episode_id: str):
    return _episode(episode_id).budget.snapshot()


@app.post("/episodes/{episode_id}/submit")
def submit(episode_id: str, result: InvestigationResult):
    session = _episode(episode_id)
    verification = verify(
        result,
        session.world,
        task=session.task,
        oracle=session.oracle,
        budget_spent=session.budget.budget.spent,
        budget_total=session.budget.budget.total_cost,
    )
    session.recorder.action(
        {
            "action_type": "submit",
            "payload": result.model_dump(mode="json"),
        }
    )
    session.trajectory = session.recorder.finish(
        findings=result.model_dump(mode="json"),
        verifier_result=verification,
        budget=session.budget.snapshot(),
    )
    return verification
