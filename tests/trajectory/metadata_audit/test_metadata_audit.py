from __future__ import annotations

import pytest
from pydantic import ValidationError

from investigation_world.foundry.models import DistributionSplit, RolloutTrace, TraceEvent
from investigation_world.trajectory.adapter import trajectory_v2_from_rollout_trace
from investigation_world.trajectory.audit import (
    AuditStatus,
    InterfaceGapRequest,
    MetadataCoverage,
    MetadataFieldCoverage,
    MetadataRequirement,
    ProducerCompleteness,
    ProducerKind,
    ProducerMetadataCoverage,
    TrajectoryMetadataAudit,
    TrajectoryMetadataField,
    serialize_metadata_audit,
)
from investigation_world.trajectory.models import HarnessIdentity, VisibilityClass

BASE_COMMIT = "fbdb74db7080a078c945506a6c759305f4cd1f78"
TRAJECTORY_MODEL = "src/investigation_world/trajectory/models.py"
FOUNDRY_MODELS = "src/investigation_world/foundry/models.py"
ROLLOUT_ADAPTER = "src/investigation_world/trajectory/adapter.py"
PORTABLE_MODELS = "src/investigation_world/portable_runtime/models.py"
HUD_ADAPTER = "src/investigation_world/exporters/hud/adapter.py"

OPTIONAL_FIELDS = {TrajectoryMetadataField.REWARD_COMPONENTS}


def _rows(
    path: str,
    *,
    present: set[TrajectoryMetadataField] | None = None,
    conditional: set[TrajectoryMetadataField] | None = None,
    unsupported: set[TrajectoryMetadataField] | None = None,
) -> tuple[MetadataFieldCoverage, ...]:
    present = present or set()
    conditional = conditional or set()
    unsupported = unsupported or set()
    rows: list[MetadataFieldCoverage] = []
    for field in TrajectoryMetadataField:
        if field in present:
            coverage = MetadataCoverage.PRESENT
            detail = "emitted or deterministically derived"
            condition = None
        elif field in conditional:
            coverage = MetadataCoverage.CONDITIONAL
            detail = "available only with integration evidence"
            condition = "caller preserves or supplies the missing evidence"
        elif field in unsupported:
            coverage = MetadataCoverage.UNSUPPORTED
            detail = "outside this path's current emitted interface"
            condition = None
        else:
            coverage = MetadataCoverage.ABSENT
            detail = "not preserved by this path"
            condition = None
        rows.append(
            MetadataFieldCoverage(
                field=field,
                requirement=(
                    MetadataRequirement.OPTIONAL
                    if field in OPTIONAL_FIELDS
                    else MetadataRequirement.REQUIRED
                ),
                coverage=coverage,
                evidence_paths=(path,),
                detail=detail,
                condition=condition,
            )
        )
    return tuple(rows)


def _legacy_rollout() -> ProducerMetadataCoverage:
    present = {
        TrajectoryMetadataField.TASK_IDENTITY,
        TrajectoryMetadataField.ACTION_TOOL_RESOURCE_CALLS,
        TrajectoryMetadataField.STATE_DIGESTS_TRANSITIONS,
        TrajectoryMetadataField.REWARD_COMPONENTS,
        TrajectoryMetadataField.PROVENANCE_SOURCE_REFERENCES,
    }
    conditional = {
        TrajectoryMetadataField.WORLD_ENVIRONMENT_IDENTITY,
        TrajectoryMetadataField.MODEL_IDENTITY,
        TrajectoryMetadataField.AGENT_IDENTITY,
        TrajectoryMetadataField.HARNESS_IDENTITY,
        TrajectoryMetadataField.RUNTIME_IDENTITY,
        TrajectoryMetadataField.VERIFIER_IDENTITY,
        TrajectoryMetadataField.SEED_RESET_IDENTITY,
        TrajectoryMetadataField.OBSERVATIONS,
        TrajectoryMetadataField.PROVIDER_CALLS,
        TrajectoryMetadataField.PROVIDER_REQUEST_ID,
        TrajectoryMetadataField.ARTIFACT_EVIDENCE_REFERENCES,
        TrajectoryMetadataField.TOKEN_USAGE,
        TrajectoryMetadataField.COST_USAGE,
        TrajectoryMetadataField.TIME_USAGE,
        TrajectoryMetadataField.TERMINATION_TRUNCATION,
        TrajectoryMetadataField.FAILURE_ORIGIN_CLASSIFICATION,
    }
    return ProducerMetadataCoverage(
        producer_id="legacy-foundry-rollout-adapter",
        producer_kind=ProducerKind.TRAJECTORY_PRODUCER,
        emits_trajectory_v2=True,
        fields=_rows(
            ROLLOUT_ADAPTER,
            present=present,
            conditional=conditional,
        ),
        notes=(
            "legacy visibility values are adapter defaults, not producer evidence",
            "resource calls and source provenance are derived",
        ),
    )


