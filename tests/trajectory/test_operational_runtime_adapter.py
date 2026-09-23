"""G-03: OperationalRuntime -> TrajectoryV2 adapter.

Every test here asserts a property the work contract for this gap requires:

* the emitted trajectory is a *record* of a runtime that already ran, never a re-execution;
* its events decode back through the reverification engine's own decoders;
* private/verifier-only truth cannot reach a public or buyer-safe serialization;
* nothing is invented where the source does not know it.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys

import pytest

from investigation_world.experience import ExperienceMaturity, machine_experience_from_trajectory
from investigation_world.foundry.models import stable_hash
from investigation_world.operational.catalog import (
    build_enterprise_operations_world,
    build_gis_operations_world,
    build_operational_suite,
)
from investigation_world.operational.models import (
    EpisodeSubmission,
    OperationalEpisode,
    VerificationBreakdown,
    WorldDomain,
)
from investigation_world.operational.native_runtime import NativeOperationalRuntime
from investigation_world.operational.realism import apply_domain_realism
from investigation_world.operational.runtime import (
    OperationalRuntime,
    verify_operational_episode,
)
from investigation_world.portable_contract import compile_operational_episode
from investigation_world.portable_contract.compiler import (
    SOURCE_VERIFIER_BLOB,
    VERIFIER_ENTRYPOINT,
    VERIFIER_SEMANTICS_ID,
)
from investigation_world.trajectory import (
    OPERATIONAL_RUNTIME_ADAPTER_ID,
    OPERATIONAL_RUNTIME_ADAPTER_VERSION,
    ArtifactIdentity,
    ModelIdentity,
    OperationalRuntimeAdapterContext,
    StateDigestScope,
    TrajectoryEvent,
    TrajectoryV2,
    VerifierIdentity,
    trajectory_v2_from_operational_runtime,
)
from investigation_world.trajectory.reverify import (
    AuthorizedVerifierRegistry,
    OperationalReplayEvidence,
    ReverificationStatus,
    attach_operational_replay_evidence,
    current_operational_verifier_binding,
    reverify_trajectory,
)
from investigation_world.trajectory.reverify import engine as reverification_engine
from investigation_world.trajectory.models import canonical_hash

_PRIVATE_MARKERS = ("segregation_of_duties_violation", "PRIVATE-ORACLE-SECRET")

# The seven components ``VerificationBreakdown`` carries; the adapter maps each into the
# trajectory's ``original_evaluation`` without re-scoring.
_REWARD_COMPONENTS = frozenset(
    {
        "outcome",
        "state",
        "constraints",
        "side_effects",
        "process",
        "efficiency",
        "evidence",
    }
)

# ``apply_domain_realism`` is the pass that populates ``required_action_order``; catalog builders
# alone leave it empty. Map each domain to the same family the production deepening pass uses.
_SCENARIO_FAMILIES = {
    WorldDomain.FINANCIAL_SPREADSHEET: "dcf_formula_repair",
    WorldDomain.ENTERPRISE_OPERATIONS: "discount_control",
    WorldDomain.DEVOPS_INCIDENT_RESPONSE: "service_availability",
    WorldDomain.INVESTIGATION_OSINT: "identity_resolution",
    WorldDomain.GIS_OPERATIONS: "projection_alignment",
}


def _apply_realism(episode: OperationalEpisode, index: int, family: str) -> OperationalEpisode:
    return apply_domain_realism(
        episode, rng=random.Random(9001), index=index, scenario_family=family
    )


def _deepen(episode: OperationalEpisode, index: int = 7) -> OperationalEpisode:
    """Apply the production realism pass for this episode's own domain."""
    return _apply_realism(episode, index=index, family=_SCENARIO_FAMILIES[episode.task.domain])


def _catalog_episode() -> OperationalEpisode:
    """A real catalog world, deepened with the production realism pass."""
    return _deepen(build_enterprise_operations_world(seed=42))


def _required_parameters(episode: OperationalEpisode, action_name: str, ordinal: int = 0) -> dict:
    effects = [
        effect for effect in episode.oracle.action_effects if effect.action_name == action_name
    ]
    return dict(effects[min(ordinal, len(effects) - 1)].required_parameters)


def _execute_required_actions(runtime: OperationalRuntime) -> None:
    """Walk the oracle's own required order, so a closed runtime actually solved its task."""
    episode = runtime.episode
    for action_name in episode.oracle.required_action_order:
        required_count = episode.oracle.required_action_counts.get(action_name, 1)
        for ordinal in range(required_count):
            runtime.act(action_name, **_required_parameters(episode, action_name, ordinal))


