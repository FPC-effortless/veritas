"""Woyengi Work: a self-contained agent evaluation environment."""

from enum import StrEnum

from investigation_world.authoring import EnvironmentBuilder
from investigation_world.operational.models import (
    ActionKind,
    OperationalEpisode,
    StateAssertion,
    WorldDomain,
)

WORK_ID = "WORK-001"
EVIDENCE_ID = "work-handoff-001"


class WoyengiWorkTask(StrEnum):
    HANDOFF = "handoff"
    APPROVAL = "approval"
    RECONCILIATION = "reconciliation"
    REVISION = "revision"
    ESCALATION = "escalation"


def build_woyengi_work_environment(
    task: WoyengiWorkTask | str = WoyengiWorkTask.HANDOFF,
) -> OperationalEpisode:
    """Build one deterministic task from the offline Woyengi Work environment."""
    task = WoyengiWorkTask(task)
    if task == WoyengiWorkTask.HANDOFF:
        return _build_handoff()
    return _build_task(task)


def _build_handoff() -> OperationalEpisode:
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
        .metadata(public={
            "environment_id": "woyengi-work", "work_task": "handoff", "mode": "simulation",
        })
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


# Each task has its own evidence, action vocabulary and completion criterion.
_TASKS = {
    WoyengiWorkTask.APPROVAL: (
        "Check authorization for report R7 before releasing it to the approved audience.",
        (
            ("request-R7", "release_request", {"audience": "internal", "report": "R7"}),
            ("decision-R7", "review_receipt", {
                "decision": "approved", "audience": "internal", "report": "R7",
            }),
        ),
        (
            ("verify_approval", ActionKind.READ, "Check a supervisor decision against the request.",
             {"decision_id": "decision-R7"}),
            ("release_report", ActionKind.WRITE, "Release the report to the authorized audience.",
             {"report_id": "R7", "audience": "internal"}),
        ),
        "released",
    ),
    WoyengiWorkTask.RECONCILIATION: (
        "Reconcile a summary against the authoritative ledger without editing the ledger.",
        (
            ("summary-12", "derived_summary", {"reported_count": 12}),
            ("ledger-14", "source_ledger", {"confirmed_count": 14}),
        ),
        (
            ("compare_records", ActionKind.READ, "Compare the summary to its authoritative ledger.",
             {"summary_id": "summary-12", "source_id": "ledger-14"}),
            ("correct_summary", ActionKind.WRITE, "Record the verified count in the summary.",
             {"summary_id": "summary-12", "count": "14"}),
        ),
        "reconciled",
    ),
    WoyengiWorkTask.REVISION: (
        "Supersede a stale brief with the reviewed revision, then update its dependent index.",
        (
            ("brief-r1", "prior_version", {"revision": "r1", "dependent": "brief-index"}),
            ("brief-r2", "reviewed_revision", {"revision": "r2", "replaces": "r1"}),
        ),
        (
            ("mark_superseded", ActionKind.WRITE, "Record which previous revision was superseded.",
             {"previous_id": "brief-r1", "replacement_id": "brief-r2"}),
            ("refresh_index", ActionKind.WRITE, "Retarget the dependent index to the replacement.",
             {"index_id": "brief-index", "revision_id": "brief-r2"}),
        ),
        "updated",
    ),
    WoyengiWorkTask.ESCALATION: (
        "Resolve a request with no approval receipt without closing the work as completed.",
        (
            ("work-request", "incoming_request", {"requested_action": "close_work"}),
            ("review-status", "approval_status", {"decision": "pending", "route": "supervisor"}),
        ),
        (
            ("check_review_status", ActionKind.READ, "Read the available approval status.",
             {"record_id": "review-status"}),
            ("escalate_work", ActionKind.ESCALATE, "Escalate unresolved approval to the right role.",
             {"reason": "approval_pending", "recipient": "supervisor"}),
        ),
        "escalated",
    ),
}


# Concrete state outcomes, in addition to the workflow phase.
_OUTCOMES = {
    WoyengiWorkTask.APPROVAL: ("released_to", None, "internal"),
    WoyengiWorkTask.RECONCILIATION: ("summary_count", 12, 14),
    WoyengiWorkTask.REVISION: ("indexed_revision", "r1", "r2"),
    WoyengiWorkTask.ESCALATION: ("assigned_reviewer", None, "supervisor"),
}


def _build_task(task: WoyengiWorkTask) -> OperationalEpisode:
    objective, records, steps, target = _TASKS[task]
    field, initial, expected = _OUTCOMES[task]
    system = "WOYENGI_WORK"
    env = (
        EnvironmentBuilder(
            name=f"woyengi-work-{task.value}",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            role="work_operator",
            objective=objective,
        )
        .system(system)
        .initial_state(**{f"{WORK_ID}.phase": "open", f"{WORK_ID}.{field}": initial})
        .target(WORK_ID, field, expected)
        .target(WORK_ID, "phase", target)
        .constraint("Cite the work records that support the final disposition.")
        .success(f"The task is {target} and its disposition is supported by both records.")
        .budgets(max_cost=8, max_tool_calls=8)
        .metadata(public={
            "environment_id": "woyengi-work", "work_task": task.value, "mode": "simulation",
        })
    )
    for record_id, record_type, fields in records:
        env.record(
            record_id, system=system, record_type=record_type, object_id=WORK_ID,
            fields=fields, searchable_text=f"{record_type} {record_id}",
        ).require_evidence(record_id)

    phase = "open"
    for i, (name, kind, description, params) in enumerate(steps):
        last = i == len(steps) - 1
        after = target if last else f"{name}_recorded"
        changes = {f"{WORK_ID}.phase": after}
        if last:
            changes[f"{WORK_ID}.{field}"] = expected
        env.action(
            name, kind=kind, system=system, description=description, parameters=tuple(params),
        ).transition(
            name,
            required_parameters=params,
            required_state=(StateAssertion(
                object_id=WORK_ID, field_name="phase", expected_value=phase,
            ),),
            set_state=changes,
            observable_result={"accepted": True, "phase": after},
        ).require_action(name)
        phase = after

    if task == WoyengiWorkTask.ESCALATION:
        env.action(
            "close_work", kind=ActionKind.WRITE, system=system,
            description="Close the work if approval has been granted.", parameters=("work_id",),
        ).transition(
            "close_work",
            required_parameters={"work_id": WORK_ID},
            required_state=(StateAssertion(
                object_id=WORK_ID, field_name="phase", expected_value="approved",
            ),),
            set_state={f"{WORK_ID}.phase": "closed"},
            blocked_observable_result={"accepted": False, "reason": "approval_pending"},
        )

    return env.require_order(*(step[0] for step in steps)).build()
