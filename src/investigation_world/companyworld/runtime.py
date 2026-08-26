from __future__ import annotations

import json
from collections import defaultdict

from investigation_world.companyworld.models import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldRecord,
    CompanyWorldVerificationResult,
)
from investigation_world.companyworld.verifier import verify_companyworld
from investigation_world.core.models import InvestigationBudget, InvestigationResult


SYSTEM_TOOL_COSTS = {
    CompanySystem.ERP: 1,
    CompanySystem.WMS: 2,
    CompanySystem.AP_WORKFLOW: 2,
    CompanySystem.AUTH_SERVICE: 2,
    CompanySystem.EMAIL: 2,
    CompanySystem.LEDGER: 3,
    CompanySystem.PROCESS: 2,
    CompanySystem.AR_WORKFLOW: 2,
    CompanySystem.TREASURY: 3,
    CompanySystem.ITSM: 2,
    CompanySystem.SAFETY: 2,
    CompanySystem.COMPLIANCE: 3,
}


class CompanyWorldRecordIndex:
    """Deterministic in-memory search over one compiled episode."""

    def __init__(self, records: list[CompanyWorldRecord]):
        self._records = {record.record_id: record for record in records}
        self._by_system: dict[CompanySystem, list[CompanyWorldRecord]] = defaultdict(list)
        self._search_text: dict[str, str] = {}
        for record in records:
            self._by_system[record.system].append(record)
            self._search_text[record.record_id] = " ".join(
                [
                    record.record_type,
                    record.object_type,
                    record.object_id,
                    *record.related_object_ids,
                    json.dumps(record.fields, sort_keys=True, default=str),
                ]
            ).casefold()

    def get(self, record_id: str) -> CompanyWorldRecord | None:
        return self._records.get(record_id)

    def search(
        self,
        query: str,
        *,
        system: CompanySystem | None = None,
        limit: int = 10,
    ) -> list[CompanyWorldRecord]:
        terms = [term.casefold() for term in query.split() if term.strip()]
        if not terms:
            return []
        candidates = self._by_system.get(system, []) if system else list(self._records.values())
        scored: list[tuple[int, str, CompanyWorldRecord]] = []
        for record in candidates:
            text = self._search_text[record.record_id]
            if not all(term in text for term in terms):
                continue
            score = sum(text.count(term) for term in terms)
            scored.append((score, record.record_id, record))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored[: max(1, min(limit, 100))]]


class CompanyWorldRuntime:
    """Executable, isolated CompanyWorld episode with budgeted system tools."""

    def __init__(
        self,
        episode: CompanyWorldEpisode,
        *,
        total_cost: int = 40,
        max_tool_calls: int = 30,
    ):
        self.episode = episode
        self.index = CompanyWorldRecordIndex(episode.records)
        self.budget = InvestigationBudget(total_cost=total_cost, max_tool_calls=max_tool_calls)
        self.closed = False

    def _ensure_open(self) -> None:
        if self.closed:
            raise ValueError("episode already submitted")

    def _charge(self, cost: int) -> None:
        self._ensure_open()
        self.budget.charge(cost)

    def search_system(
        self,
        system: CompanySystem,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        if system not in self.episode.task.permitted_systems:
            return []
        self._charge(SYSTEM_TOOL_COSTS[system])
        return [
            record.model_dump(mode="json")
            for record in self.index.search(query, system=system, limit=limit)
        ]

    def search(
        self,
        query: str,
        *,
        system: CompanySystem,
        limit: int = 10,
    ) -> list[dict]:
        """Keyword-friendly alias for the stable `search_system` API."""
        return self.search_system(system, query, limit=limit)

    def search_all(self, query: str, limit: int = 10) -> list[dict]:
        self._charge(3)
        return [
            record.model_dump(mode="json")
            for record in self.index.search(query, limit=limit)
        ]

    def open_record(self, record_id: str) -> dict:
        self._charge(1)
        record = self.index.get(record_id)
        if record is None:
            raise KeyError(record_id)
        return record.model_dump(mode="json")

    def budget_snapshot(self) -> dict:
        return self.budget.model_dump()

    def submit(self, result: InvestigationResult) -> CompanyWorldVerificationResult:
        self._ensure_open()
        verification = verify_companyworld(
            result,
            self.episode,
            budget_spent=self.budget.spent,
            budget_total=self.budget.total_cost,
        )
        self.closed = True
        return verification