def _submission(episode: OperationalEpisode) -> EpisodeSubmission:
    return EpisodeSubmission(
        conclusion="completed with full evidence chain",
        evidence_ids=list(episode.oracle.required_evidence_ids),
        confidence=0.95,
    )


def _portable_contract_identity(episode: OperationalEpisode) -> ArtifactIdentity:
    return ArtifactIdentity(
        artifact_id=compile_operational_episode(episode).contract_id,
        contract="veritas.portable-operational-contract",
        version="1.0.0",
    )


def _solve(episode: OperationalEpisode) -> tuple[OperationalRuntime, EpisodeSubmission]:
    """Execute and submit an episode, returning a closed runtime and its submission."""
    runtime = OperationalRuntime(episode)
    _execute_required_actions(runtime)
    submission = _submission(episode)
    runtime.submit(submission)
    return runtime, submission


def _closed_runtime() -> tuple[
    OperationalRuntime, EpisodeSubmission, VerificationBreakdown
]:
    runtime, submission = _solve(_catalog_episode())
    return runtime, submission, _fresh_breakdown(runtime)


def _fresh_breakdown(runtime: OperationalRuntime) -> VerificationBreakdown:
    """The caller's copy of the breakdown ``submit()`` handed back.

    ``OperationalRuntime.submit()`` returns the breakdown without retaining it, which is exactly
    the gap this adapter is contracted for. Tests cannot ask the runtime for it again, so they
    recompute it the same way the caller would have received it: once, from the recorded events.
    """
    episode = runtime.episode
    return verify_operational_episode(
        oracle=episode.oracle,
        state=runtime.state_snapshot(),
        events=list(runtime.events),
        submission=_submission(episode),
        tool_calls=runtime.budget.calls,
        cost_spent=runtime.budget.spent,
    )


def _replay_states(runtime: OperationalRuntime) -> tuple[dict, dict]:
    """The initial and replayed state the evidence and the trajectory must agree on.

    ``OperationalRuntime.act()`` applies an effect's ``set_state`` to the runtime state and
    records the same mapping on the ``ActionEvent``, so folding the recorded events over the
    oracle's initial state is the same fold the runtime itself performed. Both the evidence
    digests (``stable_hash``) and the trajectory's caller-supplied digests are derived from this
    pair, which is what makes them equal despite the two functions differing by design.
    """
    initial_state = dict(runtime.episode.oracle.initial_state)
    replayed = dict(initial_state)
    for event in runtime.events:
        replayed.update(dict(event.state_changes))
    return initial_state, replayed


def _context(
    runtime: OperationalRuntime,
    submission: EpisodeSubmission,
    breakdown: VerificationBreakdown,
    **overrides,
) -> OperationalRuntimeAdapterContext:
    """Build the adapter context, defaulting the state digests to the replay digests.

    The evidence model hashes state with ``foundry.models.stable_hash`` while the adapter's own
    computed digests use ``canonical_hash``; the two are different functions by design. Passing
    the replay digests in explicitly is the documented way a caller reconciles them, so the
    reverification round trip exercises that path rather than weakening either function. Explicit
    ``overrides`` win, because ``kwargs.update`` applies them after the defaults.
    """
    initial_state, final_state = _replay_states(runtime)
    kwargs: dict = {
        "breakdown": breakdown,
        "submission": submission,
        "portable_operational_contract": _portable_contract_identity(runtime.episode),
        "world_id": runtime.episode.world_id,
        "world_version": "1",
        "initial_state_digest": stable_hash(initial_state),
        "final_state_digest": stable_hash(final_state),
    }
    kwargs.update(overrides)
    return OperationalRuntimeAdapterContext(**kwargs)


def _trajectory(**overrides) -> TrajectoryV2:
    runtime, submission, breakdown = _closed_runtime()
    return trajectory_v2_from_operational_runtime(
        runtime,
        context=_context(runtime, submission, breakdown=breakdown, **overrides),
    )


def _act_events_only(runtime: OperationalRuntime) -> tuple[TrajectoryEvent, ...]:
    """The public projection the adapter must emit for each recorded ActionEvent."""
    return tuple(
        TrajectoryEvent(
            step=event.sequence - 1,
            event_type="act",
            payload={
                "method": "act",
                "action_name": event.action_name,
                "args": [event.action_name],
                "kwargs": dict(event.parameters),
                "success": bool(event.effect_applied and not event.blocked),
            },
            cost=float(event.cost),
        )
        for event in runtime.events
    )


