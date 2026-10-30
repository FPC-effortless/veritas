"""Joint G-02/G-03 acceptance using synthetic native artifacts, not model runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from investigation_world.experience import ExperienceMaturity, machine_experience_from_trajectory
from investigation_world.foundry.capability_families import (
    external_investigation_capability_contract,
)
from investigation_world.foundry.models import stable_hash
from investigation_world.operational.models import WorldDomain, capability_binding_from_contract
from investigation_world.portable_contract import serialize_portable_contract
from investigation_world.portable_contract.models import PortableOperationalContract
from investigation_world.trajectory import (
    ArtifactIdentity,
    OperationalRuntimeAdapterContext,
    TrajectoryV2,
    trajectory_v2_from_operational_runtime,
)
from investigation_world.trajectory.models import canonical_hash
from investigation_world.trajectory.reverify import (
    OperationalReplayEvidence,
    ReverificationStatus,
    attach_operational_replay_evidence,
    reverify_trajectory,
)


@pytest.mark.parametrize("persistent", [False, True])
@pytest.mark.parametrize("corrupt", [False, True])
def test_bound_native_world_actual_adapter_offline_experience(
    persistent, corrupt, tmp_path, monkeypatch
):
    # Reuse real native execution/corruption fixtures; never manufacture trajectory events.
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "trajectory"))
    from test_native_submission_reverification import _run, episodes
    from test_operational_runtime_adapter import _registry

    episode = episodes.__wrapped__()[WorldDomain.INVESTIGATION_OSINT]
    episode.capability = capability_binding_from_contract(
        external_investigation_capability_contract(), episode=episode
    )
    runtime, contract, initial, submission, result = _run(
        episode, tmp_path, persistent=persistent, corrupt=corrupt, blocked=True
    )
    restored = PortableOperationalContract.model_validate_json(
        serialize_portable_contract(contract)
    )
    assert restored.public.capability.model_dump() == episode.capability.model_dump()
    assert restored.contract_id == contract.contract_id
    assert restored.public.schema_version == "1.1.0"
    identity = ArtifactIdentity(
        artifact_id=contract.contract_id,
        contract="veritas.portable-operational-contract",
        version=contract.schema_version,
    )
    context = OperationalRuntimeAdapterContext(
        submission=submission, breakdown=result, portable_operational_contract=identity
    )
    trajectory = trajectory_v2_from_operational_runtime(runtime, context=context)
    assert trajectory == trajectory_v2_from_operational_runtime(runtime, context=context)
    receipt = runtime.last_native_submission
    evidence = OperationalReplayEvidence(
        portable_contract=restored,
        trajectory_events_digest=canonical_hash(trajectory.events),
        initial_state=initial,
        initial_state_digest=stable_hash(initial),
        final_state=runtime.state_snapshot(),
        final_state_digest=stable_hash(runtime.state_snapshot()),
        action_events=tuple(runtime.events),
        submission=submission,
        tool_calls=runtime.budget.calls,
        cost_spent=runtime.budget.spent,
        native_submission=receipt,
    )
    payload = trajectory.model_dump(mode="python")
    payload.update(trajectory_id="", evidence_references=(evidence.reference(),))
    referenced = TrajectoryV2.model_validate(payload)
    attached = attach_operational_replay_evidence(referenced, evidence.for_trajectory(referenced))
    registry, verifier = _registry()
    outcome = reverify_trajectory(attached, verifier=verifier, registry=registry)
    assert outcome.status is ReverificationStatus.REVERIFIED
    assert outcome.record.private_metadata["verification_breakdown"] == result.model_dump(
        mode="json"
    )
    assert json.loads(receipt.verification_json)["valid"] is (not corrupt)
    assert runtime.events[0].blocked
    experience = machine_experience_from_trajectory(attached)
    assert experience.maturity is ExperienceMaturity.E0_TRACEABLE
    assert experience.trajectory.world.portable_operational_contract == identity
    for safe in (attached.public_payload(), attached.buyer_safe_payload()):
        serialized = json.dumps(safe)
        assert receipt.receipt_id not in serialized
        assert str(tmp_path) not in serialized
        assert "operational_reverification_evidence" not in serialized