def _portable_runtime() -> ProducerMetadataCoverage:
    present = {
        TrajectoryMetadataField.OBSERVATIONS,
        TrajectoryMetadataField.REWARD_COMPONENTS,
        TrajectoryMetadataField.TERMINATION_TRUNCATION,
    }
    conditional = {
        TrajectoryMetadataField.WORLD_ENVIRONMENT_IDENTITY,
        TrajectoryMetadataField.TASK_IDENTITY,
        TrajectoryMetadataField.SEED_RESET_IDENTITY,
        TrajectoryMetadataField.ACTION_TOOL_RESOURCE_CALLS,
        TrajectoryMetadataField.ARTIFACT_EVIDENCE_REFERENCES,
        TrajectoryMetadataField.STATE_DIGESTS_TRANSITIONS,
        TrajectoryMetadataField.FAILURE_ORIGIN_CLASSIFICATION,
    }
    unsupported = {
        TrajectoryMetadataField.PROVIDER_CALLS,
        TrajectoryMetadataField.PROVIDER_REQUEST_ID,
        TrajectoryMetadataField.TOKEN_USAGE,
        TrajectoryMetadataField.COST_USAGE,
        TrajectoryMetadataField.TIME_USAGE,
        TrajectoryMetadataField.PUBLIC_PRIVATE_VISIBILITY,
    }
    return ProducerMetadataCoverage(
        producer_id="portable-operational-runtime-direct",
        producer_kind=ProducerKind.SEMANTIC_RUNTIME,
        emits_trajectory_v2=False,
        fields=_rows(
            PORTABLE_MODELS,
            present=present,
            conditional=conditional,
            unsupported=unsupported,
        ),
        notes=("semantic runtime is not itself a TrajectoryV2 producer",),
    )


def _hud_adapter() -> ProducerMetadataCoverage:
    present = {
        TrajectoryMetadataField.WORLD_ENVIRONMENT_IDENTITY,
        TrajectoryMetadataField.TASK_IDENTITY,
        TrajectoryMetadataField.OBSERVATIONS,
        TrajectoryMetadataField.TERMINATION_TRUNCATION,
    }
    conditional = {
        TrajectoryMetadataField.RUNTIME_IDENTITY,
        TrajectoryMetadataField.SEED_RESET_IDENTITY,
        TrajectoryMetadataField.ACTION_TOOL_RESOURCE_CALLS,
        TrajectoryMetadataField.ARTIFACT_EVIDENCE_REFERENCES,
        TrajectoryMetadataField.STATE_DIGESTS_TRANSITIONS,
        TrajectoryMetadataField.REWARD_COMPONENTS,
        TrajectoryMetadataField.FAILURE_ORIGIN_CLASSIFICATION,
        TrajectoryMetadataField.PUBLIC_PRIVATE_VISIBILITY,
        TrajectoryMetadataField.PROVENANCE_SOURCE_REFERENCES,
    }
    unsupported = {
        TrajectoryMetadataField.PROVIDER_CALLS,
        TrajectoryMetadataField.PROVIDER_REQUEST_ID,
        TrajectoryMetadataField.TOKEN_USAGE,
        TrajectoryMetadataField.COST_USAGE,
        TrajectoryMetadataField.TIME_USAGE,
    }
    return ProducerMetadataCoverage(
        producer_id="hud-operational-adapter",
        producer_kind=ProducerKind.EXTERNAL_ADAPTER,
        emits_trajectory_v2=False,
        fields=_rows(
            HUD_ADAPTER,
            present=present,
            conditional=conditional,
            unsupported=unsupported,
        ),
        notes=("HUD public metering is not a TrajectoryV2 producer",),
    )


