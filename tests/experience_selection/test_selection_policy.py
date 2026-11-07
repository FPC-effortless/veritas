"""Constructed public TRAIN execution tests, not learning-value evidence."""

from dataclasses import replace

import pytest

from investigation_world.experience.counterfactual import execute_counterfactual_experience
from investigation_world.experience_foundry.admission import PublicTrainingRecorder
from investigation_world.experience_selection import SelectionPolicy, select_experiences
from investigation_world.foundry.models import DistributionSplit
from investigation_world.operational import EpisodeSubmission
from investigation_world.trajectory import VisibilityClass


def recorded(
    root,
    formula=None,
    repeats=1,
    conclusion="Constructed protocol",
    evidence_repeat=False,
    claimed_state=None,
):
    recorder = PublicTrainingRecorder(root)
    records = recorder.runtime.public_payload()["records"]
    audit = next(r for r in records if r["record_type"] == "formula_audit")
    correct = f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})"
    recorder.act("repair_formula", cell=audit["object_id"], formula=formula or correct)
    for _ in range(repeats):
        recorder.act("recalculate_model")
    ids = [r["record_id"] for r in records if r["record_type"] in {"formula_audit", "model_check"}]
    if evidence_repeat:
        ids.append(ids[0])
    source = recorder.submit(
        EpisodeSubmission(
            conclusion=conclusion,
            evidence_ids=ids,
            claimed_state=claimed_state or {},
        )
    )
    return source, {"cell": audit["object_id"], "formula": correct}


@pytest.fixture(scope="module")
def pool(tmp_path_factory):
    root = tmp_path_factory.mktemp("selection")
    failures = []
    for index in range(2):
        source, replacement = recorded(root / f"failure{index}", formula=f"={index}")
        receipt = execute_counterfactual_experience(
            source,
            branch_step=0,
            replacement=replacement,
            artifact_root=root / f"branches{index}",
        )
        failures.append((receipt, source))
    success, _ = recorded(root / "success")
    duplicate, _ = recorded(root / "duplicate", conclusion="Different prose, same behavior")
    longer, _ = recorded(root / "longer", repeats=2)
    return success, duplicate, longer, tuple(failures)


def test_real_pool_selects_compact_success_and_counts_every_rejection(pool):
    success, duplicate, longer, gaps = pool
    candidates = (success, duplicate, longer, gaps[0][1])
    result = select_experiences(candidates, gap_sources=gaps)
    assert result.selected_count == 1
    assert result.rejected_count == 3
    assert result.rejection_counts == {
        "duplicate_protocol": 1,
        "stratum_quota_saturated": 1,
        "failed_not_training_candidate": 1,
    }
    assert result.gaps[0].candidate.gap.frequency == 2
    assert result.training_usefulness == "UNKNOWN"
    assert result.training_qualified is False
    assert result.resources.pool_entries == 4
    assert result.resources.recorded_candidate_cost > 0
    assert result.resources.generation_compute_cost is None
    assert result.resources.selection_wall_seconds is None
    assert result.resources.accounting_complete is False


def test_no_gap_means_zero_even_for_control(pool):
    for mode in ("representative", "random_control"):
        result = select_experiences((pool[0],), policy=SelectionPolicy(mode=mode))
        assert result.selected_count == 0
        assert result.rejection_counts == {"no_useful_gap": 1}


def test_order_independence_and_policy_identity(pool):
    candidates = pool[:3]
    policy = SelectionPolicy(max_per_stratum=2, max_items=1, seed=17)
    first = select_experiences(candidates, gap_sources=pool[3], policy=policy)
    reordered = select_experiences(
        reversed(candidates), gap_sources=reversed(pool[3]), policy=policy
    )
    assert first == reordered
    changed = select_experiences(
        candidates,
        gap_sources=pool[3],
        policy=SelectionPolicy(max_per_stratum=2, max_items=1, seed=18),
    )
    assert first.pool_id == changed.pool_id
    assert first.policy.record_id != changed.policy.record_id
    assert first.record_id != changed.record_id


