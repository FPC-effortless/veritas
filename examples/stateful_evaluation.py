"""Public constructed stateful fixture; no model, checkpoint, network or trainer.

Run against an installed Veritas package. This example intentionally does not alter
sys.path: source and wheel runs must name their import environment explicitly.
"""

from __future__ import annotations

import copy
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

EVENTS = (
    ("query", "A", "a0", (1, 0)),
    ("query", "B", "b0", (0, 1)),
    ("feedback", "A", "a0", (1, 0)),
    ("query", "A", "a1", (1, 0)),
    ("query", "B", "b1", (0, 1)),
    ("feedback", "B", "b0", (0, 1)),
    ("query", "B", "b2", (0, 1)),
    ("query", "A", "a2", (1, 0)),
)


class PublicMemoryFixture:
    """Two isolated dictionary stores, not a learned architecture or memory SDK."""

    def __init__(self) -> None:
        self._streams: dict[str, dict[str, tuple[int, ...]]] = {}

    def predict(self, stream: str, key: str) -> tuple[int, ...]:
        return self._streams.get(stream, {}).get(key, (0, 0))

    def observe(self, stream: str, key: str, answer: tuple[int, ...]) -> None:
        self._streams.setdefault(stream, {})[key] = tuple(answer)

    def snapshot(self) -> dict[str, dict[str, tuple[int, ...]]]:
        return copy.deepcopy(self._streams)

    def restore(self, state: dict[str, dict[str, tuple[int, ...]]]) -> None:
        self._streams = copy.deepcopy(state)

    def reset(self, stream: str) -> None:
        self._streams.pop(stream, None)

    def erase(self, stream: str, component: str) -> None:
        if component != "dictionary":
            raise ValueError("only the constructed dictionary component is supported")
        self.reset(stream)


def replay_fixture(*, erase_before_final: bool = False) -> dict[str, Any]:
    """Commit each query before its feedback; the probe never receives a target."""
    events = EVENTS
    probe = PublicMemoryFixture()
    rows: list[dict[str, Any]] = []
    transcript: list[dict[str, Any]] = []
    for index, (kind, stream, case, target) in enumerate(events):
        if kind == "feedback":
            probe.observe(stream, "key", target)
            transcript.append({"index": index, "kind": kind, "case": case})
            continue
        if erase_before_final and case == "a2":
            probe.erase("A", "dictionary")
        before = probe.snapshot()
        prediction = probe.predict(stream, "key")
        # Scoring is evaluator-side, after the prediction has been committed.
        row = {
            "case_id": case,
            "stream": stream,
            "event_index": index,
            "answer": prediction,
            "target": target,
            "exact": float(prediction == target),
            "component": sum(a == b for a, b in zip(prediction, target, strict=True)) / 2,
            "native_accept": prediction != (0, 0),
            # A distinct deliberately abstaining fixture policy, not calibration.
            "policy_accept": False,
        }
        rows.append(row)
        transcript.append({"index": index, "kind": kind, "case": case, "prediction": prediction})
        assert probe.snapshot() == before  # This fixture's reads are observational.
    return {"events": events, "rows": rows, "transcript": transcript}


def check_fixture_lifecycle() -> dict[str, bool]:
    """Actually executed conformance checks for this fixture alone."""
    probe = PublicMemoryFixture()
    before_feedback = probe.predict("A", "key")
    probe.observe("A", "key", (1, 0))
    isolated = probe.predict("B", "key") == (0, 0)
    probe.observe("B", "key", (0, 1))
    checkpoint = probe.snapshot()
    probe.erase("A", "dictionary")
    erasure = probe.predict("A", "key") == (0, 0) and probe.predict("B", "key") == (0, 1)
    # Reconstruct the fixture, rather than calling a same-instance restore a restart.
    previous_instance = probe
    probe = PublicMemoryFixture()
    probe.restore(checkpoint)
    restored = probe is not previous_instance and probe.snapshot() == checkpoint
    checkpoint["A"]["key"] = (0, 0)
    owned = probe.predict("A", "key") == (1, 0)
    probe.reset("B")
    reset = probe.predict("B", "key") == (0, 0) and probe.predict("A", "key") == (1, 0)
    checks = {
        "predict_before_feedback": before_feedback == (0, 0),
        "stream_isolation": isolated,
        "targeted_erasure": erasure,
        "snapshot_restore": restored,
        "snapshot_ownership": owned,
        "stream_reset": reset,
    }
    assert all(checks.values())
    return checks