def _audit() -> TrajectoryMetadataAudit:
    return TrajectoryMetadataAudit(
        base_commit_sha=BASE_COMMIT,
        producers=(_hud_adapter(), _portable_runtime(), _legacy_rollout()),
        interface_gaps=(
            InterfaceGapRequest(
                gap_id="TRACE-GAP-LEGACY-VISIBILITY",
                field=TrajectoryMetadataField.PUBLIC_PRIVATE_VISIBILITY,
                owner="Foundry/trajectory adapter authority",
                requested_change=(
                    "add explicit sensitivity metadata to legacy trace events and "
                    "preserve it during TrajectoryV2 conversion"
                ),
                evidence_paths=(FOUNDRY_MODELS, ROLLOUT_ADAPTER),
                rationale=(
                    "TraceEvent carries an arbitrary payload without visibility "
                    "metadata, while the adapter assigns PUBLIC unconditionally"
                ),
            ),
            InterfaceGapRequest(
                gap_id="TRACE-GAP-HARNESS-CONFIG",
                field=TrajectoryMetadataField.HARNESS_CONFIG_IDENTITY,
                owner="trajectory schema authority",
                requested_change=(
                    "add a content-bound harness configuration identity without "
                    "weakening visibility boundaries"
                ),
                evidence_paths=(TRAJECTORY_MODEL,),
                rationale=(
                    "HarnessIdentity has only harness_id and version, so exact "
                    "configuration cannot affect trajectory identity"
                ),
            ),
            InterfaceGapRequest(
                gap_id="TRACE-GAP-PORTABLE-PRODUCER",
                field=TrajectoryMetadataField.PROVENANCE_SOURCE_REFERENCES,
                owner="trajectory/portable integration",
                requested_change=(
                    "define an additive portable interaction-to-TrajectoryV2 "
                    "capture adapter"
                ),
                evidence_paths=(PORTABLE_MODELS,),
                rationale=(
                    "portable runtime preserves semantic results but does not "
                    "emit trajectory execution identity or provenance"
                ),
            ),
            InterfaceGapRequest(
                gap_id="TRACE-GAP-HUD-CAPTURE",
                field=TrajectoryMetadataField.PROVIDER_CALLS,
                owner="HUD harness integration",
                requested_change=(
                    "capture harness/provider/accounting events around HUD "
                    "execution before constructing TrajectoryV2"
                ),
                evidence_paths=(HUD_ADAPTER,),
                rationale=(
                    "HUD metering preserves task/state/reward/termination but "
                    "not model-provider or usage metadata"
                ),
            ),
        ),
    )


def test_audit_covers_three_distinct_producer_paths() -> None:
    audit = _audit()

    assert audit.status == AuditStatus.GAPS_FOUND
    assert {item.producer_kind for item in audit.producers} == {
        ProducerKind.TRAJECTORY_PRODUCER,
        ProducerKind.SEMANTIC_RUNTIME,
        ProducerKind.EXTERNAL_ADAPTER,
    }
    assert all(
        len(item.fields) == len(TrajectoryMetadataField)
        for item in audit.producers
    )


def test_schema_presence_is_not_legacy_producer_completeness() -> None:
    legacy = _legacy_rollout()

    assert legacy.completeness == ProducerCompleteness.INCOMPLETE
    model = legacy.coverage_for(TrajectoryMetadataField.MODEL_IDENTITY)
    config = legacy.coverage_for(
        TrajectoryMetadataField.HARNESS_CONFIG_IDENTITY
    )
    provenance = legacy.coverage_for(
        TrajectoryMetadataField.PROVENANCE_SOURCE_REFERENCES
    )
    assert model.coverage == MetadataCoverage.CONDITIONAL
    assert config.coverage == MetadataCoverage.ABSENT
    assert provenance.coverage == MetadataCoverage.PRESENT


def test_legacy_adapter_public_default_is_not_visibility_evidence() -> None:
    trace = RolloutTrace(
        trace_id="trace-unclassified",
        environment_version="1",
        task_id="task-unclassified",
        task_seed=7,
        split=DistributionSplit.IID_TEST,
        taskset_version="1",
        harness_version="1",
        runtime_version="1",
        initial_state_hash="state-before",
        events=[
            TraceEvent(
                step=0,
                event_type="unclassified",
                payload={"content": "no visibility metadata"},
            )
        ],
    )

    trajectory = trajectory_v2_from_rollout_trace(trace)
    visibility = _legacy_rollout().coverage_for(
        TrajectoryMetadataField.PUBLIC_PRIVATE_VISIBILITY
    )
    gap = next(
        item
        for item in _audit().interface_gaps
        if item.gap_id == "TRACE-GAP-LEGACY-VISIBILITY"
    )

    assert trajectory.events[0].visibility == VisibilityClass.PUBLIC
    assert trajectory.visibility == VisibilityClass.PUBLIC
    assert visibility.coverage == MetadataCoverage.ABSENT
    assert gap.field == TrajectoryMetadataField.PUBLIC_PRIVATE_VISIBILITY
    assert gap.owner == "Foundry/trajectory adapter authority"