def _replay_evidence(
    runtime: OperationalRuntime,
    submission: EpisodeSubmission,
    trajectory: TrajectoryV2,
) -> OperationalReplayEvidence:
    """Build reverification evidence bound to an adapted trajectory.

    ``_validate_evidence_against_trajectory`` digests the *whole* emitted event list, including
    the ``submit`` event, so the evidence digest is taken from the trajectory rather than
    reconstructed from the act events alone. ``_matching_private_reference`` then requires the
    trajectory's ``evidence_references`` to name this evidence, which the adapter's context
    cannot do: the reference is derived from the evidence's own digest. The caller attaches it.
    """
    episode = runtime.episode
    initial_state, final_state = _replay_states(runtime)
    return OperationalReplayEvidence(
        portable_contract=compile_operational_episode(episode),
        trajectory_events_digest=canonical_hash(trajectory.events),
        initial_state=initial_state,
        initial_state_digest=stable_hash(initial_state),
        final_state=final_state,
        final_state_digest=stable_hash(final_state),
        action_events=tuple(runtime.events),
        submission=submission,
        tool_calls=runtime.budget.calls,
        cost_spent=runtime.budget.spent,
        input_trajectory_id=trajectory.trajectory_id,
    )


def _attach_evidence(
    trajectory: TrajectoryV2,
    runtime: OperationalRuntime,
    submission: EpisodeSubmission,
) -> TrajectoryV2:
    """Attach replay evidence and the private reference that names it.

    The reference is appended after adaptation and after evidence construction, so the trajectory
    identity it pins is already final; ``attach_operational_replay_evidence`` then asserts that
    attaching private evidence does not change it.
    """
    evidence = _replay_evidence(runtime, submission, trajectory)
    referenced = trajectory.model_copy(
        update={"evidence_references": (evidence.reference(),)}
    )
    return attach_operational_replay_evidence(referenced, evidence.for_trajectory(referenced))


def _reverifiable(**overrides) -> TrajectoryV2:
    runtime, submission, breakdown = _closed_runtime()
    trajectory = trajectory_v2_from_operational_runtime(
        runtime,
        context=_context(runtime, submission, breakdown=breakdown, **overrides),
    )
    return _attach_evidence(trajectory, runtime, submission)


def _registry() -> tuple[AuthorizedVerifierRegistry, VerifierIdentity]:
    binding = current_operational_verifier_binding()
    return AuthorizedVerifierRegistry((binding,)), binding.identity


# ---------------------------------------------------------------------------
# 1. Round trip: emitted events decode through the engine's own decoders and reverify.
# ---------------------------------------------------------------------------


def test_emitted_events_decode_and_reverify_on_a_real_catalog_episode() -> None:
    trajectory = _reverifiable()
    runtime, submission, breakdown = _closed_runtime()

    assert [event.event_type for event in trajectory.events] == ["act"] * len(runtime.events) + [
        "submit"
    ]
    for emitted, expected in zip(trajectory.events, _act_events_only(runtime), strict=True):
        assert reverification_engine._decode_operational_act(emitted) == (
            reverification_engine._decode_operational_act(expected)
        )

    submit_events = [
        event
        for event in trajectory.events
        if event.payload.get("method") == "submit" and event.payload.get("success") is True
    ]
    assert len(submit_events) == 1
    assert reverification_engine._decode_submission(submit_events[0]) == submission

    registry, verifier = _registry()
    outcome = reverify_trajectory(trajectory, verifier=verifier, registry=registry)

    assert outcome.status is ReverificationStatus.REVERIFIED
    assert outcome.record is not None
    assert outcome.record.reward == pytest.approx(trajectory.original_evaluation.reward)
    assert outcome.record.component_scores == trajectory.original_evaluation.component_scores


# ---------------------------------------------------------------------------
# 2. Determinism of the canonical trajectory id.
# ---------------------------------------------------------------------------


def test_trajectory_id_is_deterministic_across_adaptations() -> None:
    first = _trajectory()
    second = _trajectory()

    assert first == second
    assert first.trajectory_id == second.trajectory_id
    assert first.trajectory_id.startswith("TRAJ-V2-")


# ---------------------------------------------------------------------------
# 3. Identity sensitivity.
# ---------------------------------------------------------------------------


def test_model_and_contract_identity_changes_change_trajectory_identity() -> None:
    base = _trajectory()
    model_changed = _trajectory(
        model=ModelIdentity(provider="hf", model_id="model-b", snapshot="sha-abc")
    )
    contract_changed = _trajectory(
        portable_operational_contract=ArtifactIdentity(
            artifact_id="POC-OTHER",
            contract="veritas.portable-operational-contract",
            version="1.0.0",
        )
    )

    identities = {
        base.trajectory_id,
        model_changed.trajectory_id,
        contract_changed.trajectory_id,
    }
    assert len(identities) == 3


