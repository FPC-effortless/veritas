from __future__ import annotations

import hashlib
import json

from investigation_world.authoring import EnvironmentBuilder
from investigation_world.experience import ExperienceMaturity, machine_experience_from_trajectory
from investigation_world.operational import (
    ActionKind,
    EpisodeSubmission,
    OperationalRuntime,
    WorldDomain,
)
from investigation_world.trajectory import (
    EvaluationRecord,
    StateDigest,
    TaskIdentity,
    TrajectoryEvent,
    TrajectoryV2,
    VerifierIdentity,
    WorldIdentity,
)


def build_environment():
    return (
        EnvironmentBuilder(
            name="machine-experience-ready",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Inspect evidence and record a deterministic verified decision.",
            role="experience_operator",
        )
        .system("EXPERIENCE")
        .action(
            "inspect_evidence",
            kind=ActionKind.READ,
            system="EXPERIENCE",
            description="Inspect the public evidence record.",
            parameters=("case_id",),
        )
        .action(
            "record_decision",
            kind=ActionKind.WRITE,
            system="EXPERIENCE",
            description="Record the verified decision.",
            parameters=("case_id",),
        )
        .record(
            "experience-evidence-001",
            system="EXPERIENCE",
            record_type="evidence",
            object_id="CASE-EXP-1",
            fields={"decision": "proceed"},
            searchable_text="verified evidence supports proceed decision",
        )
        .initial_state(**{"CASE-EXP-1.decision": "unknown"})
        .target("CASE-EXP-1", "decision", "proceed")
        .transition(
            "inspect_evidence",
            required_parameters={"case_id": "CASE-EXP-1"},
            observable_result={"accepted": True, "evidence_id": "experience-evidence-001"},
        )
        .transition(
            "record_decision",
            required_parameters={"case_id": "CASE-EXP-1"},
            required_prior_actions=("inspect_evidence",),
            set_state={"CASE-EXP-1.decision": "proceed"},
            observable_result={"accepted": True},
        )
        .require_action("inspect_evidence")
        .require_action("record_decision")
        .require_order("inspect_evidence", "record_decision")
        .require_evidence("experience-evidence-001")
        .success("The evidence-backed decision is recorded.")
        .build()
    )


def _state_digest(state: dict[str, object]) -> str:
    canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_demo():
    episode = build_environment()
    runtime = OperationalRuntime(episode)
    public_events: list[TrajectoryEvent] = []
    for step, (action_name, parameters) in enumerate(
        (
            ("inspect_evidence", {"case_id": "CASE-EXP-1"}),
            ("record_decision", {"case_id": "CASE-EXP-1"}),
        )
    ):
        result = runtime.act(action_name, **parameters)
        public_events.append(
            TrajectoryEvent(
                step=step,
                event_type="action",
                payload={"action": action_name, "result": result},
            )
        )
    verification = runtime.submit(
        EpisodeSubmission(
            conclusion="CASE-EXP-1 proceeds based on the cited evidence.",
            claimed_state={"CASE-EXP-1.decision": "proceed"},
            evidence_ids=["experience-evidence-001"],
            confidence=1.0,
        )
    )
    if verification.overall_reward != 1.0:
        raise RuntimeError("MachineExperience source episode did not verify perfectly")

    verifier = VerifierIdentity(verifier_id="operational-structured-verifier", version="1")
    trajectory = TrajectoryV2(
        world=WorldIdentity(
            environment_id=episode.world_id,
            environment_version="dx-003-v1",
            world_id=episode.world_id,
            world_version="1",
        ),
        task=TaskIdentity(
            task_id=episode.task.task_id,
            taskset_version="dx-003-v1",
            split="example",
        ),
        verifier=verifier,
        initial_state=StateDigest(digest=_state_digest(episode.oracle.initial_state)),
        events=tuple(public_events),
        original_evaluation=EvaluationRecord(
            verifier=verifier,
            component_scores={"operational_verification": verification.overall_reward},
            reward=verification.overall_reward,
        ),
    )
    experience = machine_experience_from_trajectory(trajectory)
    if experience.maturity is not ExperienceMaturity.E0_TRACEABLE:
        raise RuntimeError("example must not claim readiness beyond traceable evidence")
    return experience
