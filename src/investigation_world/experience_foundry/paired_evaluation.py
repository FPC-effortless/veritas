"""Complete frozen-panel outcome checks, not a training/evaluation runner.

Panel membership and provenance are evaluator-supplied commitments. Hash equality
checks those commitments, not their chronology or who produced model actions.
All objects and reports are evaluator-side; no private source IDs are exported.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import model_validator

from investigation_world.foundry.models import DistributionSplit
from investigation_world.foundry.training_product import TrainingBundle, TrainingRunManifest
from investigation_world.trajectory.models import (
    CanonicalModel,
    RuntimeIdentity,
    TaskIdentity,
    TrajectoryV2,
    VerifierIdentity,
    WorldIdentity,
    canonical_hash,
)
from investigation_world.trajectory.reverify import (
    REPLAY_EVIDENCE_PRIVATE_KEY,
    AuthorizedVerifierRegistry,
    ReverificationStatus,
    reverify_trajectory,
)


def _digest(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


class PanelCase(CanonicalModel):
    """Pinned expected identity; split/runtime enrichment never overwrites unknowns."""

    case_id: str
    task: TaskIdentity
    world: WorldIdentity
    runtime: RuntimeIdentity
    verifier: VerifierIdentity
    split: DistributionSplit
    source_id: str
    source_digest: str
    runtime_source_digest: str
    contract_digest: str

    @model_validator(mode="after")
    def validate_case(self) -> PanelCase:
        if not self.case_id or not self.source_id or not self.task.task_id:
            raise ValueError("panel case identity is incomplete")
        if self.split is DistributionSplit.TRAIN:
            raise ValueError("panel must be held out")
        if self.task.split is not None and self.task.split != self.split.value:
            raise ValueError("panel split contradicts canonical task")
        if (
            not self.world.world_id
            or not self.world.world_version
            or self.world.portable_operational_contract is None
            or not self.world.portable_operational_contract.version
        ):
            raise ValueError("panel world/contract identity is incomplete")
        if not self.verifier.verifier_id or not self.verifier.version:
            raise ValueError("panel verifier identity is incomplete")
        if not all(
            _digest(value)
            for value in (
                self.source_digest,
                self.runtime_source_digest,
                self.contract_digest,
            )
        ):
            raise ValueError("panel source digests are incomplete")
        return self


class FrozenPanel(CanonicalModel):
    panel_id: str = ""
    cases: tuple[PanelCase, ...]
    evaluation_config: dict[str, Any]
    run_id: str
    model_provider: str

    @model_validator(mode="after")
    def bind_panel(self) -> FrozenPanel:
        if not self.cases or not self.run_id or not self.model_provider.strip():
            raise ValueError("panel must contain cases and a run identity")
        for values in (
            [case.case_id for case in self.cases],
            [case.task.task_id for case in self.cases],
            [case.source_id for case in self.cases],
        ):
            if len(values) != len(set(values)):
                raise ValueError("duplicate panel identity")
        expected = "PANEL-" + canonical_hash(self.model_dump(exclude={"panel_id"}))
        if self.panel_id and self.panel_id != expected:
            raise ValueError("panel identity drift")
        object.__setattr__(self, "panel_id", expected)
        return self


class PanelAttempt(CanonicalModel):
    case_id: str
    trajectory: TrajectoryV2
    source_id: str
    source_digest: str
    runtime_source_digest: str
    evaluation_config_digest: str
    run_id: str
    checkpoint_identity: str


def _attempts_by_case(attempts: tuple[PanelAttempt, ...], panel: FrozenPanel) -> dict:
    checked = [PanelAttempt.model_validate(item.model_dump(mode="python")) for item in attempts]
    by_id = {item.case_id: item for item in checked}
    if len(checked) != len(by_id):
        raise ValueError("duplicate paired attempt")
    if set(by_id) != {case.case_id for case in panel.cases}:
        raise ValueError("incomplete or substituted paired cases")
    trajectory_ids = [item.trajectory.trajectory_id for item in checked]
    if len(trajectory_ids) != len(set(trajectory_ids)):
        raise ValueError("duplicate paired trajectory")
    return by_id


def _evaluate(
    attempt: PanelAttempt,
    case: PanelCase,
    panel: FrozenPanel,
    *,
    model_id: str,
    checkpoint_identity: str,
    registry: AuthorizedVerifierRegistry,
) -> dict[str, Any]:
    trajectory = attempt.trajectory
    if (
        attempt.run_id != panel.run_id
        or attempt.evaluation_config_digest != canonical_hash(panel.evaluation_config)
        or attempt.source_id != case.source_id
        or attempt.source_digest != case.source_digest
        or attempt.runtime_source_digest != case.runtime_source_digest
        or trajectory.task != case.task
        or trajectory.world != case.world
        or trajectory.runtime != case.runtime
        or trajectory.verifier != case.verifier
    ):
        raise ValueError("paired protocol or source identity drift")
    if (
        attempt.checkpoint_identity != checkpoint_identity
        or trajectory.model.snapshot != checkpoint_identity
        or trajectory.model.model_id != model_id
        or trajectory.model.provider != panel.model_provider
    ):
        raise ValueError("paired checkpoint/model substitution")
    sources = [item for item in trajectory.provenance if item.source_id == case.source_id]
    if len(sources) != 1 or sources[0].source_digest != case.source_digest:
        raise ValueError("paired source provenance mismatch")
    raw = trajectory.private_metadata.get(REPLAY_EVIDENCE_PRIVATE_KEY)
    if isinstance(raw, dict) and "portable_contract" in raw:
        if canonical_hash(raw["portable_contract"]) != case.contract_digest:
            raise ValueError("paired contract drift")
    # History is not execution identity. Discard caller-authored prior records so
    # even ALREADY_RECORDED cannot return their unbound private metadata.
    payload = trajectory.model_dump(mode="python")
    payload["reverifications"] = ()
    fresh_input = TrajectoryV2.model_validate(payload)
    if fresh_input.trajectory_id != trajectory.trajectory_id:
        raise ValueError("paired execution identity changed while clearing history")
    result = reverify_trajectory(fresh_input, verifier=case.verifier, registry=registry)
    if result.status is ReverificationStatus.UNAUTHORIZED:
        raise ValueError("paired verifier unauthorized")
    record = result.record
    if record is not None and (
        not math.isfinite(record.reward)
        or not all(math.isfinite(value) for value in record.component_scores.values())
    ):
        raise ValueError("nonfinite paired outcome")
    return {
        "trajectory_id": trajectory.trajectory_id,
        "status": result.status.value,
        "reason_code": result.reason_code,
        "record_id": record.record_id if record else None,
        "reward": record.reward if record else None,
        "component_scores": dict(record.component_scores) if record else {},
        "termination": trajectory.termination.model_dump(mode="json"),
        "failure": trajectory.failure.model_dump(mode="json"),
    }


def _training_membership(bundle: TrainingBundle) -> tuple[set[str], set[str], set[str]]:
    """Derive disjointness only from the exact byte-bound bundle, never caller sets."""
    examples = bundle.train_examples
    rows = bundle.metadata.get("verified_learning_lineage")
    if (
        not examples
        or bundle.preference_examples
        or not isinstance(rows, list)
        or len(rows) != len(examples)
    ):
        raise ValueError("training lineage must cover every training example")
    by_id = {example.trajectory_id: example for example in examples}
    if len(by_id) != len(examples) or len({x.example_id for x in examples}) != len(examples):
        raise ValueError("duplicate training lineage/example identity")
    fields = (
        "verified_trajectory_id",
        "task_id",
        "source_id",
        "source_digest",
        "trajectory_id",
        "experience_id",
    )
    seen: dict[str, set[str]] = {field: set() for field in fields}
    for row in rows:
        if not isinstance(row, dict) or any(
            not isinstance(row.get(field), str) or not row[field].strip() for field in fields
        ):
            raise ValueError("training lineage identity is incomplete")
        if not _digest(row["source_digest"]):
            raise ValueError("training lineage source digest is invalid")
        example = by_id.get(row["verified_trajectory_id"])
        if (
            example is None
            or row["task_id"] != example.task_id
            or example.split is not DistributionSplit.TRAIN
        ):
            raise ValueError("training lineage does not bind its exact TRAIN example")
        for field in fields:
            if row[field] in seen[field]:
                raise ValueError("duplicate training lineage identity")
            seen[field].add(row[field])
    if seen["verified_trajectory_id"] != set(by_id):
        raise ValueError("training lineage is incomplete")
    return seen["task_id"], seen["source_id"], seen["source_digest"]


def compare_frozen_panel(
    panel: FrozenPanel,
    baseline: tuple[PanelAttempt, ...],
    checkpoint: tuple[PanelAttempt, ...],
    *,
    receipt: Any,
    expected_manifest: TrainingRunManifest,
    training_bundle: TrainingBundle,
    registry: AuthorizedVerifierRegistry,
) -> dict[str, Any]:
    """Check complete pairs against the panel commitment in the expected manifest.

    ``expected_manifest`` is the caller's independent pre-run commitment, not
    selected from the receipt. ``receipt`` is a ReceiptValidation integrity report,
    not authority or an unforgeable token.
    No success filter is used: failures/regressions remain visible, and missing or
    unusable replay evidence yields an explicit unscored row, never an omitted row.
    """
    from investigation_world.experience_foundry.external_receipt import ReceiptValidation

    panel = FrozenPanel.model_validate(panel.model_dump(mode="python"))
    receipt = ReceiptValidation.model_validate(receipt.model_dump(mode="python"))
    manifest = TrainingRunManifest.model_validate(expected_manifest.model_dump(mode="python"))
    if (
        receipt.status != "byte_integrity_checked"
        or not _digest(receipt.checkpoint_digest)
        or not receipt.base_model_revision.strip()
        or canonical_hash(receipt.expected_manifest) != canonical_hash(manifest)
        or manifest.parameters.get("frozen_panel_id") != panel.panel_id
        or manifest.run_id != panel.run_id
        or receipt.run_id != panel.run_id
        or receipt.manifest_digest != canonical_hash(manifest)
    ):
        raise ValueError("panel lacks matching pre-intervention manifest commitment")
    training_bundle = TrainingBundle.model_validate(training_bundle.model_dump(mode="python"))
    if (
        training_bundle.bundle_id != manifest.bundle_id
        or canonical_hash(training_bundle) != receipt.bundle_digest
    ):
        raise ValueError("training bundle does not match byte-bound receipt")
    training_task_ids, training_source_ids, training_source_digests = _training_membership(
        training_bundle
    )
    if any(
        case.task.task_id in training_task_ids
        or case.source_id in training_source_ids
        or case.source_digest in training_source_digests
        for case in panel.cases
    ):
        raise ValueError("training/panel overlap")
    before = _attempts_by_case(baseline, panel)
    after = _attempts_by_case(checkpoint, panel)
    pairs = []
    for case in panel.cases:
        base = _evaluate(
            before[case.case_id],
            case,
            panel,
            model_id=manifest.base_model,
            checkpoint_identity=receipt.base_model_revision,
            registry=registry,
        )
        candidate = _evaluate(
            after[case.case_id],
            case,
            panel,
            model_id=manifest.base_model,
            checkpoint_identity=receipt.checkpoint_digest,
            registry=registry,
        )
        scored = base["reward"] is not None and candidate["reward"] is not None
        pairs.append(
            {
                "case_id": case.case_id,
                "baseline": base,
                "checkpoint": candidate,
                "reward_delta": candidate["reward"] - base["reward"] if scored else None,
            }
        )
    complete = all(pair["reward_delta"] is not None for pair in pairs)
    return {
        "panel_id": panel.panel_id,
        "run_id": panel.run_id,
        "status": "paired_outcomes_checked" if complete else "unknown",
        "pairs": pairs,
        "panel_chronology_attestation": "unknown",
        "model_execution_attestation": "unknown",
        "provenance_status": "declared_and_identity_checked",
        "evaluation_evidence": "authorized_offline_reverification",
        "training_validated": False,
        "capability_gain": None,
    }
