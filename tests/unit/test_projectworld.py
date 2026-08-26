from datetime import datetime, timezone

from investigation_world.projectworld import (
    OperationalProjectWorldRuntime,
    ProjectAction,
    ProjectActionType,
    ProjectPhase,
    ProjectRole,
    construction_episode,
)
from investigation_world.projectworld.sources import (
    FusionTarget,
    NormalizedSourceRecord,
    chunk_transcript,
    construction_source_manifest,
    fuse_records,
)


def action(kind, object_type, object_id, **parameters):
    return ProjectAction(
        action_type=kind,
        target_object_type=object_type,
        target_object_id=object_id,
        parameters=parameters,
    )


def test_private_oracle_is_not_public():
    episode = construction_episode()
    payload = episode.public_payload()
    assert "oracle" not in payload
    assert "evidence" not in payload


def test_role_observations_are_namespace_filtered():
    episode = construction_episode()
    runtime = OperationalProjectWorldRuntime(episode)
    architect = runtime.observation_for(ProjectRole.ARCHITECT)
    assert all(item.namespace != "commercial" for item in architect.state)
    assert any(item.namespace == "design" for item in architect.state)


def test_unauthorized_design_approval_is_rejected():
    runtime = OperationalProjectWorldRuntime(construction_episode())
    result = runtime.act(
        ProjectRole.SUBCONTRACTOR,
        ProjectAction(
            action_type=ProjectActionType.APPROVE_DESIGN,
            target_object_type="design",
            target_object_id="D-001",
            evidence_ids=["EV-DESIGN-REVIEW"],
        ),
    )
    assert not result.applied
    assert not result.authorized


def _move_to_construction(runtime):
    assert runtime.act(
        ProjectRole.PROJECT_MANAGER,
        ProjectAction(
            action_type=ProjectActionType.APPROVE_DESIGN,
            target_object_type="design",
            target_object_id="D-001",
            evidence_ids=["EV-DESIGN-REVIEW"],
        ),
    ).applied
    for phase in [ProjectPhase.PRECONSTRUCTION, ProjectPhase.PROCUREMENT, ProjectPhase.CONSTRUCTION]:
        assert runtime.act(
            ProjectRole.PROJECT_MANAGER,
            ProjectAction(
                action_type=ProjectActionType.ADVANCE_PHASE,
                target_object_type="project",
                target_object_id="CONSTRUCTION-001",
                parameters={"phase": phase.value},
                evidence_ids=["EV-PHASE-GATE"],
            ),
        ).applied


def test_dependencies_duration_and_hidden_disruption_are_executable():
    runtime = OperationalProjectWorldRuntime(construction_episode())
    _move_to_construction(runtime)

    assert not runtime.act(
        ProjectRole.SITE_MANAGER,
        action(ProjectActionType.START_ACTIVITY, "activity", "A200"),
    ).applied

    assert runtime.act(
        ProjectRole.SITE_MANAGER,
        action(ProjectActionType.START_ACTIVITY, "activity", "A100"),
    ).applied
    assert not runtime.act(
        ProjectRole.SITE_MANAGER,
        action(ProjectActionType.COMPLETE_ACTIVITY, "activity", "A100"),
    ).applied
    runtime.advance(2)
    assert runtime.act(
        ProjectRole.SITE_MANAGER,
        action(ProjectActionType.COMPLETE_ACTIVITY, "activity", "A100"),
    ).applied

    assert runtime.act(ProjectRole.SITE_MANAGER, action(ProjectActionType.START_ACTIVITY, "activity", "A200")).applied
    runtime.advance(2)
    assert runtime.act(ProjectRole.SITE_MANAGER, action(ProjectActionType.COMPLETE_ACTIVITY, "activity", "A200")).applied
    assert runtime.act(ProjectRole.SITE_MANAGER, action(ProjectActionType.START_ACTIVITY, "activity", "A300")).applied
    runtime.advance(1)
    assert runtime.act(ProjectRole.SITE_MANAGER, action(ProjectActionType.COMPLETE_ACTIVITY, "activity", "A300")).applied

    assert not runtime.act(
        ProjectRole.SITE_MANAGER,
        action(ProjectActionType.START_ACTIVITY, "activity", "A400"),
    ).applied
    assert runtime.act(
        ProjectRole.SITE_MANAGER,
        ProjectAction(
            action_type=ProjectActionType.MITIGATE_RISK,
            target_object_type="activity",
            target_object_id="A400",
            evidence_ids=["EV-MITIGATION"],
        ),
    ).applied
    assert runtime.act(
        ProjectRole.SITE_MANAGER,
        action(ProjectActionType.START_ACTIVITY, "activity", "A400"),
    ).applied


