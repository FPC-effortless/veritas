from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from investigation_world.investigation_data.gold10_manifest import build_gold10_manifest
from investigation_world.tasks.spec import TaskFamily, TaskSpec

from .models import (
    EvidenceRecord,
    Gold10Task,
    InstitutionalFinding,
    PilotContract,
)

ROOT = Path(__file__).resolve().parents[3]
PILOT_CONTRACT_REL = Path("data/gold10/pilot/pilot_contract_v1.json")
PILOTS_REL = Path("docs/investigation_data/pilots")


class Gold10PilotError(ValueError):
    """Raised when the executable Gold-10 pilot cannot be reconstructed safely."""


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Gold10PilotError(f"expected object JSON at {path}")
    return value


def _string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Gold10PilotError(f"{label} must be a non-empty string")
    return value.strip()


def _string_tuple(value: Any, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise Gold10PilotError(f"{label} must be a non-empty list")
    output = tuple(_string(item, label=f"{label} item") for item in value)
    if len(output) != len(set(output)):
        raise Gold10PilotError(f"{label} must not contain duplicates")
    return output


def _timestamp(value: Any, *, label: str) -> datetime:
    raw = _string(value, label=label)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise Gold10PilotError(f"{label} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise Gold10PilotError(f"{label} must be timezone-aware")
    return parsed


def load_pilot_contract(root: Path | None = None) -> PilotContract:
    repo_root = (root or ROOT).resolve()
    return PilotContract.model_validate(_read_object(repo_root / PILOT_CONTRACT_REL))


def _available_evidence(
    pilot: dict[str, Any],
    *,
    case_id: str,
    simulation_as_of: datetime,
) -> tuple[EvidenceRecord, ...]:
    fragments = pilot.get("fragments")
    if not isinstance(fragments, list) or not fragments:
        raise Gold10PilotError(f"case {case_id} has no canonical evidence fragments")

    evidence: list[EvidenceRecord] = []
    seen: set[str] = set()
    for raw in fragments:
        if not isinstance(raw, dict):
            raise Gold10PilotError(f"case {case_id} contains a malformed fragment")
        evidence_id = _string(raw.get("fragment_id"), label=f"{case_id} fragment_id")
        if evidence_id in seen:
            raise Gold10PilotError(f"case {case_id} has duplicate evidence id {evidence_id}")
        seen.add(evidence_id)
        if raw.get("sensitivity") != "public":
            continue

        timeless = raw.get("timeless", False)
        if not isinstance(timeless, bool):
            raise Gold10PilotError(f"case {case_id} fragment timeless must be boolean")
        available_from_raw = raw.get("available_from")
        if not timeless:
            available_from = _timestamp(
                available_from_raw,
                label=f"{case_id} fragment {evidence_id} available_from",
            )
            if available_from > simulation_as_of:
                continue

        evidence.append(
            EvidenceRecord(
                evidence_id=evidence_id,
                source_id=_string(
                    raw.get("source_id"),
                    label=f"{case_id} fragment {evidence_id} source_id",
                ),
                source_artifact_id=_string(
                    raw.get("source_artifact_id"),
                    label=f"{case_id} fragment {evidence_id} source_artifact_id",
                ),
                modality=_string(
                    raw.get("modality"),
                    label=f"{case_id} fragment {evidence_id} modality",
                ),
                epistemic_role=_string(
                    raw.get("epistemic_role"),
                    label=f"{case_id} fragment {evidence_id} epistemic_role",
                ),
                reliability=_string(
                    raw.get("reliability"),
                    label=f"{case_id} fragment {evidence_id} reliability",
                ),
                locator=_string(
                    raw.get("locator"),
                    label=f"{case_id} fragment {evidence_id} locator",
                ),
                content_ref=_string(
                    raw.get("content_ref"),
                    label=f"{case_id} fragment {evidence_id} content_ref",
                ),
                available_from=(
                    None
                    if timeless
                    else _string(
                        available_from_raw,
                        label=f"{case_id} fragment {evidence_id} available_from",
                    )
                ),
            )
        )
    if not evidence:
        raise Gold10PilotError(f"case {case_id} has no public evidence at its temporal cut")
    return tuple(evidence)


def _available_findings(
    pilot: dict[str, Any],
    *,
    case_id: str,
    available_evidence_ids: set[str],
) -> tuple[InstitutionalFinding, ...]:
    raw_findings = pilot.get("official_findings", [])
    if not isinstance(raw_findings, list):
        raise Gold10PilotError(f"case {case_id} official_findings must be a list")

    output: list[InstitutionalFinding] = []
    seen: set[str] = set()
    for raw in raw_findings:
        if not isinstance(raw, dict):
            raise Gold10PilotError(f"case {case_id} contains a malformed institutional finding")
        finding_id = _string(raw.get("finding_id"), label=f"{case_id} finding_id")
        if finding_id in seen:
            raise Gold10PilotError(f"case {case_id} has duplicate finding id {finding_id}")
        seen.add(finding_id)
        source_ids = _string_tuple(
            raw.get("source_evidence_ids"),
            label=f"{case_id} finding {finding_id} source_evidence_ids",
        )
        if not set(source_ids).issubset(available_evidence_ids):
            continue
        confidence = raw.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, int | float):
            raise Gold10PilotError(f"case {case_id} finding confidence must be numeric")
        output.append(
            InstitutionalFinding(
                finding_id=finding_id,
                authority=_string(
                    raw.get("authority"),
                    label=f"{case_id} finding {finding_id} authority",
                ),
                statement=_string(
                    raw.get("finding"),
                    label=f"{case_id} finding {finding_id} statement",
                ),
                confidence=float(confidence),
                source_evidence_ids=source_ids,
            )
        )
    return tuple(output)


def build_task(case_id: str, root: Path | None = None) -> Gold10Task:
    repo_root = (root or ROOT).resolve()
    manifest = build_gold10_manifest(repo_root)
    contract = load_pilot_contract(repo_root)

    cases = {
        _string(row.get("case_id"), label="Gold-10 case_id"): row
        for row in manifest.get("cases", [])
        if isinstance(row, dict)
    }
    row = cases.get(case_id)
    if row is None:
        raise Gold10PilotError(f"unknown frozen Gold-10 case: {case_id}")

    report = row.get("report")
    if not isinstance(report, dict) or report.get("eligible_for_task_evidence") is not True:
        raise Gold10PilotError(f"case {case_id} lacks exact task-use authority")

    task_owner_path = _string(row.get("task_owner_path"), label=f"{case_id} task_owner_path")
    verifier_owner_path = _string(
        row.get("verifier_owner_path"),
        label=f"{case_id} verifier_owner_path",
    )
    for label, relative in (("task", task_owner_path), ("verifier", verifier_owner_path)):
        candidate = (repo_root / relative).resolve()
        if repo_root not in candidate.parents or not candidate.is_file():
            raise Gold10PilotError(f"case {case_id} expected {label} owner path is absent")

    pilot_dir = _string(row.get("pilot_dir"), label=f"{case_id} pilot_dir")
    pilot = _read_object(repo_root / PILOTS_REL / pilot_dir / "manifest.json")
    if pilot.get("ground_truth_claims") != []:
        raise Gold10PilotError(f"case {case_id} unexpectedly exposes private ground truth")

    public_cut = row.get("public_temporal_cut")
    if not isinstance(public_cut, dict):
        raise Gold10PilotError(f"case {case_id} public temporal cut is malformed")
    simulation_as_of_raw = _string(
        public_cut.get("simulation_as_of"),
        label=f"{case_id} simulation_as_of",
    )
    simulation_as_of = _timestamp(
        simulation_as_of_raw,
        label=f"{case_id} simulation_as_of",
    )
    evidence = _available_evidence(
        pilot,
        case_id=case_id,
        simulation_as_of=simulation_as_of,
    )
    evidence_ids = {item.evidence_id for item in evidence}
    findings = _available_findings(
        pilot,
        case_id=case_id,
        available_evidence_ids=evidence_ids,
    )

    initial_state = pilot.get("initial_public_state")
    if not isinstance(initial_state, dict):
        raise Gold10PilotError(f"case {case_id} initial_public_state must be an object")
    objective = _string(initial_state.get("task"), label=f"{case_id} public task")
    actions = _string_tuple(
        pilot.get("available_actions"),
        label=f"{case_id} available_actions",
    )
    capability_raw = row.get("capability_targets")
    if not isinstance(capability_raw, list) or not capability_raw:
        raise Gold10PilotError(f"case {case_id} capability targets are absent")
    capability_targets = tuple(
        _string(item, label=f"{case_id} capability target")
        for item in capability_raw
    )
    calibration_required = row.get("calibration_required")
    if not isinstance(calibration_required, bool):
        raise Gold10PilotError(f"case {case_id} calibration_required must be boolean")

    task_spec = TaskSpec(
        task_id=f"GOLD10-{case_id}",
        world_id=f"{contract.world_id}:{case_id}",
        family=TaskFamily.DUE_DILIGENCE,
        objective=objective,
        target_refs=[item.evidence_id for item in evidence],
        constraints={
            "must_cite_evidence": True,
            "no_hindsight": True,
            "institutional_findings_are_not_private_truth": True,
            "task_use_scope": "internal_task_and_verifier_evidence_only",
        },
        difficulty={
            "available_evidence_count": float(len(evidence)),
            "available_modality_count": float(len({item.modality for item in evidence})),
            "public_historical_contamination": 1.0,
        },
        metadata={
            "domain": "industrial_accident_investigation",
            "case_id": case_id,
            "slug": row["slug"],
            "split": row["split"],
            "calibration_required": row["calibration_required"],
            "capability_targets": list(capability_targets),
        },
    )
    return Gold10Task(
        case_id=case_id,
        slug=_string(row.get("slug"), label=f"{case_id} slug"),
        split=_string(row.get("split"), label=f"{case_id} split"),
        task=task_spec,
        calibration_required=calibration_required,
        public_temporal_cut={
            "simulation_start": _string(
                public_cut.get("simulation_start"),
                label=f"{case_id} simulation_start",
            ),
            "simulation_as_of": simulation_as_of_raw,
            "date_only_release_policy": _string(
                public_cut.get("date_only_release_policy"),
                label=f"{case_id} date_only_release_policy",
            ),
        },
        available_actions=actions,
        available_evidence=evidence,
        available_findings=findings,
        capability_targets=capability_targets,
        manifest_sha256=_string(
            manifest.get("manifest_sha256"),
            label="Gold-10 manifest_sha256",
        ),
    )


def build_taskset(root: Path | None = None) -> tuple[Gold10Task, ...]:
    repo_root = (root or ROOT).resolve()
    manifest = build_gold10_manifest(repo_root)
    case_ids = sorted(
        _string(row.get("case_id"), label="Gold-10 case_id")
        for row in manifest.get("cases", [])
        if isinstance(row, dict)
    )
    tasks = tuple(build_task(case_id, repo_root) for case_id in case_ids)
    if len(tasks) != 10:
        raise Gold10PilotError("Gold-10 executable pilot must contain exactly 10 tasks")
    splits = {"train": 0, "dev": 0, "eval": 0}
    for task in tasks:
        if task.split not in splits:
            raise Gold10PilotError(f"invalid executable split: {task.split}")
        splits[task.split] += 1
    if splits != {"train": 6, "dev": 2, "eval": 2}:
        raise Gold10PilotError(f"Gold-10 executable split drifted: {splits}")
    modalities = {item.modality for task in tasks for item in task.available_evidence}
    if len(modalities) < 2:
        raise Gold10PilotError("Gold-10 pilot must expose at least two evidence modalities")
    return tasks