def test_heldout_and_private_never_reverified(pool, monkeypatch):
    import investigation_world.experience_selection.selection as module

    source = pool[0]
    heldout = replace(
        source, companion=source.companion.model_copy(update={"split": DistributionSplit.IID_TEST})
    )
    private = replace(
        source,
        experience=source.experience.model_copy(update={"visibility": VisibilityClass.SEALED}),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("boundary input reached evaluator")

    monkeypatch.setattr(module, "verify_recorded", forbidden)
    canonical_heldout = replace(
        source,
        experience=source.experience.model_copy(
            update={
                "trajectory": source.experience.trajectory.model_copy(
                    update={
                        "task": source.experience.trajectory.task.model_copy(
                            update={"split": DistributionSplit.IID_TEST}
                        ),
                    }
                ),
            }
        ),
    )
    result = select_experiences((heldout, private, canonical_heldout))
    assert result.selected_count == 0
    assert result.rejection_counts == {"non_train": 2, "nonpublic_source": 1}
    assert result.resources.recorded_candidate_cost is None
    assert result.resources.candidate_validation_attempts == 0


def test_control_uses_identical_eligibility_and_resource_denominator(pool):
    candidates = (*pool[:3], pool[3][0][1])
    targeted = select_experiences(candidates, gap_sources=pool[3])
    control = select_experiences(
        candidates, gap_sources=pool[3], policy=SelectionPolicy(mode="random_control", seed=11)
    )
    assert targeted.pool_id == control.pool_id
    assert targeted.gap_input_digest == control.gap_input_digest
    assert targeted.eligibility_digest == control.eligibility_digest
    assert targeted.selected_count == control.selected_count == 1
    assert targeted.resources == control.resources
    assert targeted.policy.record_id != control.policy.record_id


def test_explicit_hard_negatives_are_private_analysis_only(pool):
    result = select_experiences(
        tuple(s for _, s in pool[3]),
        gap_sources=pool[3],
        policy=SelectionPolicy(max_items=2, max_hard_negatives=1),
    )
    selected = [d for d in result.decisions if d.reason == "selected"]
    assert len(selected) == 1
    assert selected[0].role == "private_hard_negative"
    assert selected[0].target_shortfall > 0
    assert result.training_qualified is False
    assert result.public_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}
    assert result.buyer_safe_payload() == result.public_payload()
    assert pool[3][0][1].experience.experience_id not in str(result.public_payload())


def test_trivial_and_zero_budget_are_explicit(pool):
    trivial = select_experiences(
        (pool[0],), gap_sources=pool[3], policy=SelectionPolicy(min_actions=3)
    )
    assert trivial.rejection_counts == {"trivial_action_count": 1}
    zero = select_experiences((pool[0],), gap_sources=pool[3], policy=SelectionPolicy(max_items=0))
    assert zero.rejection_counts == {"selection_budget": 1}
    assert zero.resources.recorded_candidate_cost > 0


def test_repeated_input_slots_are_counted_without_double_charging_same_record(pool):
    source = pool[0]
    result = select_experiences((source, source), gap_sources=pool[3])
    assert result.resources.pool_entries == 2
    assert result.resources.unique_input_snapshots == 1
    assert result.resources.candidate_validation_attempts == 2
    assert result.resources.recorded_candidate_cost == source.companion.total_cost
    assert result.selected_count == 1
    assert result.rejection_counts == {"duplicate_protocol": 1}
    assert len({d.slot_id for d in result.decisions}) == 2


def test_frozen_task_and_source_exclusions_apply_to_candidates_and_gap_evidence(pool):
    source = pool[0]
    for policy in (
        SelectionPolicy(heldout_task_ids=(source.companion.task_id,)),
        SelectionPolicy(heldout_source_digests=(source.companion.metadata["source_digest"],)),
    ):
        result = select_experiences((source,), policy=policy)
        assert result.rejection_counts == {"heldout_overlap": 1}
        assert result.resources.candidate_validation_attempts == 0
        with pytest.raises(ValueError, match="boundary"):
            select_experiences((source,), gap_sources=pool[3], policy=policy)


def test_gap_receipts_and_actual_source_are_bound_not_just_declared_pass(pool):
    receipt, source = pool[3][0]
    forged = receipt.model_copy(update={"source_digest": "f" * 64})
    with pytest.raises(ValueError, match="fresh provider"):
        select_experiences((pool[0],), gap_sources=((forged, source), pool[3][1]))
    with pytest.raises(ValueError, match="fresh provider"):
        select_experiences((pool[0],), gap_sources=((receipt, pool[3][1][1]), pool[3][1]))
    heldout = replace(
        source, companion=source.companion.model_copy(update={"split": DistributionSplit.OOD})
    )
    with pytest.raises(ValueError, match="boundary"):
        select_experiences((pool[0],), gap_sources=((receipt, heldout),))