def test_a_partial_action_trace_changes_trajectory_identity() -> None:
    episode = _catalog_episode()
    runtime = OperationalRuntime(episode)
    first = episode.oracle.required_action_order[0]
    runtime.act(first, **_required_parameters(episode, first))
    runtime.submit(_submission(episode))
    partial = trajectory_v2_from_operational_runtime(
        runtime,
        context=_context(runtime, _submission(episode), breakdown=_fresh_breakdown(runtime)),
    )

    assert partial.trajectory_id != _trajectory().trajectory_id


# ---------------------------------------------------------------------------
# 4. Never re-execute; never submit on the caller's runtime.
# ---------------------------------------------------------------------------


def test_unsubmitted_runtime_is_rejected_without_calling_submit() -> None:
    episode = _catalog_episode()
    runtime = OperationalRuntime(episode)
    first = episode.oracle.required_action_order[0]
    runtime.act(first, **_required_parameters(episode, first))

    with pytest.raises(ValueError, match="must be submitted"):
        trajectory_v2_from_operational_runtime(
            runtime,
            context=OperationalRuntimeAdapterContext(breakdown=VerificationBreakdown()),
        )
    assert runtime.closed is False
    assert len(runtime.events) == 1


def test_missing_breakdown_is_rejected_without_re_scoring() -> None:
    runtime, submission, breakdown = _closed_runtime()

    with pytest.raises(ValueError, match="VerificationBreakdown"):
        trajectory_v2_from_operational_runtime(
            runtime,
            context=OperationalRuntimeAdapterContext(submission=submission),
        )


# ---------------------------------------------------------------------------
# 5. Verifier identity.
# ---------------------------------------------------------------------------


def test_default_verifier_is_the_authorized_operational_binding() -> None:
    trajectory = _trajectory()
    binding = current_operational_verifier_binding()

    assert trajectory.verifier.verifier_id == VERIFIER_ENTRYPOINT
    assert trajectory.verifier.version == VERIFIER_SEMANTICS_ID
    assert trajectory.verifier == binding.identity
    assert trajectory.original_evaluation.verifier == trajectory.verifier


def test_supplied_verifier_identity_is_honored_and_affects_identity() -> None:
    named = VerifierIdentity(verifier_id="operational-legacy", version="legacy-v1")
    trajectory = _trajectory(verifier=named)

    assert trajectory.verifier == named
    assert trajectory.original_evaluation.verifier == named
    assert trajectory.trajectory_id != _trajectory().trajectory_id


def test_current_binding_pins_the_committed_verifier_source() -> None:
    binding = current_operational_verifier_binding()

    assert binding.entrypoint == VERIFIER_ENTRYPOINT
    assert binding.semantics_id == VERIFIER_SEMANTICS_ID
    assert binding.source_git_blob_sha1 == SOURCE_VERIFIER_BLOB


# ---------------------------------------------------------------------------
# 6. MachineExperience round trip.
# ---------------------------------------------------------------------------


def test_machine_experience_succeeds_with_defaults() -> None:
    experience = machine_experience_from_trajectory(_trajectory())

    assert experience.maturity is ExperienceMaturity.E0_TRACEABLE
    assert set(experience.trajectory.original_evaluation.component_scores) == {
        "outcome",
        "state",
        "constraints",
        "side_effects",
        "process",
        "efficiency",
        "evidence",
    }


# ---------------------------------------------------------------------------
# 7. No private leakage.
# ---------------------------------------------------------------------------


def test_public_and_buyer_safe_payloads_carry_no_verifier_only_truth() -> None:
    episode = _catalog_episode()
    episode.oracle.metadata["PRIVATE-ORACLE-SECRET"] = True
    runtime, submission = _solve(episode)
    trajectory = trajectory_v2_from_operational_runtime(
        runtime,
        context=_context(runtime, submission, breakdown=_fresh_breakdown(runtime)),
    )

    public = json.dumps(trajectory.public_payload(), sort_keys=True)
    buyer = json.dumps(trajectory.buyer_safe_payload(), sort_keys=True)

    for marker in _PRIVATE_MARKERS:
        assert marker not in public
        assert marker not in buyer
    for event in trajectory.events:
        for forbidden_key in (
            "state_changes",
            "side_effects",
            "forbidden",
            "consequence_severity",
            "blocked_reason",
        ):
            assert forbidden_key not in event.payload
    assert "operational_breakdown" not in public
    assert "operational_breakdown" not in buyer


