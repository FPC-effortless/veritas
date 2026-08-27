from __future__ import annotations

import hashlib
import json
import random

import pytest

from investigation_world.integrations.woyengi import (
    WoyengiHiddenOracle,
    WorldBundleAdapterError,
    adapt_pinned_world_bundle_fixture,
    adapt_world_bundle,
)
from investigation_world.operational.models import WorldDomain
from investigation_world.operational.runtime import OperationalRuntime


PRIVATE_TARGET_VALUE = "PRIVATE_TARGET::service-recovered"
PRIVATE_EFFECT_TOKEN = "PRIVATE_EFFECT::set-service-healthy"
PRIVATE_EVIDENCE_LOCATOR = "sealed://evaluator/service-health-proof"
PRIVATE_AUTH_TOKEN = "PRIVATE_AUTH::evaluator-only"


def _bundle() -> dict:
    return {
        "contract": "woyengi.world-bundle.v0.1",
        "id": "worldbundle:incident-recovery:001",
        "version": "0.1.0",
        "sourceSpecRef": "opspec:incident-recovery",
        "sourceSpecVersion": "0.1.0",
        "compatibility": {"minimumRuntimeVersion": "0.1.0"},
        "public": {
            "objective": "Recover the checkout service without losing customer data.",
            "actorRoles": ["incident_commander", "sre"],
            "actionSurface": [
                {"id": "action:inspect", "name": "Inspect service", "kind": "READ"},
                {"id": "action:mitigate", "name": "Mitigate service", "kind": "EXECUTE"},
            ],
            "observationRefs": ["observation:checkout-status"],
            "assetDescriptors": [
                {
                    "id": "artifact:runbook",
                    "kind": "runbook",
                    "format": "text/markdown",
                    "contentHash": "sha256:public-runbook",
                }
            ],
            "outcomeContractRefs": ["outcome:recover-checkout"],
            "provenanceRefs": ["provenance:public-incident-record"],
        },
        "privateEvaluator": {
            "targetAssertionRefs": ["target:service-recovered"],
            "invariantRefs": ["invariant:no-hidden-data-loss"],
            "hiddenEffectRefs": ["effect:mitigate-service"],
            "evidenceLocatorRefs": ["evidence-locator:private-health-proof"],
        },
        "partitionManifest": [
            {"id": "action:inspect", "partition": "public", "kind": "action"},
            {"id": "action:mitigate", "partition": "public", "kind": "action"},
            {
                "id": "observation:checkout-status",
                "partition": "public",
                "kind": "observation",
            },
            {"id": "artifact:runbook", "partition": "public", "kind": "artifact"},
            {"id": "outcome:recover-checkout", "partition": "public", "kind": "outcome-contract"},
            {"id": "evidence:health-check", "partition": "public", "kind": "evidence-requirement"},
            {
                "id": "provenance:public-incident-record",
                "partition": "public",
                "kind": "provenance",
            },
            {
                "id": "target:service-recovered",
                "partition": "private-evaluator",
                "kind": "target-assertion",
            },
            {
                "id": "invariant:no-hidden-data-loss",
                "partition": "private-evaluator",
                "kind": "invariant",
            },
            {
                "id": "effect:mitigate-service",
                "partition": "private-evaluator",
                "kind": "hidden-effect",
            },
            {
                "id": "evidence-locator:private-health-proof",
                "partition": "private-evaluator",
                "kind": "evidence-locator",
            },
        ],
        "provenanceRefs": ["provenance:public-incident-record"],
    }


def _member_payloads() -> dict[str, dict]:
    return {
        "outcome:recover-checkout": {
            "contract": "woyengi.outcome-contract.v0.1",
            "id": "outcome:recover-checkout",
            "version": "0.1.0",
            "objective": "Recover the checkout service without losing customer data.",
            "successAssertions": [
                {
                    "id": "success:checkout-healthy",
                    "description": "Checkout is healthy and serving requests.",
                }
            ],
            "invariants": ["Do not lose customer data."],
            "requiredEvidenceRefs": ["evidence:health-check"],
            "verificationRequirements": ["Verify checkout health independently."],
            "effectConstraints": [
                {"effectClass": "EXTERNAL", "policy": "REQUIRE_RECONCILIATION"}
            ],
            "budget": {
                "maximumCost": 20,
                "currency": "credits",
                "maximumAttempts": 5,
            },
            "acceptanceAuthorityRequirements": ["incident_commander"],
        },
        "target:service-recovered": {
            "id": "target:service-recovered",
            "field": "service.status",
            "expectedValue": PRIVATE_TARGET_VALUE,
        },
        "invariant:no-hidden-data-loss": {
            "id": "invariant:no-hidden-data-loss",
            "statement": "Evaluator confirms no hidden data loss occurred.",
            "privateThreshold": 0,
        },
        "effect:mitigate-service": {
            "id": "effect:mitigate-service",
            "actionRef": "action:mitigate",
            "token": PRIVATE_EFFECT_TOKEN,
            "set": {"service.status": "healthy"},
        },
        "evidence-locator:private-health-proof": {
            "id": "evidence-locator:private-health-proof",
            "locator": PRIVATE_EVIDENCE_LOCATOR,
            "authorization": PRIVATE_AUTH_TOKEN,
        },
    }


