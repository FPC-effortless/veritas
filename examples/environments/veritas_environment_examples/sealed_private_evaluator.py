from __future__ import annotations

import hashlib

from investigation_world.authoring import EnvironmentBuilder
from investigation_world.operational import (
    ActionKind,
    EpisodeSubmission,
    OperationalRuntime,
    WorldDomain,
)

from ._common import require_perfect


def build_environment(*, private_expected_choice: str):
    if not private_expected_choice:
        raise ValueError("private_expected_choice must not be empty")
    expected_digest = hashlib.sha256(private_expected_choice.encode("utf-8")).hexdigest()
    return (
        EnvironmentBuilder(
            name="sealed-private-evaluator",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Submit the externally evaluated choice without exposing evaluator material.",
            role="decision_operator",
        )
        .system("DECISION")
        .action(
            "submit_choice",
            kind=ActionKind.COMMUNICATE,
            system="DECISION",
            description="Submit one choice for sealed evaluation.",
            parameters=("choice",),
        )
        .initial_state(**{"DECISION-1.accepted": False})
        .target("DECISION-1", "accepted", True)
        .transition(
            "submit_choice",
            required_parameters={"choice": private_expected_choice},
            set_state={"DECISION-1.accepted": True},
            observable_result={"accepted": True},
            blocked_observable_result={"accepted": False},
        )
        .require_action("submit_choice")
        .metadata(
            public={"evaluator_mode": "sealed_external_material"},
            private={"expected_choice_sha256": expected_digest},
        )
        .success("The sealed evaluator accepted the submitted choice.")
        .build()
    )


def run_demo(*, private_expected_choice: str):
    episode = build_environment(private_expected_choice=private_expected_choice)
    runtime = OperationalRuntime(episode)
    public_before = repr(runtime.public_payload())
    if private_expected_choice in public_before:
        raise RuntimeError("sealed evaluator material leaked into the public payload")
    outcome = runtime.act("submit_choice", choice=private_expected_choice)
    if not outcome.get("accepted"):
        raise RuntimeError("sealed evaluator did not accept the expected choice")
    result = runtime.submit(
        EpisodeSubmission(
            conclusion="The submitted choice satisfied the sealed evaluator.",
            claimed_state={"DECISION-1.accepted": True},
            evidence_ids=[],
            confidence=1.0,
        )
    )
    return require_perfect(result)


def wrong_choice_fails(*, private_expected_choice: str):
    episode = build_environment(private_expected_choice=private_expected_choice)
    runtime = OperationalRuntime(episode)
    wrong_choice = f"not-{private_expected_choice}"
    outcome = runtime.act("submit_choice", choice=wrong_choice)
    result = runtime.submit(
        EpisodeSubmission(
            conclusion="The wrong choice should not satisfy the sealed evaluator.",
            claimed_state={"DECISION-1.accepted": True},
            evidence_ids=[],
            confidence=1.0,
        )
    )
    return outcome, result
