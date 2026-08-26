from __future__ import annotations

from typing import Any

from investigation_world.projectworld.models import (
    ProjectAction,
    ProjectActionKind,
    ProjectObservation,
    ProjectTransition,
)
from investigation_world.projectworld.runtime import OperationalProjectWorld, ProjectActionError


class ProjectWorldSession:
    """Identity-bound model-facing interface for an ``OperationalProjectWorld``.

    The raw world supports privileged evaluator/orchestrator control across roles. Agent sessions do
    not: the actor identity is bound by the harness when the session is created and cannot be changed
    by model-generated action arguments.
    """

    def __init__(self, world: OperationalProjectWorld, actor_role_id: str):
        # Validate the binding eagerly against the authoritative world role registry.
        world._role(actor_role_id)
        self._world = world
        self.actor_role_id = actor_role_id

    @property
    def world(self) -> OperationalProjectWorld:
        return self._world

    def observe(self) -> ProjectObservation:
        return self._world.observe(self.actor_role_id)

    def act(
        self,
        kind: ProjectActionKind,
        *,
        target_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> ProjectTransition:
        """Execute an action using the session's immutable actor identity."""
        return self._world.step(
            ProjectAction(
                actor_role_id=self.actor_role_id,
                kind=kind,
                target_id=target_id,
                parameters=dict(parameters or {}),
            )
        )

    def step(self, action: ProjectAction) -> ProjectTransition:
        """Compatibility surface that rejects any attempted role impersonation."""
        if action.actor_role_id != self.actor_role_id:
            raise ProjectActionError(
                f"session identity {self.actor_role_id} cannot submit action as "
                f"{action.actor_role_id}"
            )
        return self._world.step(action)
