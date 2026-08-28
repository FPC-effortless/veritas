from __future__ import annotations

from investigation_world.authoring import EnvironmentBuilder
from investigation_world.operational import ActionKind, OperationalRuntime, WorldDomain

from ._common import execute_episode, require_perfect


def build_environment():
    return (
        EnvironmentBuilder(
            name="hierarchical-observation",
            domain=WorldDomain.INVESTIGATION_OSINT,
            objective="Resolve a case using nested observation fields without exposing verifier state.",
            role="investigator",
        )
        .system("CASEFILE")
        .action(
            "resolve_case",
            kind=ActionKind.WRITE,
            system="CASEFILE",
            description="Resolve the case from nested evidence.",
            parameters=("case_id",),
        )
        .record(
            "hier-rec-001",
            system="CASEFILE",
            record_type="case_bundle",
            object_id="CASE-1",
            fields={
                "subject": {"id": "SUBJECT-1", "aliases": ["A1", "A2"]},
                "evidence": {
                    "documents": [{"id": "DOC-1", "authority": "authoritative"}],
                    "signals": {"match": True, "confidence": 0.99},
                },
            },
            searchable_text="CASE-1 SUBJECT-1 authoritative match",
        )
        .initial_state(**{"CASE-1.resolved": False})
        .target("CASE-1", "resolved", True)
        .transition(
            "resolve_case",
            required_parameters={"case_id": "CASE-1"},
            set_state={"CASE-1.resolved": True},
            observable_result={"accepted": True},
        )
        .require_action("resolve_case")
        .require_evidence("hier-rec-001")
        .metadata(public={"observation_shape": "hierarchical"})
        .success("The nested observation supports case resolution.")
        .build()
    )


def public_observation():
    runtime = OperationalRuntime(build_environment())
    payload = runtime.public_payload()
    return payload["records"][0]["fields"]


def run_demo():
    observation = public_observation()
    if observation["evidence"]["signals"]["match"] is not True:
        raise RuntimeError("hierarchical observation lost nested signal semantics")
    result = execute_episode(
        build_environment(),
        actions=(("resolve_case", {"case_id": "CASE-1"}),),
        evidence_ids=("hier-rec-001",),
        claimed_state={"CASE-1.resolved": True},
        conclusion="Nested authoritative evidence supports resolving CASE-1.",
    )
    return require_perfect(result)
