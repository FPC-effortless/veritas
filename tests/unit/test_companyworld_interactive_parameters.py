from __future__ import annotations

from investigation_world.companyworld import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    InteractiveCompanyWorldRuntime,
    OperationalAction,
    OperationalActionType,
    OperationalFactTarget,
    compile_interactive_episode,
    solve_interactive_public,
)


def _authority_base(episode_id: str) -> CompanyWorldEpisode:
    policy = CompanyWorldRecord(
        record_id="REC-AUTH-POLICY",
        system=CompanySystem.AUTH_SERVICE,
        record_type="policy_rule",
        object_type="AUTHORITY",
        object_id="POS-1",
        fields={"approval_limit_usd": 1000},
        source_file="fixture/authority",
    )
    task = CompanyWorldTask(
        task_id="TASK-AUTH",
        world_id="CW-TEST",
        task_type="INVESTIGATE_AUTHORITY_BREACH",
        objective="Determine the correct approval authority for POS-1.",
        target_object_type="AUTHORITY",
        target_object_id="POS-1",
        permitted_systems=[CompanySystem.AUTH_SERVICE],
    )
    oracle = CompanyWorldOracle(
        task_id=task.task_id,
        answer_class="authority_misconfiguration",
        expected_resolution="Restore the policy limit.",
        facts=[
            OperationalFactTarget(
                object_type="AUTHORITY",
                object_id="POS-1",
                field_name="approval_limit_usd",
                expected_value=1000,
                supporting_record_ids=[policy.record_id],
            )
        ],
    )
    return CompanyWorldEpisode(
        episode_id=episode_id,
        world_id="CW-TEST",
        task=task,
        records=[policy],
        oracle=oracle,
    )


def _admin_episode():
    for index in range(100):
        episode = compile_interactive_episode(_authority_base(f"CWX-AUTH-{index}"))
        if episode.task.actor_role == "COMPLIANCE_ADMIN":
            return episode
    raise AssertionError("failed to generate deterministic admin fixture")


def test_wrong_parameter_is_applied_without_oracle_feedback_but_scores_below_success():
    episode = _admin_episode()
    runtime = InteractiveCompanyWorldRuntime(episode)
    execution = runtime.act(
        OperationalAction(
            action_type=OperationalActionType.RESTORE_AUTHORITY_LIMIT,
            target_object_type="AUTHORITY",
            target_object_id="POS-1",
            parameters={"approval_limit_usd": 999999},
        )
    )
    assert execution.authorized
    assert execution.applied
    assert execution.reason == ""
    result, _ = solve_interactive_public(episode.public_payload())
    score = runtime.submit(result)
    assert score.investigation_fact_score == 1.0
    assert score.outcome_score < 1.0
    assert score.overall_reward < 1.0