def test_source_fusion_preserves_conflicts_and_prefers_authority():
    community = NormalizedSourceRecord(
        source_id="community",
        canonical_type=FusionTarget.COST,
        canonical_id="WP-1",
        field_name="estimate",
        value=100.0,
        confidence=0.9,
        authority_rank=50,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    authoritative = NormalizedSourceRecord(
        source_id="verified",
        canonical_type=FusionTarget.COST,
        canonical_id="WP-1",
        field_name="estimate",
        value=120.0,
        confidence=0.8,
        authority_rank=90,
        observed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    fused = fuse_records([community, authoritative])
    assert fused[0].value == 120.0
    assert fused[0].winning_source_id == "verified"
    assert fused[0].alternatives[0]["value"] == 100.0


def test_authorized_transcript_chunker_keeps_provenance():
    source = construction_source_manifest().transcript_sources[0]
    chunks = chunk_transcript(source, "word " * 900, words_per_chunk=300, overlap_words=50)
    assert len(chunks) >= 3
    assert all(item.source_id == source.source_id for item in chunks)
    assert all(item.provenance["ingestion_mode"] == "authorized_local_transcript" for item in chunks)


def test_project_costs_are_committed_from_started_work():
    runtime = OperationalProjectWorldRuntime(construction_episode())
    _move_to_construction(runtime)
    result = runtime.act(
        ProjectRole.SITE_MANAGER,
        action(ProjectActionType.START_ACTIVITY, "activity", "A100"),
    )
    assert result.applied
    assert result.financial_impact == 450_000
    assert runtime.committed_cost == 450_000


def test_foundry_is_deterministic_and_split_aware():
    from investigation_world.foundry.models import DistributionSplit
    from investigation_world.projectworld.foundry import (
        ProjectWorldGenerationSpec,
        generate_construction_distribution,
    )

    spec = ProjectWorldGenerationSpec(split=DistributionSplit.ADVERSARIAL, seed=242, count=2)
    first = generate_construction_distribution(spec)
    second = generate_construction_distribution(spec)
    assert first.manifest_hash == second.manifest_hash
    assert len(first.worlds) == 2
    assert all(item.split == DistributionSplit.ADVERSARIAL for item in first.worlds)
    assert all(item.difficulty.adversarial_pressure > 0 for item in first.worlds)


def test_source_adapters_normalize_real_world_schemas():
    from investigation_world.projectworld.adapters import (
        normalize_ifc_element,
        normalize_noaa_hourly,
        normalize_osha_incident,
        normalize_usaspending_award,
    )

    assert normalize_ifc_element(
        {"GlobalId": "g1", "IfcClass": "IfcWall", "Name": "Core wall"},
        source_id="gni-bim-2026",
        model_id="M1",
    )[0].canonical_id == "M1:g1"
    assert normalize_osha_incident({"event_id": "S1", "event": "Fall"})[0].value == "Fall"
    assert normalize_usaspending_award(
        {"award_id": "C1", "award_amount": "1000", "recipient_name": "Vendor"}
    )[0].value == 1000.0
    assert normalize_noaa_hourly(
        {"DATE": "2026-08-01T12:00:00+00:00", "STATION": "X", "temperature": "31"},
        site_id="SITE-1",
    )[0].field_name == "temperature"