def test_portable_semantics_do_not_imply_trajectory_metadata() -> None:
    portable = _portable_runtime()

    assert not portable.emits_trajectory_v2
    assert portable.completeness == ProducerCompleteness.INCOMPLETE
    observation = portable.coverage_for(TrajectoryMetadataField.OBSERVATIONS)
    model = portable.coverage_for(TrajectoryMetadataField.MODEL_IDENTITY)
    tokens = portable.coverage_for(TrajectoryMetadataField.TOKEN_USAGE)
    assert observation.coverage == MetadataCoverage.PRESENT
    assert model.coverage == MetadataCoverage.ABSENT
    assert tokens.coverage == MetadataCoverage.UNSUPPORTED


def test_hud_metering_is_not_provider_or_usage_capture() -> None:
    hud = _hud_adapter()

    assert not hud.emits_trajectory_v2
    world = hud.coverage_for(
        TrajectoryMetadataField.WORLD_ENVIRONMENT_IDENTITY
    )
    provider = hud.coverage_for(TrajectoryMetadataField.PROVIDER_CALLS)
    elapsed = hud.coverage_for(TrajectoryMetadataField.TIME_USAGE)
    state = hud.coverage_for(
        TrajectoryMetadataField.STATE_DIGESTS_TRANSITIONS
    )
    assert world.coverage == MetadataCoverage.PRESENT
    assert provider.coverage == MetadataCoverage.UNSUPPORTED
    assert elapsed.coverage == MetadataCoverage.UNSUPPORTED
    assert state.coverage == MetadataCoverage.CONDITIONAL


def test_harness_config_gap_is_grounded_in_current_schema() -> None:
    assert "config_sha256" not in HarnessIdentity.model_fields
    gap = next(
        item
        for item in _audit().interface_gaps
        if item.gap_id == "TRACE-GAP-HARNESS-CONFIG"
    )
    assert gap.owner == "trajectory schema authority"
    assert gap.field == TrajectoryMetadataField.HARNESS_CONFIG_IDENTITY


def test_conditional_metadata_requires_an_explicit_condition() -> None:
    with pytest.raises(ValidationError, match="must state its condition"):
        MetadataFieldCoverage(
            field=TrajectoryMetadataField.MODEL_IDENTITY,
            requirement=MetadataRequirement.REQUIRED,
            coverage=MetadataCoverage.CONDITIONAL,
            evidence_paths=(ROLLOUT_ADAPTER,),
            detail="caller-dependent",
        )


def test_producer_row_cannot_omit_an_audit_field() -> None:
    legacy = _legacy_rollout()
    incomplete = tuple(
        item
        for item in legacy.fields
        if item.field != TrajectoryMetadataField.FAILURE_ORIGIN_CLASSIFICATION
    )

    with pytest.raises(ValidationError, match="omits metadata fields"):
        ProducerMetadataCoverage(
            producer_id="incomplete",
            producer_kind=ProducerKind.TRAJECTORY_PRODUCER,
            emits_trajectory_v2=True,
            fields=incomplete,
        )


def test_audit_serialization_is_deterministic_and_content_bound() -> None:
    first = _audit()
    second = TrajectoryMetadataAudit(
        base_commit_sha=BASE_COMMIT,
        producers=tuple(reversed(first.producers)),
        interface_gaps=tuple(reversed(first.interface_gaps)),
    )

    assert first.audit_id == second.audit_id
    assert first.content_sha256 == second.content_sha256
    assert serialize_metadata_audit(first) == serialize_metadata_audit(second)


def test_stale_copied_audit_status_is_rejected() -> None:
    audit = _audit()
    stale = audit.model_copy(update={"status": AuditStatus.COMPLETE})

    with pytest.raises(ValidationError, match="status does not match"):
        serialize_metadata_audit(stale)
