from __future__ import annotations

from investigation_world.authoring import EnvironmentBuilder
from investigation_world.operational import ActionKind, OperationalRuntime, WorldDomain

from ._common import execute_episode, require_perfect


def build_environment():
    return (
        EnvironmentBuilder(
            name="long-horizon-budgeted-reconciliation",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Complete a four-stage reconciliation within a strict action budget.",
            role="reconciliation_operator",
        )
        .system("RECON")
        .action(
            "inspect",
            kind=ActionKind.READ,
            system="RECON",
            description="Inspect the case.",
            parameters=("case_id",),
            cost=1,
        )
        .action(
            "cross_check",
            kind=ActionKind.READ,
            system="RECON",
            description="Cross-check the case evidence.",
            parameters=("case_id",),
            cost=1,
        )
        .action(
            "reconcile",
            kind=ActionKind.WRITE,
            system="RECON",
            description="Reconcile the case.",
            parameters=("case_id",),
            cost=1,
        )
        .action(
            "close",
            kind=ActionKind.WRITE,
            system="RECON",
            description="Close the reconciled case.",
            parameters=("case_id",),
            cost=1,
        )
        .action(
            "extra_probe",
            kind=ActionKind.READ,
            system="RECON",
            description="An unnecessary extra probe used only as a budget falsifier.",
            parameters=("case_id",),
            cost=1,
        )
        .record(
            "recon-evidence-001",
            system="RECON",
            record_type="case_evidence",
            object_id="CASE-1",
            fields={"requires_cross_check": True},
            searchable_text="case requires cross check before reconciliation",
        )
        .initial_state(**{"CASE-1.stage": "open"})
        .target("CASE-1", "stage", "closed")
        .transition(
            "inspect",
            required_parameters={"case_id": "CASE-1"},
            set_state={"CASE-1.stage": "inspected"},
            observable_result={"accepted": True},
        )
        .transition(
            "cross_check",
            required_parameters={"case_id": "CASE-1"},
            required_prior_actions=("inspect",),
            set_state={"CASE-1.stage": "checked"},
            observable_result={"accepted": True},
        )
        .transition(
            "reconcile",
            required_parameters={"case_id": "CASE-1"},
            required_prior_actions=("inspect", "cross_check"),
            set_state={"CASE-1.stage": "reconciled"},
            observable_result={"accepted": True},
        )
        .transition(
            "close",
            required_parameters={"case_id": "CASE-1"},
            required_prior_actions=("inspect", "cross_check", "reconcile"),
            set_state={"CASE-1.stage": "closed"},
            observable_result={"accepted": True},
        )
        .require_action("inspect")
        .require_action("cross_check")
        .require_action("reconcile")
        .require_action("close")
        .require_order("inspect", "cross_check", "reconcile", "close")
        .require_evidence("recon-evidence-001")
        .budgets(max_cost=8, max_tool_calls=8)
        .success("CASE-1 is reconciled and closed with budget headroom.")
        .build()
    )


def run_demo():
    result = execute_episode(
        build_environment(),
        actions=(
            ("inspect", {"case_id": "CASE-1"}),
            ("cross_check", {"case_id": "CASE-1"}),
            ("reconcile", {"case_id": "CASE-1"}),
            ("close", {"case_id": "CASE-1"}),
        ),
        evidence_ids=("recon-evidence-001",),
        claimed_state={"CASE-1.stage": "closed"},
        conclusion="CASE-1 was reconciled and closed within budget.",
    )
    return require_perfect(result)


def budget_falsifier_raises() -> None:
    runtime = OperationalRuntime(build_environment())
    for action_name in ("inspect", "cross_check", "reconcile", "close"):
        runtime.act(action_name, case_id="CASE-1")
    for _ in range(4):
        runtime.act("extra_probe", case_id="CASE-1")
    runtime.act("extra_probe", case_id="CASE-1")
