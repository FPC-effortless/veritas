"""Woyengi Work: a self-contained agent evaluation environment."""

from investigation_world.authoring import EnvironmentBuilder
from investigation_world.operational.models import (
    ActionKind,
    OperationalEpisode,
    StateAssertion,
    WorldDomain,
)

WORK_ID = "WORK-001"
EVIDENCE_ID = "work-handoff-001"


def build_woyengi_work_environment() -> OperationalEpisode:
    """Build a simulated evidence-gated handoff without a Woyengi service."""
    system = "WOYENGI_WORK"
    env = (
        EnvironmentBuilder(
            name="woyengi-work",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            role="work_operator",
            objective="Resume paused work from its handoff and close it only after verification.",
        )
        .system(system)
        .record(
            EVIDENCE_ID,
            system=system,
            record_type="work_handoff",
            object_id=WORK_ID,
            fields={
                "status": "paused",
                "checkpoint": "checkpoint-001",
                "completed": ["prepare_draft"],
                "remaining": ["verify_artifact", "close_work"],
            },
            searchable_text="Paused work handoff checkpoint remaining verification",
        )
        .initial_state(**{f"{WORK_ID}.phase": "paused", f"{WORK_ID}.source_preserved": True})
        .target(WORK_ID, "phase", "closed")
        .invariant(
            "preserve-handoff",
            description="Preserve the original handoff evidence.",
            object_id=WORK_ID,
            field_name="source_preserved",
            expected_value=True,
            scope="always",
        )
        .require_evidence(EVIDENCE_ID)
        .constraint("Use the handoff checkpoint; do not overwrite the original evidence.")
        .budgets(max_cost=8, max_tool_calls=8)
        .success("The paused work is resumed, its artifact verified, and the work closed.")
        .metadata(public={"environment_id": "woyengi-work", "mode": "simulation"})
    )
    steps = (
        (
            "resume_work", ActionKind.EXECUTE, "Resume using the handoff checkpoint.",
            "paused", "resumed", {"work_id": WORK_ID, "checkpoint": "checkpoint-001"},
        ),
        (
            "verify_artifact", ActionKind.READ, "Verify the resumed work's artifact.",
            "resumed", "verified", {"work_id": WORK_ID},
        ),
        (
            "close_work", ActionKind.WRITE, "Record completion after successful verification.",
            "verified", "closed", {"work_id": WORK_ID},
        ),
    )
    for name, kind, description, before, after, parameters in steps:
        env.action(
            name, kind=kind, system=system, description=description,
            parameters=tuple(parameters),
        ).transition(
            name,
            required_parameters=parameters,
            required_state=(
                StateAssertion(object_id=WORK_ID, field_name="phase", expected_value=before),
            ),
            set_state={f"{WORK_ID}.phase": after},
            observable_result={"accepted": True, "phase": after},
        ).require_action(name)
    return env.require_order(*(step[0] for step in steps)).build()
