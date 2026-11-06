from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from investigation_world.authoring import EnvironmentBuilder
from investigation_world.operational import ActionKind, WorldDomain

from ._common import execute_episode, require_perfect


class SetStatusInput(BaseModel):
    """Typed adapter input validated before the runtime action is invoked."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: str


def build_environment():
    return (
        EnvironmentBuilder(
            name="minimal-typed-tool",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Set a queued job to ready using a validated typed tool input.",
            role="workflow_operator",
        )
        .system("QUEUE")
        .action(
            "set_status",
            kind=ActionKind.WRITE,
            system="QUEUE",
            description="Set the job status.",
            parameters=("job_id", "status"),
        )
        .record(
            "typed-rec-001",
            system="QUEUE",
            record_type="job",
            object_id="JOB-1",
            fields={"status": "queued"},
            searchable_text="JOB-1 queued",
        )
        .initial_state(**{"JOB-1.status": "queued"})
        .target("JOB-1", "status", "ready")
        .transition(
            "set_status",
            required_parameters={"job_id": "JOB-1", "status": "ready"},
            set_state={"JOB-1.status": "ready"},
            observable_result={"accepted": True},
        )
        .require_action("set_status")
        .require_evidence("typed-rec-001")
        .success("JOB-1 is ready.")
        .build()
    )


def run_demo():
    tool_input = SetStatusInput(job_id="JOB-1", status="ready")
    result = execute_episode(
        build_environment(),
        actions=(("set_status", tool_input.model_dump()),),
        evidence_ids=("typed-rec-001",),
        claimed_state={"JOB-1.status": "ready"},
        conclusion="Validated input moved JOB-1 to ready.",
    )
    return require_perfect(result)
