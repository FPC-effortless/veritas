from __future__ import annotations

import pytest
from pydantic import ValidationError

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
from investigation_world.trajectory.models import HarnessIdentity

BASE_COMMIT = "fbdb74db7080a078c945506a6c759305f4cd1f78"
TRAJECTORY_MODEL = "src/investigation_world/trajectory/models.py"
ROLLOUT_ADAPTER = "src/investigation_world/trajectory/adapter.py"
PORTABLE_MODELS = "src/investigation_world/portable_runtime/models.py"
HUD_ADAPTER = "src/investigation_world/exporters/hud/adapter.py"

REWARD_COMPONENTS = {TrajectoryMetadataField.REWARD_COMPONENTS}


def _field_rows(
    path: str,
    overrides: dict[
        TrajectoryMetadataField,
        tuple[MetadataCoverage, str, str | None],
    ],
) -> tuple[MetadataFieldCoverage, ...]:
    rows: list[MetadataFieldCoverage] = []
    for field in TrajectoryMetadataField:
        coverage, detail, condition = overrides.get(
            field,
            (MetadataCoverage.PRESENT, "explicitly emitted or deterministically derived", None),
        )
        rows.append(
            MetadataFieldCoverage(
                field=field,
                requirement=(
                    MetadataRequirement.OPTIONAL
                    if field in REWARD_COMPONENTS
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
    conditional = MetadataCoverage.CONDITIONAL
    return ProducerMetadataCoverage(
        producer_id="legacy-foundry-rollout-adapter",
        producer_kind=ProducerKind.TRAJECTORY_PRODUCER,
        emits_trajectory_v2=True,
        fields=_field_rows(
            ROLLOUT_ADAPTER,
            {
                TrajectoryMetadataField.WORLD_ENVIRONMENT_IDENTITY: (
                    conditional,
                    "environment version is native; environment/world IDs and artifacts require adapter context",
                    "RolloutTraceAdapterContext supplies world/environment identity beyond environment_version",
                ),
                TrajectoryMetadataField.MODEL_IDENTITY: (
                    conditional,
                    "legacy RolloutTrace has no model identity",
                    "RolloutTraceAdapterContext.model is populated by the caller",
                ),
                TrajectoryMetadataField.AGENT_IDENTITY: (
                    conditional,
                    "legacy RolloutTrace has no agent identity",
                    "RolloutTraceAdapterContext.agent is populated by the caller",
                ),
                TrajectoryMetadataField.HARNESS_IDENTITY: (
                    conditional,
                    "harness version is native but harness ID requires adapter context",
                    "RolloutTraceAdapterContext.harness_id is populated by the caller",
                ),
                TrajectoryMetadataField.HARNESS_CONFIG_IDENTITY: (
                    MetadataCoverage.ABSENT,
                    "TrajectoryV2 HarnessIdentity has no harness configuration digest field",
                    None,
                ),
                TrajectoryMetadataField.RUNTIME_IDENTITY: (
                    conditional,
                    "runtime version is native but runtime ID requires adapter context",
                    "RolloutTraceAdapterContext.runtime_id is populated by the caller",
                ),
                TrajectoryMetadataField.VERIFIER_IDENTITY: (
                    conditional,
                    "verifier scores are native but verifier identity requires adapter context",
                    "RolloutTraceAdapterContext.verifier is populated by the caller",
                ),
                TrajectoryMetadataField.SEED_RESET_IDENTITY: (
                    conditional,
                    "task seed is native; reset ID/index require adapter context",
                    "RolloutTraceAdapterContext supplies reset_id/reset_index",
                ),
                TrajectoryMetadataField.OBSERVATIONS: (
                    conditional,
                    "legacy events do not standardize observation references",
                    "RolloutTraceAdapterContext supplies observation references",
                ),
                TrajectoryMetadataField.PROVIDER_CALLS: (
                    conditional,
                    "legacy RolloutTrace has no provider call summaries",
                    "RolloutTraceAdapterContext supplies provider_calls",
                ),
                TrajectoryMetadataField.PROVIDER_REQUEST_ID: (
                    conditional,
                    "provider request IDs exist only inside supplied provider summaries",
                    "provider calls are supplied with request_id values",
                ),
                TrajectoryMetadataField.ARTIFACT_EVIDENCE_REFERENCES: (
                    conditional,
                    "world/artifact/evidence references are not native to RolloutTrace",
                    "RolloutTraceAdapterContext supplies artifact/evidence references",
                ),
                TrajectoryMetadataField.TOKEN_USAGE: (
                    conditional,
                    "token totals are derived only from complete supplied provider calls",
                    "provider call token accounting is supplied completely",
                ),
                TrajectoryMetadataField.COST_USAGE: (
                    conditional,
                    "environment cost is native; total/provider cost requires complete provider accounting",
                    "provider call cost accounting is supplied completely",
                ),
                TrajectoryMetadataField.TIME_USAGE: (
                    conditional,
                    "legacy events have no duration and elapsed time is external context",
                    "RolloutTraceAdapterContext.elapsed_s is populated by the caller",
                ),
                TrajectoryMetadataField.TERMINATION_TRUNCATION: (
                    conditional,
                    "termination reason is native but terminated/truncated booleans are not inferred",
                    "RolloutTraceAdapterContext supplies terminated/truncated",
                ),
                TrajectoryMetadataField.FAILURE_ORIGIN_CLASSIFICATION: (
                    conditional,
                    "ambiguous termination is intentionally not promoted to a failure origin",
                    "RolloutTraceAdapterContext supplies a failure classification",
                ),
            },
        ),
        notes=(
            "unknown legacy facts remain unknown instead of being fabricated",
            "resource calls and source provenance are deterministically derived",
        ),
    )


def _portable_runtime() -> ProducerMetadataCoverage:
    absent = MetadataCoverage.ABSENT
    unsupported = MetadataCoverage.UNSUPPORTED
    conditional = MetadataCoverage.CONDITIONAL
    return ProducerMetadataCoverage(
        producer_id="portable-operational-runtime-direct",
        producer_kind=ProducerKind.SEMANTIC_RUNTIME,
        emits_trajectory_v2=False,
        fields=_field_rows(
            PORTABLE_MODELS,
            {
                TrajectoryMetadataField.WORLD_ENVIRONMENT_IDENTITY: (
                    conditional,
                    "identity is available from the bound portable contract, not emitted on reset/step results",
                    "caller retains the PortableOperationalContract beside runtime results",
                ),
                TrajectoryMetadataField.TASK_IDENTITY: (
                    conditional,
                    "task identity is available from the bound contract, not emitted on runtime results",
                    "caller retains the PortableOperationalContract beside runtime results",
                ),
                TrajectoryMetadataField.MODEL_IDENTITY: (absent, "runtime results carry no model identity", None),
                TrajectoryMetadataField.AGENT_IDENTITY: (absent, "runtime results carry no agent identity", None),
                TrajectoryMetadataField.HARNESS_IDENTITY: (absent, "runtime results carry no harness identity", None),
                TrajectoryMetadataField.HARNESS_CONFIG_IDENTITY: (absent, "runtime results carry no harness configuration identity", None),
                TrajectoryMetadataField.RUNTIME_IDENTITY: (absent, "runtime result models do not identify runtime/version", None),
                TrajectoryMetadataField.VERIFIER_IDENTITY: (absent, "reward components do not identify the verifier implementation", None),
                TrajectoryMetadataField.SEED_RESET_IDENTITY: (
                    conditional,
                    "reset accepts a seed but PortableResetResult does not preserve seed/reset ID",
                    "caller records the reset request separately",
                ),
                TrajectoryMetadataField.ACTION_TOOL_RESOURCE_CALLS: (
                    conditional,
                    "PortableStepRequest names an invocation but result models do not emit a call summary",
                    "caller preserves request/result pairs",
                ),
                TrajectoryMetadataField.PROVIDER_CALLS: (unsupported, "portable runtime has no model-provider call surface", None),
                TrajectoryMetadataField.PROVIDER_REQUEST_ID: (unsupported, "portable runtime has no provider request identity", None),
                TrajectoryMetadataField.ARTIFACT_EVIDENCE_REFERENCES: (
                    conditional,
                    "submission can reference evidence IDs but runtime results do not emit canonical trajectory references",
                    "caller retains submission/contract evidence identities",
                ),
                TrajectoryMetadataField.STATE_DIGESTS_TRANSITIONS: (
                    conditional,
                    "results expose the post-state digest but not an explicit before/after transition pair",
                    "caller sequences reset/step results",
                ),
                TrajectoryMetadataField.TOKEN_USAGE: (unsupported, "runtime models have no token accounting", None),
                TrajectoryMetadataField.COST_USAGE: (unsupported, "budget resources are not a canonical monetary usage total", None),
                TrajectoryMetadataField.TIME_USAGE: (unsupported, "runtime models have no elapsed/duration accounting", None),
                TrajectoryMetadataField.FAILURE_ORIGIN_CLASSIFICATION: (
                    conditional,
                    "PortableFailureStatus preserves a runtime failure code but not TrajectoryV2 failure-origin taxonomy",
                    "an integration adapter maps failure code/context without inventing attribution",
                ),
                TrajectoryMetadataField.PUBLIC_PRIVATE_VISIBILITY: (unsupported, "portable result models have no trajectory visibility classification", None),
                TrajectoryMetadataField.PROVENANCE_SOURCE_REFERENCES: (absent, "portable results carry no trajectory provenance record", None),
            },
        ),
        notes=("semantic runtime is not itself a TrajectoryV2 producer",),
    )


def _hud_adapter() -> ProducerMetadataCoverage:
    absent = MetadataCoverage.ABSENT
    unsupported = MetadataCoverage.UNSUPPORTED
    conditional = MetadataCoverage.CONDITIONAL
    return ProducerMetadataCoverage(
        producer_id="hud-operational-adapter",
        producer_kind=ProducerKind.EXTERNAL_ADAPTER,
        emits_trajectory_v2=False,
        fields=_field_rows(
            HUD_ADAPTER,
            {
                TrajectoryMetadataField.MODEL_IDENTITY: (absent, "HUD adapter/meter carries no model identity", None),
                TrajectoryMetadataField.AGENT_IDENTITY: (absent, "HUD adapter/meter carries no agent identity", None),
                TrajectoryMetadataField.HARNESS_IDENTITY: (absent, "HUD protocol/SDK metadata is not a harness execution identity", None),
                TrajectoryMetadataField.HARNESS_CONFIG_IDENTITY: (absent, "HUD adapter exposes no harness config digest", None),
                TrajectoryMetadataField.RUNTIME_IDENTITY: (
                    conditional,
                    "adapter/protocol versions are emitted but a custom bound PortableRuntimeProtocol identity is not",
                    "integration records the actual bound runtime identity separately",
                ),
                TrajectoryMetadataField.VERIFIER_IDENTITY: (absent, "grade result carries reward without verifier identity", None),
                TrajectoryMetadataField.SEED_RESET_IDENTITY: (
                    conditional,
                    "tasks.start receives a seed but HudTaskStart does not preserve it as reset identity",
                    "calling harness records start(seed, session_id)",
                ),
                TrajectoryMetadataField.ACTION_TOOL_RESOURCE_CALLS: (
                    conditional,
                    "metering records tool_name but not a canonical request/result/resource-call summary",
                    "calling harness preserves tool arguments and returned PortableStepResult",
                ),
                TrajectoryMetadataField.PROVIDER_CALLS: (unsupported, "HUD operational metering has no model-provider call summaries", None),
                TrajectoryMetadataField.PROVIDER_REQUEST_ID: (unsupported, "HUD metering has no provider request IDs", None),
                TrajectoryMetadataField.ARTIFACT_EVIDENCE_REFERENCES: (
                    conditional,
                    "public contract identity is emitted but canonical artifact/evidence trajectory references are not",
                    "integration retains contract/submission evidence references",
                ),
                TrajectoryMetadataField.STATE_DIGESTS_TRANSITIONS: (
                    conditional,
                    "metering emits post-state digest but not before/after transition pairs",
                    "calling harness sequences metering events/results",
                ),
                TrajectoryMetadataField.REWARD_COMPONENTS: (
                    conditional,
                    "PortableStepResult can carry reward components but HudMeteringEvent carries only scalar reward",
                    "calling harness retains full PortableStepResult",
                ),
                TrajectoryMetadataField.TOKEN_USAGE: (unsupported, "HUD metering has no token accounting", None),
                TrajectoryMetadataField.COST_USAGE: (unsupported, "HUD metering has no cost accounting", None),
                TrajectoryMetadataField.TIME_USAGE: (unsupported, "HUD metering has no duration/elapsed accounting", None),
                TrajectoryMetadataField.FAILURE_ORIGIN_CLASSIFICATION: (
                    conditional,
                    "PortableStepResult can carry a runtime failure but metering does not preserve failure classification",
                    "calling harness retains the full PortableStepResult",
                ),
                TrajectoryMetadataField.PUBLIC_PRIVATE_VISIBILITY: (
                    conditional,
                    "metering is documented public-only and private contract identity is optional metadata, without TrajectoryV2 visibility classes",
                    "integration applies trajectory visibility when constructing a trajectory",
                ),
                TrajectoryMetadataField.PROVENANCE_SOURCE_REFERENCES: (
                    conditional,
                    "adapter metadata exposes adapter/protocol/contract IDs but does not emit a content-bound TrajectoryV2 provenance record",
                    "integration converts adapter metadata to canonical provenance",
                ),
            },
        ),
        notes=("HUD metering is observational and is not a TrajectoryV2 producer",),
    )


def _audit() -> TrajectoryMetadataAudit:
    return TrajectoryMetadataAudit(
        base_commit_sha=BASE_COMMIT,
        producers=(_hud_adapter(), _portable_runtime(), _legacy_rollout()),
        interface_gaps=(
            InterfaceGapRequest(
                gap_id="TRACE-GAP-HARNESS-CONFIG",
                field=TrajectoryMetadataField.HARNESS_CONFIG_IDENTITY,
                owner="trajectory schema authority",
                requested_change="add a content-bound harness configuration identity without weakening current public/private boundaries",
                evidence_paths=(TRAJECTORY_MODEL,),
                rationale="HarnessIdentity currently carries only harness_id and version, so exact harness config cannot affect trajectory identity",
            ),
            InterfaceGapRequest(
                gap_id="TRACE-GAP-PORTABLE-PRODUCER",
                field=TrajectoryMetadataField.PROVENANCE_SOURCE_REFERENCES,
                owner="trajectory/portable integration",
                requested_change="define an additive PortableOperationalRuntime interaction-to-TrajectoryV2 adapter",
                evidence_paths=(PORTABLE_MODELS,),
                rationale="portable runtime preserves semantic execution results but does not emit trajectory provenance or execution identities",
            ),
            InterfaceGapRequest(
                gap_id="TRACE-GAP-HUD-CAPTURE",
                field=TrajectoryMetadataField.PROVIDER_CALLS,
                owner="HUD harness integration",
                requested_change="capture harness/provider/accounting events around HUD execution before constructing TrajectoryV2",
                evidence_paths=(HUD_ADAPTER,),
                rationale="HUD public metering preserves task/state/reward/termination but not model-provider or usage metadata",
            ),
        ),
    )


def test_audit_covers_portable_runtime_external_adapter_and_legacy_producer() -> None:
    audit = _audit()

    assert audit.status == AuditStatus.GAPS_FOUND
    assert {item.producer_kind for item in audit.producers} == {
        ProducerKind.TRAJECTORY_PRODUCER,
        ProducerKind.SEMANTIC_RUNTIME,
        ProducerKind.EXTERNAL_ADAPTER,
    }
    assert {item.producer_id for item in audit.producers} == {
        "legacy-foundry-rollout-adapter",
        "portable-operational-runtime-direct",
        "hud-operational-adapter",
    }
    assert all(len(item.fields) == len(TrajectoryMetadataField) for item in audit.producers)


def test_schema_presence_is_not_counted_as_legacy_producer_completeness() -> None:
    legacy = _legacy_rollout()

    assert legacy.completeness == ProducerCompleteness.INCOMPLETE
    assert legacy.coverage_for(TrajectoryMetadataField.MODEL_IDENTITY).coverage == MetadataCoverage.CONDITIONAL
    assert legacy.coverage_for(TrajectoryMetadataField.HARNESS_CONFIG_IDENTITY).coverage == MetadataCoverage.ABSENT
    assert legacy.coverage_for(TrajectoryMetadataField.PROVENANCE_SOURCE_REFERENCES).coverage == MetadataCoverage.PRESENT


def test_portable_runtime_semantics_do_not_imply_trajectory_metadata() -> None:
    portable = _portable_runtime()

    assert not portable.emits_trajectory_v2
    assert portable.completeness == ProducerCompleteness.INCOMPLETE
    assert portable.coverage_for(TrajectoryMetadataField.OBSERVATIONS).coverage == MetadataCoverage.PRESENT
    assert portable.coverage_for(TrajectoryMetadataField.TERMINATION_TRUNCATION).coverage == MetadataCoverage.PRESENT
    assert portable.coverage_for(TrajectoryMetadataField.MODEL_IDENTITY).coverage == MetadataCoverage.ABSENT
    assert portable.coverage_for(TrajectoryMetadataField.TOKEN_USAGE).coverage == MetadataCoverage.UNSUPPORTED


def test_hud_metering_is_not_generalized_into_provider_or_usage_capture() -> None:
    hud = _hud_adapter()

    assert not hud.emits_trajectory_v2
    assert hud.coverage_for(TrajectoryMetadataField.WORLD_ENVIRONMENT_IDENTITY).coverage == MetadataCoverage.PRESENT
    assert hud.coverage_for(TrajectoryMetadataField.PROVIDER_CALLS).coverage == MetadataCoverage.UNSUPPORTED
    assert hud.coverage_for(TrajectoryMetadataField.TIME_USAGE).coverage == MetadataCoverage.UNSUPPORTED
    assert hud.coverage_for(TrajectoryMetadataField.STATE_DIGESTS_TRANSITIONS).coverage == MetadataCoverage.CONDITIONAL


def test_harness_config_gap_is_grounded_in_current_trajectory_schema() -> None:
    assert "config_sha256" not in HarnessIdentity.model_fields
    gap = next(item for item in _audit().interface_gaps if item.gap_id == "TRACE-GAP-HARNESS-CONFIG")
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


def test_stale_copied_audit_status_is_rejected_at_serialization_boundary() -> None:
    audit = _audit()
    stale = audit.model_copy(update={"status": AuditStatus.COMPLETE})

    with pytest.raises(ValidationError, match="status does not match"):
        serialize_metadata_audit(stale)
