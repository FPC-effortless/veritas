import pytest

from investigation_world.benchmark.policies import (
    AlwaysAbstainPolicy,
    CiteEverythingPolicy,
    ConclusionOnlyPolicy,
    EmptyPolicy,
    ProjectionTrustPolicy,
    PublicEvidenceReferencePolicy,
    StuffingPolicy,
)
from investigation_world.companyworld import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    OperationalFactTarget,
    verify_companyworld,
)


def _episode(task_type: str) -> CompanyWorldEpisode:
    if task_type == "INVESTIGATE_MISSING_SHIPMENT":
        target_type, target_id, field, expected = "SHIPMENT", "SHP-1", "delivered_quantity", 9
        direct = CompanyWorldRecord(
            record_id="DIRECT",
            system=CompanySystem.WMS,
            record_type="carrier_manifest",
            object_type=target_type,
            object_id=target_id,
            fields={field: expected},
            source_file="carrier",
        )
        projection = CompanyWorldRecord(
            record_id="PROJECTION",
            system=CompanySystem.ERP,
            record_type="system_projection",
            object_type=target_type,
            object_id=target_id,
            fields={field: 10},
            source_file="erp",
        )
    elif task_type == "INVESTIGATE_DUPLICATE_INVOICE":
        target_type, target_id, field, expected = "SUPPLIER_INVOICE", "SINV-1", "duplicate_status", "DUPLICATE"
        direct = CompanyWorldRecord(
            record_id="DIRECT",
            system=CompanySystem.AP_WORKFLOW,
            record_type="supplier_submission",
            object_type=target_type,
            object_id="EXT-SINV-1",
            fields={
                "submission_kind": "resubmission",
                "submitted_reference": target_id,
            },
            source_file="supplier",
            related_object_ids=[target_id],
        )
        projection = CompanyWorldRecord(
            record_id="PROJECTION",
            system=CompanySystem.AP_WORKFLOW,
            record_type="system_projection",
            object_type=target_type,
            object_id=target_id,
            fields={field: "UNIQUE"},
            source_file="ap",
        )
    else:
        target_type, target_id, field, expected = "AUTHORITY", "POS-1", "approval_limit_usd", 1000
        direct = CompanyWorldRecord(
            record_id="DIRECT",
            system=CompanySystem.AUTH_SERVICE,
            record_type="policy_rule",
            object_type=target_type,
            object_id=target_id,
            fields={field: expected},
            source_file="policy",
        )
        projection = CompanyWorldRecord(
            record_id="PROJECTION",
            system=CompanySystem.AUTH_SERVICE,
            record_type="system_projection",
            object_type=target_type,
            object_id=target_id,
            fields={field: 3000},
            source_file="auth",
        )

    task = CompanyWorldTask(
        task_id=f"TASK-{target_id}",
        world_id="companyworld:test:1",
        task_type=task_type,
        objective="Investigate the discrepancy.",
        target_object_type=target_type,
        target_object_id=target_id,
        permitted_systems=list({direct.system, projection.system}),
    )
    oracle = CompanyWorldOracle(
        task_id=task.task_id,
        answer_class="test",
        expected_resolution="Resolve the discrepancy.",
        facts=[
            OperationalFactTarget(
                object_type=target_type,
                object_id=target_id,
                field_name=field,
                expected_value=expected,
                supporting_record_ids=[direct.record_id, projection.record_id],
            )
        ],
    )
    return CompanyWorldEpisode(
        episode_id=f"CW-{task.task_id}",
        world_id=task.world_id,
        task=task,
        records=[direct, projection],
        oracle=oracle,
    )


@pytest.mark.parametrize(
    "task_type",
    [
        "INVESTIGATE_MISSING_SHIPMENT",
        "INVESTIGATE_DUPLICATE_INVOICE",
        "INVESTIGATE_AUTHORITY_BREACH",
    ],
)
def test_public_reference_policy_solves_each_family(task_type: str):
    episode = _episode(task_type)
    result = PublicEvidenceReferencePolicy()(episode.public_payload())
    score = verify_companyworld(result, episode)
    assert score.fact_score == 1.0
    assert score.evidence_support == 1.0
    assert score.overall_reward == 1.0


@pytest.mark.parametrize(
    "policy",
    [EmptyPolicy(), ConclusionOnlyPolicy(), AlwaysAbstainPolicy(), CiteEverythingPolicy()],
)
def test_non_solving_shortcuts_receive_zero(policy):
    episode = _episode("INVESTIGATE_MISSING_SHIPMENT")
    score = verify_companyworld(policy(episode.public_payload()), episode)
    assert score.overall_reward == 0.0


def test_projection_trust_is_wrong_and_receives_zero():
    episode = _episode("INVESTIGATE_MISSING_SHIPMENT")
    score = verify_companyworld(ProjectionTrustPolicy()(episode.public_payload()), episode)
    assert score.fact_score == 0.0
    assert score.overall_reward == 0.0


def test_field_stuffing_is_bounded_below_reference_solver():
    episode = _episode("INVESTIGATE_MISSING_SHIPMENT")
    stuffed = verify_companyworld(StuffingPolicy()(episode.public_payload()), episode)
    reference = verify_companyworld(
        PublicEvidenceReferencePolicy()(episode.public_payload()), episode
    )
    assert stuffed.overall_reward <= 0.25
    assert stuffed.overall_reward < reference.overall_reward