def test_single_or_repeated_protocol_cannot_invent_a_gap(pool):
    for evidence in ((pool[3][0],), (pool[3][0], pool[3][0])):
        result = select_experiences((pool[0],), gap_sources=evidence)
        assert not result.gaps
        assert result.selected_count == 0
        assert result.rejection_counts == {"no_useful_gap": 1}
        assert result.resources.recorded_gap_execution_cost > 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime_version", "forged"),
        ("total_cost", 0),
        ("total_reward", -1),
        ("task_seed", 1),
        ("taskset_version", "forged"),
    ],
)
def test_tampered_candidate_is_rejected_and_cost_is_unknown(pool, field, value):
    source = pool[0]
    forged = replace(source, companion=source.companion.model_copy(update={field: value}))
    result = select_experiences((forged, source), gap_sources=pool[3])
    assert result.rejection_counts == {"invalid_source": 1}
    assert result.selected_count == 1
    assert result.resources.recorded_candidate_cost is None
    assert result.resources.known_candidate_recorded_cost == source.companion.total_cost


def test_unknown_capability_target_yields_zero_not_name_based_match(pool):
    result = select_experiences(
        (pool[0],),
        gap_sources=pool[3],
        policy=SelectionPolicy(target_capability_digests=("a" * 64,)),
    )
    assert result.rejection_counts == {"no_useful_gap": 1}
    assert result.gaps  # Evidence remains inspectable even when outside policy target.


def test_report_validation_requires_expected_policy_and_actual_pool(pool):
    from investigation_world.experience_selection import validate_selection

    policy = SelectionPolicy()
    result = select_experiences(pool[:3], gap_sources=pool[3], policy=policy)
    assert validate_selection(result, pool[:3], gap_sources=pool[3], policy=policy) == result
    with pytest.raises(ValueError, match="actual inputs"):
        validate_selection(result, (pool[0],), gap_sources=pool[3], policy=policy)
    with pytest.raises(ValueError, match="expected policy"):
        validate_selection(result, pool[:3], gap_sources=pool[3], policy=SelectionPolicy(seed=1))
    payload = result.model_dump(mode="python")
    payload["selected_count"] = 100
    with pytest.raises(ValueError, match="identity"):
        type(result).model_validate(payload)
    forged = result.model_copy(deep=True)
    forged.rejection_counts["secret injected"] = 2
    with pytest.raises(ValueError, match="identity"):
        forged.public_payload()
    widened = result.model_copy(update={"visibility": "public"})
    with pytest.raises(ValueError):
        widened.public_payload()


def test_deleted_artifacts_invalidate_old_report(tmp_path):
    import shutil

    from investigation_world.experience_selection import validate_selection

    source, _ = recorded(tmp_path / "retained")
    policy = SelectionPolicy()
    result = select_experiences((source,), policy=policy)
    shutil.rmtree(tmp_path / "retained")
    with pytest.raises(ValueError, match="actual inputs"):
        validate_selection(result, (source,), policy=policy)
    fresh = select_experiences((source,), policy=policy)
    assert fresh.rejection_counts == {"invalid_source": 1}
    assert fresh.resources.recorded_candidate_cost is None


def test_empty_input_and_bounds(pool):
    empty = select_experiences(())
    assert empty.selected_count == empty.rejected_count == 0
    assert (
        empty.resources.recorded_candidate_cost == 0
    )  # Known absence of inputs, not unknown cost.
    assert empty.resources.generation_compute_cost is None
    consumed = []

    def unbounded():
        while True:
            consumed.append(1)
            yield pool[0]

    with pytest.raises(ValueError, match="bound"):
        select_experiences(unbounded())
    assert len(consumed) == 257
    with pytest.raises(ValueError, match="bound"):
        select_experiences((), gap_sources=(pool[3][0] for _ in range(65)))


@pytest.mark.parametrize(
    "changes",
    [
        {"seed": True},
        {"seed": -1},
        {"seed": 2**32},
        {"max_items": 257},
        {"max_per_stratum": 0},
        {"min_actions": 0},
        {"mode": "greedy_test_outcomes"},
        {"max_items": 1, "max_hard_negatives": 2},
        {"visibility": "public"},
        {"version": "unimplemented"},
        {"target_capability_digests": ("invalid",)},
    ],
)
def test_policy_rejects_unsupported_or_unbounded_semantics(changes):
    with pytest.raises(ValueError):
        SelectionPolicy(**changes)