def local_import_provenance(expected_module_sha256: str | None = None) -> dict[str, Any]:
    """Local diagnostics, kept outside any public evidence projection."""
    import investigation_world.observatory.stateful as implementation

    source = Path(implementation.__file__).resolve()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if expected_module_sha256 is not None and digest != expected_module_sha256:
        raise ValueError("actual imported module differs from independently expected source")
    return {
        "module_path": str(source),
        "module_sha256": digest,
        "source_comparison": "MATCH" if expected_module_sha256 is not None else "NOT_CHECKED",
        "fixture_path": str(Path(__file__).resolve()),
        "fixture_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": sys.version,
        "platform": platform.platform(),
        "cpu_timing": "NOT_RUN",
        "timing_reason": "Fixture correctness is not a model latency benchmark.",
    }


def fixture_report() -> Any:
    """Adapt actual constructed fixture outputs, not supplied scientific results."""
    from investigation_world.capability_science import (
        CapabilitySpec,
        CaseOutcome,
        EvaluationConditions,
        EvaluationPoint,
        EvaluationPopulation,
    )
    from investigation_world.experience import ExperienceReference
    from investigation_world.foundry.models import CapabilityContract
    from investigation_world.observatory.stateful import (
        ImportedRun,
        ResourceMeasurement,
        RunManifest,
        StateCheck,
        StateComponent,
        StatefulStudy,
        assess_stateful,
    )
    from investigation_world.trajectory import VisibilityClass, canonical_hash

    def ref(name: str, payload: Any) -> ExperienceReference:
        return ExperienceReference(
            reference_id=name,
            reference_type="constructed_public_fixture",
            digest=canonical_hash(payload),
            visibility=VisibilityClass.PUBLIC,
        )

    def source_ref(name: str, digest: str) -> ExperienceReference:
        return ExperienceReference(
            reference_id=name,
            reference_type="source_file_sha256",
            digest=digest,
            visibility=VisibilityClass.PUBLIC,
        )

    actual = local_import_provenance()
    lifecycle = check_fixture_lifecycle()
    capability = CapabilitySpec(
        contract=CapabilityContract(
            capability_id="constructed-stateful-recall",
            objective="Conformance of separated public two-bit dictionary streams",
            success_conditions=["whole two-bit answer equals the supplied fixture target"],
        ),
    )
    members = tuple(
        ref(case, {"case_id": case, "stream": stream, "event_index": index, "target": target})
        for index, (kind, stream, case, target) in enumerate(EVENTS)
        if kind == "query"
    )
    panels = {}
    for metric in ("success_fraction", "criterion_score"):
        panels[metric] = EvaluationPopulation(
            capability=capability,
            conditions=EvaluationConditions(
                environment_id="public-memory-fixture",
                environment_revision="constructed-v1",
                verifier_id="two-bit-equality",
                verifier_revision="constructed-v1",
                metric=metric,
                metric_definition_digest=canonical_hash(
                    {
                        "metric": metric,
                        "definition": "all bits equal"
                        if metric == "success_fraction"
                        else "mean bit equality",
                    }
                ),
                distribution_id="six-public-queries-v1",
                structure_id="two-isolated-streams-v1",
                interface_id="predict-before-feedback-v1",
                evidence_references=(ref("fixture-conditions", EVENTS),),
            ),
            split="HELD_OUT",
            members=members,
            evidence_references=(ref("fixture-population", EVENTS),),
        )

    plans = []
    for erase in (False, True):
        arm = "erase-final-A" if erase else "dictionary"
        plan = RunManifest(
            family="constructed",
            arm=arm,
            condition="six-public-queries",
            init_seed=0,
            data_seed=0,
            model_id="deterministic-dictionary-fixture",
            source_revision="constructed-public-memory-v1",
            source_provenance="CONSTRUCTED",
            protocol=ref("fixture-protocol", {"events": EVENTS, "arms": (False, True)}),
            source=source_ref("fixture-source", actual["fixture_sha256"]),
            configuration=ref(f"configuration-{arm}", {"erase_before_final": erase}),
            checkpoint=ref("initial-empty-state", {}),
            stream=ref("fixture-stream", EVENTS),
            adapter=source_ref("stateful-receipt-adapter", actual["module_sha256"]),
            evaluator=source_ref("equality-evaluator", actual["fixture_sha256"]),
            runtime=ref(
                "local-runtime", {"python": actual["python"], "platform": actual["platform"]}
            ),
            exact_population=panels["success_fraction"],
            criterion_population=panels["criterion_score"],
        )
        plans.append(plan)

    # The planned cells and their full populations exist before any measured replay.
    runs = []
    for plan in plans:
        arm = plan.arm
        result = replay_fixture(erase_before_final=arm == "erase-final-A")

        def point(metric: str, field: str) -> EvaluationPoint:
            return EvaluationPoint(
                population=panels[metric],
                model_id=plan.model_id,
                model_revision=plan.checkpoint.digest or "",
                sequence_index=0,
                execution_provenance="CONSTRUCTED",
                outcomes=tuple(
                    CaseOutcome(
                        member_id=member.reference_id,
                        member_digest=member.digest or "",
                        value=row[field],
                        evidence_references=(
                            ref(f"{arm}-{member.reference_id}", {"arm": arm, "row": row}),
                        ),
                    )
                    for member, row in zip(members, result["rows"], strict=True)
                ),
                evidence_references=(ref(f"{arm}-{metric}-execution", result),),
            )

        components = tuple(
            StateComponent(
                component_id=f"dictionary-{stream}",
                owner_id=stream,
                scope="adaptive",
                reason="Python dictionary heap size was not measured",
                evidence_references=(
                    ref(f"state-{stream}", {"owner": stream, "type": "dictionary"}),
                ),
            )
            for stream in ("A", "B")
        )
        checks = tuple(
            StateCheck.model_validate(
                dict(
                    kind=kind,
                    component_ids=("dictionary-A", "dictionary-B"),
                    status="OBSERVED",
                    provenance="CONSTRUCTED",
                    passed=lifecycle[key],
                    detail="Executed fixture check, not architecture qualification",
                    evidence_references=(
                        ref(f"lifecycle-{key}", {"check": key, "result": lifecycle[key]}),
                    ),
                )
            )
            for key, kind in (
                ("predict_before_feedback", "predict_before_feedback"),
                ("stream_isolation", "stream_isolation"),
                ("targeted_erasure", "query_erasure"),
                ("snapshot_restore", "restart"),
                ("snapshot_ownership", "snapshot_ownership"),
                ("stream_reset", "reset"),
            )
        )
        runs.append(
            ImportedRun(
                manifest=plan,
                status="completed",
                provenance="CONSTRUCTED",
                exact=point("success_fraction", "exact"),
                criterion=point("criterion_score", "component"),
                native_acceptance={row["case_id"]: row["native_accept"] for row in result["rows"]},
                policy_acceptance={row["case_id"]: row["policy_accept"] for row in result["rows"]},
                policy=ref("all-abstain-fixture-policy", {"accept": False, "calibrated": False}),
                components=components,
                checks=checks,
                resources=(
                    ResourceMeasurement(
                        metric="latency_p95",
                        unit="second",
                        scope="whole fixture replay",
                        reason="not measured; correctness fixture is not a latency benchmark",
                        provenance="UNKNOWN",
                        measurement=ref("timing-not-run", {"timing": "NOT_RUN"}),
                    ),
                ),
                evidence_references=(ref(f"{arm}-receipt", result),),
            )
        )
    return assess_stateful(StatefulStudy(expected=tuple(plans), runs=tuple(runs)))


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "scope": "CONSTRUCTED evaluator-side demonstration, not a public/scientific export",
                "report": fixture_report().model_dump(mode="json"),
                "local_import_provenance": local_import_provenance(),
            },
            indent=2,
        )
    )