def test_private_payload_keeps_verifier_only_truth_out_of_the_public_event() -> None:
    trajectory = _trajectory()

    assert any(event.private_payload for event in trajectory.events)
    assert all(
        event.private_payload.get("state_changes") is not None
        for event in trajectory.events
        if event.event_type == "act"
    )


# ---------------------------------------------------------------------------
# 8. Import direction: operational must not import trajectory.
# ---------------------------------------------------------------------------


def test_operational_package_does_not_import_trajectory() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import investigation_world.operational, sys;"
            " print('investigation_world.trajectory' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert probe.stdout.strip() == "False", (
        "operational -> trajectory import would make this adapter part of an import cycle"
    )


# ---------------------------------------------------------------------------
# 9. NativeOperationalRuntime goes through the same code path.
# ---------------------------------------------------------------------------


def test_native_runtime_adapts_through_the_same_path(tmp_path) -> None:
    """Adaptation is shared, but replay reverification is not claimed for the native runtime.

    ``NativeOperationalRuntime.submit()`` writes ``native_artifact.*`` keys into the runtime
    state *before* ``super().submit()`` scores, and asserts them in ``oracle.target_state``.
    Those keys are not the ``state_changes`` of any ``ActionEvent``, so the state the engine
    replays from the recorded events cannot equal the state the verifier scored. That is a
    property of the native runtime's own scoring path, not of this adapter, which is why the
    same-context, same-code-path adaptation is what this lane asserts.
    """
    episode = _apply_realism(
        build_gis_operations_world(seed=42), index=3, family="projection_alignment"
    )
    runtime = NativeOperationalRuntime(episode, artifact_root=tmp_path)
    _execute_required_actions(runtime)
    submission = _submission(episode)
    breakdown = runtime.submit(submission)

    trajectory = trajectory_v2_from_operational_runtime(
        runtime,
        context=_context(runtime, submission, breakdown=breakdown),
    )
    assert [event.event_type for event in trajectory.events].count("submit") == 1
    assert trajectory.usage.environment_cost == pytest.approx(float(runtime.budget.spent))
    assert trajectory.original_evaluation.reward == pytest.approx(breakdown.overall_reward)
    assert set(trajectory.original_evaluation.component_scores) == _REWARD_COMPONENTS
    assert trajectory.provenance[0].adapter_id == OPERATIONAL_RUNTIME_ADAPTER_ID


# ---------------------------------------------------------------------------
# 10. Provenance, adapter identity, and unknown-not-default across the catalog.
# ---------------------------------------------------------------------------


def test_provenance_records_the_adapter_and_the_source_runtime() -> None:
    runtime, submission, breakdown = _closed_runtime()
    trajectory = trajectory_v2_from_operational_runtime(
        runtime,
        context=_context(runtime, submission, breakdown=breakdown),
    )

    assert trajectory.provenance[0].adapter_id == OPERATIONAL_RUNTIME_ADAPTER_ID
    assert trajectory.provenance[0].adapter_version == OPERATIONAL_RUNTIME_ADAPTER_VERSION
    assert trajectory.provenance[0].source_kind == "operational.episode_execution"
    assert trajectory.provenance[0].source_id == runtime.episode.episode_id
    assert trajectory.provenance[0].source_digest is not None
    assert trajectory.termination.terminated is True
    assert trajectory.capability_tags == ()


def test_supplied_state_digests_win_over_computed_ones() -> None:
    runtime, submission, breakdown = _closed_runtime()
    trajectory = trajectory_v2_from_operational_runtime(
        runtime,
        context=_context(
            runtime,
            submission,
            breakdown=breakdown,
            initial_state_digest="a" * 64,
            final_state_digest="b" * 64,
            initial_state_scope=StateDigestScope.SEMANTIC,
        ),
    )
    assert trajectory.initial_state.digest == "a" * 64
    assert trajectory.final_state is not None
    assert trajectory.final_state.digest == "b" * 64


def test_every_catalog_domain_adapts_without_inventing_facts() -> None:
    """All five production catalog worlds adapt through the same code path."""
    for episode in build_operational_suite(seed=7):
        runtime, submission = _solve(_deepen(episode))
        trajectory = trajectory_v2_from_operational_runtime(
            runtime,
            context=_context(runtime, submission, breakdown=_fresh_breakdown(runtime)),
        )
        assert trajectory.task.task_id == episode.task.task_id
        assert trajectory.world.world_id == episode.world_id
        assert trajectory.trajectory_id.startswith("TRAJ-V2-")
        # Facts the runtime cannot supply stay unknown rather than being defaulted.
        assert trajectory.world.environment_id is None
        assert trajectory.task.split is None
        assert trajectory.reset.seed is None
        assert trajectory.termination.truncated is None