def test_scheduler_diversity_and_seeded_control_on_constructed_strata():
    from investigation_world.experience_selection.selection import Decision, _Candidate, _choose
    from investigation_world.trajectory import canonical_hash

    def rows(seed):
        return [
            _Candidate(
                Decision(
                    slot_id=f"{group}:{index}",
                    input_digest=canonical_hash((group, index)),
                    experience_id="CONSTRUCTED",
                    reason="selected",
                    role="verified_success_candidate",
                    stratum_digest=canonical_hash(group),
                    recorded_cost=float(index + 1),
                ),
                canonical_hash((seed, group, index)),
            )
            for group in ("a", "b", "c")
            for index in range(4)
        ]

    policy = SelectionPolicy(max_items=3, max_per_stratum=3)
    chosen = _choose(rows(4), policy)
    assert {key for key, reason in chosen.items() if reason == "selected"} == {"a:0", "b:0", "c:0"}
    control = SelectionPolicy(mode="random_control", max_items=3, max_per_stratum=3)
    assert _choose(rows(4), control) == _choose(list(reversed(rows(4))), control)
    selections = {
        tuple(sorted(k for k, v in _choose(rows(seed), control).items() if v == "selected"))
        for seed in range(8)
    }
    assert len(selections) > 1


def test_admission_integrity_failure_cannot_fall_back_to_hard_negative(pool, monkeypatch):
    import investigation_world.experience_selection.selection as module

    def failed_admission(*args, **kwargs):
        raise ValueError("retained source changed after first verification")

    monkeypatch.setattr(module, "admit_experience", failed_admission)
    result = select_experiences(
        (pool[0],), gap_sources=pool[3], policy=SelectionPolicy(max_hard_negatives=1)
    )
    assert result.selected_count == 0
    assert result.rejection_counts == {"invalid_source": 1}


def test_cached_reverification_alias_is_one_recorded_execution(pool):
    from investigation_world.experience import machine_experience_from_trajectory
    from investigation_world.experience_foundry.admission import authorized_registry
    from investigation_world.trajectory.reverify import (
        current_operational_verifier_binding,
        reverify_trajectory,
    )

    source = pool[0]
    outcome = reverify_trajectory(
        source.experience.trajectory,
        verifier=current_operational_verifier_binding().identity,
        registry=authorized_registry(),
    )
    trajectory = source.experience.trajectory.model_copy(
        update={"reverifications": (outcome.record,)}
    )
    alias = replace(source, experience=machine_experience_from_trajectory(trajectory))
    assert alias.experience.experience_id == source.experience.experience_id
    assert alias.companion.trace_id == source.companion.trace_id
    result = select_experiences((source, alias), gap_sources=pool[3])
    assert result.rejection_counts == {"duplicate_protocol": 1}
    assert result.resources.recorded_candidate_cost == source.companion.total_cost
    assert result.resources.unique_input_snapshots == 2
    assert result.resources.unique_validated_recordings == 1


@pytest.mark.parametrize(
    "changes", [{"evidence_repeat": True}, {"claimed_state": {"irrelevant": 7}}]
)
def test_submission_padding_cannot_buy_another_protocol(tmp_path, pool, changes):
    source, _ = recorded(tmp_path / "first")
    padded, _ = recorded(tmp_path / "padded", **changes)
    result = select_experiences(
        (source, padded),
        gap_sources=pool[3],
        policy=SelectionPolicy(max_items=2, max_per_stratum=2),
    )
    assert result.selected_count == 1
    assert result.rejection_counts == {"duplicate_protocol": 1}


def test_private_digests_and_counts_are_never_publicly_projected(pool):
    result = select_experiences(pool[:3], gap_sources=pool[3])
    for projection in (result.public_payload(), result.buyer_safe_payload()):
        assert set(projection) == {"status", "reason"}
        assert result.pool_id not in str(projection)
        assert result.record_id not in str(projection)
        assert "selected_count" not in projection


def test_gap_prose_aliases_cannot_manufacture_two_behavioral_protocols(tmp_path, pool):
    alias, replacement = recorded(tmp_path / "alias", formula="=0", conclusion="Only prose differs")
    receipt = execute_counterfactual_experience(
        alias, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
    )
    result = select_experiences((pool[0],), gap_sources=(pool[3][0], (receipt, alias)))
    assert result.selected_count == 0
    assert result.rejection_counts == {"no_useful_gap": 1}
    assert result.resources.recorded_gap_execution_cost > 0
