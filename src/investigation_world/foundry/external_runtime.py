from __future__ import annotations

from typing import Any

from investigation_world.foundry.models import FoundryTaskMetadata
from investigation_world.tools.runtime import InvestigationEpisode, InvestigationRuntime


class ExternalInvestigationEpisode(InvestigationEpisode):
    """Foundry-scoped investigation episode with split/difficulty metadata."""

    metadata: FoundryTaskMetadata

    def public_payload(self) -> dict[str, Any]:
        payload = super().public_payload()
        task_metadata = payload.get("task", {}).get("metadata")
        if isinstance(task_metadata, dict):
            task_metadata.pop("generator_seed", None)
        # Agent-facing payloads exclude split assignment, replay seeds, mutation seeds and
        # generator parameters. Operators retain all of them in the private bundle.
        payload["foundry"] = {
            "task_id": self.metadata.task_id,
            "capability_tags": list(self.metadata.capability_tags),
            "difficulty": self.metadata.difficulty.model_dump(mode="json"),
            "taskset_version": self.metadata.taskset_version,
            "harness_version": self.metadata.harness_version,
            "runtime_version": self.metadata.runtime_version,
            "parent_task_id": self.metadata.parent_task_id,
        }
        return payload

    def runtime(self) -> InvestigationRuntime:
        return InvestigationRuntime(self)


ExternalInvestigationRuntime = InvestigationRuntime

__all__ = [
    "ExternalInvestigationEpisode",
    "ExternalInvestigationRuntime",
]