def test_adapter_preserves_public_semantics_and_private_evaluator_material():
    episode = adapt_world_bundle(
        _bundle(),
        member_payloads=_member_payloads(),
        domain=WorldDomain.ENTERPRISE_OPERATIONS,
    )

    assert episode.episode_id == "worldbundle:incident-recovery:001"
    assert episode.world_id == "worldbundle:incident-recovery:001"
    assert episode.task.task_id == "worldbundle:incident-recovery:001"
    assert episode.task.objective == "Recover the checkout service without losing customer data."
    assert episode.task.role == "incident_commander | sre"
    assert episode.task.metadata["woyengi"]["actor_roles"] == ["incident_commander", "sre"]
    assert episode.task.metadata["woyengi"]["action_surface"] == _bundle()["public"]["actionSurface"]
    assert episode.task.metadata["woyengi"]["asset_descriptors"] == _bundle()["public"]["assetDescriptors"]
    assert episode.task.metadata["woyengi"]["outcome_contract_refs"] == ["outcome:recover-checkout"]
    assert episode.task.metadata["woyengi"]["budgets"] == [
        {"maximumCost": 20, "currency": "credits", "maximumAttempts": 5}
    ]
    assert episode.task.metadata["woyengi"]["evidence_requirements"] == ["evidence:health-check"]
    assert "Do not lose customer data." in episode.task.constraints
    assert "required-evidence:evidence:health-check" in episode.task.constraints

    actions = {action.name: action for action in episode.task.available_actions}
    assert set(actions) == {"action:inspect", "action:mitigate"}
    assert actions["action:inspect"].kind.value == "read"
    assert actions["action:mitigate"].kind.value == "execute"
    assert episode.task.metadata["woyengi"]["action_bindings"]["action:mitigate"] == {
        "id": "action:mitigate",
        "name": "Mitigate service",
        "kind": "EXECUTE",
    }

    runbook = next(record for record in episode.records if record.object_id == "artifact:runbook")
    assert runbook.fields["descriptor"] == _bundle()["public"]["assetDescriptors"][0]

    assert isinstance(episode.oracle, WoyengiHiddenOracle)
    assert episode.oracle.max_cost == 20
    assert episode.oracle.max_tool_calls == 5
    assert episode.oracle.target_assertion_refs == ["target:service-recovered"]
    assert episode.oracle.invariant_refs == ["invariant:no-hidden-data-loss"]
    assert episode.oracle.hidden_effect_refs == ["effect:mitigate-service"]
    assert episode.oracle.evidence_locator_refs == ["evidence-locator:private-health-proof"]
    assert episode.oracle.private_member_payloads["target:service-recovered"]["expectedValue"] == PRIVATE_TARGET_VALUE
    assert (
        episode.oracle.private_member_payloads["evidence-locator:private-health-proof"]["locator"]
        == PRIVATE_EVIDENCE_LOCATOR
    )
    # Woyengi remains the canonical semantic source. Opaque evaluator material is retained
    # in the extension rather than guessed into Veritas-native target/effect structures.
    assert episode.oracle.target_state == []
    assert episode.oracle.invariants == []
    assert episode.oracle.action_effects == []


def test_public_payload_never_exposes_private_partition_ids_or_bytes():
    episode = adapt_world_bundle(_bundle(), member_payloads=_member_payloads())
    public_text = json.dumps(episode.public_payload(), sort_keys=True)

    for secret in (
        "target:service-recovered",
        "invariant:no-hidden-data-loss",
        "effect:mitigate-service",
        "evidence-locator:private-health-proof",
        PRIVATE_TARGET_VALUE,
        PRIVATE_EFFECT_TOKEN,
        PRIVATE_EVIDENCE_LOCATOR,
        PRIVATE_AUTH_TOKEN,
    ):
        assert secret not in public_text

    public_manifest = episode.task.metadata["woyengi"]["partition_manifest"]
    assert public_manifest
    assert {member["partition"] for member in public_manifest} == {"public"}


def test_adapter_rejects_public_reference_to_private_evaluator_member():
    bundle = _bundle()
    bundle["public"]["observationRefs"].append("target:service-recovered")

    with pytest.raises(WorldBundleAdapterError, match="private-evaluator"):
        adapt_world_bundle(bundle, member_payloads=_member_payloads())


def test_seeded_action_replay_is_deterministic_without_woyengi_service():
    first_episode = adapt_world_bundle(_bundle(), member_payloads=_member_payloads())
    second_episode = adapt_world_bundle(_bundle(), member_payloads=_member_payloads())
    assert first_episode.model_dump(mode="json") == second_episode.model_dump(mode="json")

    seed = 1729
    action_ids = ["action:inspect", "action:mitigate"]
    first_rng = random.Random(seed)
    second_rng = random.Random(seed)
    first_sequence = [first_rng.choice(action_ids) for _ in range(5)]
    second_sequence = [second_rng.choice(action_ids) for _ in range(5)]
    assert first_sequence == second_sequence

    first_runtime = OperationalRuntime(first_episode)
    second_runtime = OperationalRuntime(second_episode)
    first_results = [first_runtime.act(action_id) for action_id in first_sequence]
    second_results = [second_runtime.act(action_id) for action_id in second_sequence]

    assert first_results == second_results
    assert first_runtime.trace() == second_runtime.trace()
    assert first_runtime.public_payload() == second_runtime.public_payload()


def test_pinned_fixture_adapter_verifies_exact_sha256_before_acceptance():
    raw = json.dumps(_bundle(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected_sha256 = hashlib.sha256(raw).hexdigest()

    episode = adapt_pinned_world_bundle_fixture(
        raw,
        expected_sha256=expected_sha256,
        member_payloads=_member_payloads(),
    )
    assert episode.metadata["woyengi_source"]["fixture_sha256"] == expected_sha256

    with pytest.raises(WorldBundleAdapterError, match="fixture SHA-256"):
        adapt_pinned_world_bundle_fixture(
            raw,
            expected_sha256="0" * 64,
            member_payloads=_member_payloads(),
        )
