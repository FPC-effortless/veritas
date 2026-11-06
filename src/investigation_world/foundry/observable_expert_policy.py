from __future__ import annotations

from typing import Any

from investigation_world.foundry.external_runtime import ExternalInvestigationEpisode
from investigation_world.foundry.trajectory_generation import (
    OracleExpertPolicy,
    _supporting_documents,
)
from investigation_world.tasks.spec import TaskFamily


class ObservableOracleExpertPolicy(OracleExpertPolicy):
    """Privileged teacher whose recorded tool path is executable from its observations.

    Hidden truth may choose which evidence is worth seeking, but the policy cannot open a
    document merely because it knows the private document ID. Except for document IDs
    explicitly supplied by a provenance task, an ID must first appear in a public search
    result. This makes the resulting demonstrations behaviorally realizable by a student.
    """

    policy_id = "oracle-observable-expert-v1"

    @staticmethod
    def _remember(results: Any, discovered: set[str]) -> None:
        if not isinstance(results, list):
            return
        for result in results:
            if isinstance(result, dict) and result.get("document_id"):
                discovered.add(str(result["document_id"]))

    @staticmethod
    def _remaining_budget(runtime: Any) -> int:
        snapshot = runtime.budget_snapshot()
        if not isinstance(snapshot, dict):
            return 0
        return int(snapshot.get("total_cost", 0)) - int(snapshot.get("spent", 0))

    def _retrieve(
        self,
        runtime: Any,
        episode: ExternalInvestigationEpisode,
    ) -> list[str]:
        task = episode.task
        supporting = _supporting_documents(
            episode,
            maximum=self.max_documents,
        )
        discovered: set[str] = set()

        def search(method: str, query: str, *, limit: int = 100) -> None:
            results = getattr(runtime, method)(query, limit=limit)
            self._remember(results, discovered)

        refs = [reference for reference in task.target_refs if reference][:3]
        for reference in refs:
            search("document_search", reference)
        if refs and task.family in {
            TaskFamily.OWNERSHIP,
            TaskFamily.CONFLICT,
            TaskFamily.DUE_DILIGENCE,
        }:
            search("registry_search", refs[0])
            search("filing_search", refs[0])
        elif refs and task.family == TaskFamily.TEMPORAL:
            search("archive_search", refs[0])
        elif refs and task.family == TaskFamily.ENTITY_RESOLUTION:
            search("web_search", refs[0])

        explicitly_supplied = (
            set(task.target_refs)
            if task.family == TaskFamily.PROVENANCE
            else set()
        )
        documents = {
            document.document_id: document for document in episode.world.documents
        }
        opened: list[str] = []

        for document_id in supporting:
            if document_id not in discovered and document_id not in explicitly_supplied:
                # A privileged teacher may know the best retrieval query, but the document
                # ID itself still has to become observable before it can be opened.
                document = documents.get(document_id)
                if document is not None and self._remaining_budget(runtime) >= 3:
                    title_subject = document.title.split(":", 1)[-1].strip()
                    query = title_subject or document.title
                    search("document_search", query)

            if document_id not in discovered and document_id not in explicitly_supplied:
                continue
            if self._remaining_budget(runtime) < 1:
                break
            runtime.open_document(document_id)
            opened.append(document_id)

        return opened


__all__ = ["ObservableOracleExpertPolicy"]
