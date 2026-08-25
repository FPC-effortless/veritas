from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from investigation_world.core.models import CanonicalWorld, InvestigationResult, PublicDocument, SourceType
from investigation_world.search.index import FrozenSearchIndex
from investigation_world.tasks.spec import TaskOracle, TaskSpec, generate_task_bundle
from investigation_world.tools.budget import BudgetManager
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


_EPISODES: dict[str, EpisodeSession] = {}


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
def create_episode(request: EpisodeCreateRequest):
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
    )
    return {"episode_id": episode_id, "task": task.model_dump(mode="json")}


@app.delete("/admin/episodes/{episode_id}")
def delete_episode(episode_id: str):
    session = _EPISODES.pop(episode_id, None)
    if session is None:
        raise HTTPException(404, "episode not found")
    session.search_index.db.close()
    return {"deleted": True}


@app.get("/episodes/{episode_id}/task")
def get_task(episode_id: str):
    return _episode(episode_id).task.model_dump(mode="json")


@app.post("/episodes/{episode_id}/search/web")
def web_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    _charge(session, "web_search")
    return session.search_index.search(
        query,
        limit,
        source_types=[SourceType.NEWS, SourceType.COMPANY_SITE, SourceType.DIRECTORY],
    )


@app.post("/episodes/{episode_id}/search/documents")
def document_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    _charge(session, "document_search")
    return session.search_index.search(query, limit)


@app.post("/episodes/{episode_id}/registry/search")
def registry_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    _charge(session, "registry_search")
    return session.search_index.search(query, limit, source_types=[SourceType.REGISTRY])


@app.post("/episodes/{episode_id}/filings/search")
def filing_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    _charge(session, "filing_search")
    return session.search_index.search(query, limit, source_types=[SourceType.FILING])


@app.post("/episodes/{episode_id}/archive/search")
def archive_search(episode_id: str, query: str, limit: int = 10):
    session = _episode(episode_id)
    _charge(session, "archive_lookup")
    return session.search_index.search(query, limit, source_types=[SourceType.ARCHIVE])


@app.get("/episodes/{episode_id}/documents/{document_id}")
def get_document(episode_id: str, document_id: str):
    session = _episode(episode_id)
    _charge(session, "open_page")
    return _public_document(session, document_id).model_dump(mode="json")


@app.get("/episodes/{episode_id}/budget")
def get_budget(episode_id: str):
    return _episode(episode_id).budget.snapshot()


@app.post("/episodes/{episode_id}/submit")
def submit(episode_id: str, result: InvestigationResult):
    session = _episode(episode_id)
    return verify(
        result,
        session.world,
        task=session.task,
        oracle=session.oracle,
        budget_spent=session.budget.budget.spent,
        budget_total=session.budget.budget.total_cost,
    )
