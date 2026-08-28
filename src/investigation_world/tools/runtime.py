from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.core.models import (
    CanonicalWorld,
    InvestigationResult,
    PublicDocument,
    SourceType,
    VerificationResult,
)
from investigation_world.search.index import FrozenSearchIndex
from investigation_world.tasks.spec import TaskOracle, TaskSpec
from investigation_world.tools.budget import BudgetManager
from investigation_world.verifier.aggregate import verify


class InvestigationEpisode(BaseModel):
    """Privileged executable investigation episode."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    world: CanonicalWorld
    task: TaskSpec
    oracle: TaskOracle
    total_cost: int = Field(default=40, ge=1)
    max_tool_calls: int = Field(default=30, ge=1)

    def public_payload(self) -> dict[str, Any]:
        return {
            "task": self.task.model_dump(mode="json"),
            "budget": {
                "total_cost": self.total_cost,
                "max_tool_calls": self.max_tool_calls,
            },
        }

    def runtime(self) -> "InvestigationRuntime":
        return InvestigationRuntime(self)


class InvestigationRuntime:
    """Single in-process implementation of public Investigation World semantics."""

    def __init__(self, episode: InvestigationEpisode):
        if episode.task.world_id != episode.world.world_id:
            raise ValueError("task/world mismatch")
        if episode.task.task_id != episode.oracle.task_id:
            raise ValueError("task/oracle mismatch")
        episode.world.validate()
        self.episode = episode
        self.index = FrozenSearchIndex()
        self.index.build(episode.world)
        self.budget = BudgetManager(
            total_cost=episode.total_cost,
            max_tool_calls=episode.max_tool_calls,
        )
        self.closed = False
        self.opened_document_ids: list[str] = []
        self.query_log: list[dict[str, Any]] = []
        self.final_result: InvestigationResult | None = None
        self.verification: VerificationResult | None = None

    @property
    def task(self) -> TaskSpec:
        return self.episode.task

    def _ensure_open(self) -> None:
        if self.closed:
            raise ValueError("episode already submitted")

    def _charge(self, tool: str) -> None:
        self._ensure_open()
        self.budget.charge(tool)

    def _search(
        self,
        tool: str,
        query: str,
        *,
        limit: int,
        source_types: list[SourceType] | None = None,
    ) -> list[dict[str, Any]]:
        self._charge(tool)
        results = self.index.search(query, limit=limit, source_types=source_types)
        self.query_log.append(
            {
                "tool": tool,
                "query": query,
                "limit": limit,
                "source_types": [
                    source_type.value for source_type in (source_types or [])
                ],
                "result_document_ids": [
                    str(item.get("document_id"))
                    for item in results
                    if item.get("document_id")
                ],
            }
        )
        return results

    def web_search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        return self._search(
            "web_search",
            query,
            limit=limit,
            source_types=[
                SourceType.NEWS,
                SourceType.COMPANY_SITE,
                SourceType.DIRECTORY,
            ],
        )

    def document_search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        return self._search("document_search", query, limit=limit)

    def registry_search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        return self._search(
            "registry_search",
            query,
            limit=limit,
            source_types=[SourceType.REGISTRY],
        )

    def filing_search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        return self._search(
            "filing_search",
            query,
            limit=limit,
            source_types=[SourceType.FILING],
        )

    def archive_search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        return self._search(
            "archive_lookup",
            query,
            limit=limit,
            source_types=[SourceType.ARCHIVE],
        )

    def open_document(self, document_id: str) -> dict[str, Any]:
        self._charge("open_page")
        document = next(
            (
                candidate
                for candidate in self.episode.world.documents
                if candidate.document_id == document_id
            ),
            None,
        )
        if document is None:
            raise KeyError(f"document not found: {document_id}")
        source_types = {
            source.source_id: source.source_type
            for source in self.episode.world.sources
        }
        public = PublicDocument(
            document_id=document.document_id,
            title=document.title,
            body=document.body,
            published_at=document.published_at,
            source_type=source_types.get(
                document.source_id,
                SourceType.DIRECTORY,
            ),
            url=document.url,
            cites_document_ids=document.cites_document_ids,
        )
        if document_id not in self.opened_document_ids:
            self.opened_document_ids.append(document_id)
        return public.model_dump(mode="json")

    def budget_snapshot(self) -> dict[str, Any]:
        return self.budget.snapshot()

    def state_snapshot(self) -> dict[str, Any]:
        """Public execution state only; canonical truth and oracle are excluded."""
        return {
            "task_id": self.task.task_id,
            "budget": self.budget_snapshot(),
            "opened_document_ids": list(self.opened_document_ids),
            "query_count": len(self.query_log),
            "submitted": self.closed,
        }

    def submit(self, result: InvestigationResult | dict[str, Any]) -> VerificationResult:
        self._ensure_open()
        if not isinstance(result, InvestigationResult):
            result = InvestigationResult.model_validate(result)
        budget = self.budget_snapshot()
        verification = VerificationResult.model_validate(
            verify(
                result,
                self.episode.world,
                task=self.episode.task,
                oracle=self.episode.oracle,
                budget_spent=int(budget["spent"]),
                budget_total=int(budget["total_cost"]),
            )
        )
        self.final_result = result
        self.verification = verification
        self.closed = True
        return verification

    def close(self) -> None:
        self.index.db.close()

    def __enter__(self) -> "InvestigationRuntime":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
