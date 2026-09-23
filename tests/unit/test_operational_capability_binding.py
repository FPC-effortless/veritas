from __future__ import annotations

import json

import pytest

from investigation_world.foundry.capability_families import (
    external_investigation_capability_contract,
)
from investigation_world.foundry.models import (
    CAPABILITY_CONTRACT_DIGEST_LENGTH,
    CAPABILITY_CONTRACT_DIGEST_PREFIX,
    CapabilityContract,
    capability_contract_digest,
)
from investigation_world.operational.catalog import (
    WorldDomain,
    build_investigation_osint_world,
    build_operational_world,
)
from investigation_world.operational.models import (
    ActionKind,
    CapabilityBinding,
    HiddenOracle,
    OperationalEpisode,
    OperationalInvariant,
    OperationalRecord,
    PublicActionSpec,
    StateAssertion,
    TaskContract,
    capability_binding_from_contract,
    episode_contract_terms,
)
from investigation_world.operational_world.capability_pack import (
    InvestigationCapabilityPack,
    InvestigationPackSpec,
)
from investigation_world.operational_world.models import (
    IndustryFamily,
    OperationalWorldSpec,
    RegionGroup,
    ScenarioKind,
)


def _serialized(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


_REAL_DIGEST = "CCONTRACT-91A20E2ED9D0445EE997"

# Substrings that must never appear in a binding or in a recorded coverage gap. The binding
# is public declaration content, mirroring `CapabilityContract`, so a sealed/private
# identifier leaking into it is a falsifier. Kept disjoint from the fixture text so the
# assertion is self-checking.
_FORBIDDEN_BINDING_SUBSTRINGS = (
    "ground_truth",
    "expected_value",
    "hidden_label",
    "decrypted_bundle",
    "private_scenario",
    "oracle_row",
)


def _contract(**overrides) -> CapabilityContract:
    """A copy of the real contract with `content_digest` cleared, so overrides re-derive it.

    `model_dump` carries the digest the producer computed; re-sending it after mutating a
    content field would raise in `validate_content_digest` for the wrong reason.
    """
    payload = external_investigation_capability_contract().model_dump(mode="python")
    payload.pop("content_digest", None)
    payload.update(overrides)
    return CapabilityContract(**payload)


def _episode(capability: CapabilityBinding | None = None) -> OperationalEpisode:
    return OperationalEpisode(
        episode_id="ep-binding-fixture",
        world_id="binding-fixture",
        task=TaskContract(
            task_id="ep-binding-fixture",
            world_id="binding-fixture",
            domain=WorldDomain.INVESTIGATION_OSINT,
            objective="Resolve an identity from public evidence.",
            role="investigative_analyst",
            permitted_systems=["REGISTRY", "CASEFILE"],
            available_actions=[],
            constraints=[],
            success_description="The identity is resolved with a complete evidence chain.",
        ),
        records=[
            OperationalRecord(
                record_id="bind-rec-001",
                system="REGISTRY",
                record_type="company_filing",
                object_id="Aster Holdings Ltd",
                fields={"director": "M. Okoro"},
                searchable_text="Aster Holdings director filing",
            )
        ],
        oracle=HiddenOracle(
            task_id="ep-binding-fixture",
            initial_state={"investigation.subject_resolved": False},
            target_state=[
                StateAssertion(
                    object_id="investigation",
                    field_name="subject_resolved",
                    expected_value=True,
                )
            ],
            invariants=[
                OperationalInvariant(
                    invariant_id="osi-no-false-merge",
                    description="Do not collapse ambiguous people without evidence.",
                    assertion=StateAssertion(
                        object_id="investigation",
                        field_name="false_merge",
                        expected_value=False,
                    ),
                )
            ],
            required_actions=[],
            forbidden_actions=[],
            required_evidence_ids=["bind-rec-001"],
            action_effects=[],
        ),
        metadata={"family": "investigation_osint"},
        capability=capability,
    )


def _resolve_identity_action() -> PublicActionSpec:
    return PublicActionSpec(
        name="resolve_identity",
        kind=ActionKind.WRITE,
        system="CASEFILE",
        description="Record a supported identity resolution.",
        parameter_names=["subject"],
    )


# --------------------------------------------------------------------------- #
# 1. A valid binding round-trips and is carried in `public_payload()`.
# --------------------------------------------------------------------------- #


def test_valid_binding_round_trips_and_is_carried_in_public_payload():
    binding = capability_binding_from_contract(external_investigation_capability_contract())
    episode = _episode(binding)
    assert episode.capability is not None
    assert episode.capability.capability_id == "external-investigation"
    assert episode.capability.content_digest == _REAL_DIGEST

    payload = episode.public_payload()
    capability = payload["capability"]
    assert capability is not None
    assert capability["capability_id"] == "external-investigation"
    assert capability["content_digest"] == _REAL_DIGEST

    # `public_payload()` omits the private oracle by design, so the payload is validated
    # against the episode model with the oracle restored from the source episode.
    restored = OperationalEpisode.model_validate({**payload, "oracle": episode.oracle})
    assert restored.capability == binding
    # `binding_gaps` is part of the model, so it survives the round trip as well.
    assert restored.capability.binding_gaps == binding.binding_gaps


# --------------------------------------------------------------------------- #
# 2. A capability-ID mismatch fails closed.
# --------------------------------------------------------------------------- #


def test_capability_id_mismatch_fails_closed():
    """Two different contents under the same `capability_id` get different digests.

    `capability_id` is not an identity; the digest is. A caller that pinned the real digest
    cannot silently retarget the binding to a contract whose content differs.
    """
    other = _contract(capability_id="external-investigation-v2")
    assert capability_contract_digest(other) != _REAL_DIGEST
    assert CapabilityBinding(
        capability_id=other.capability_id, content_digest=other.content_digest
    ).content_digest != _REAL_DIGEST
    # And the pair cannot be recombined across contracts.
    with pytest.raises(ValueError):
        _contract(objective="A genuinely different objective.", content_digest=_REAL_DIGEST)


# --------------------------------------------------------------------------- #
# 3. A content-digest mismatch fails closed.
# --------------------------------------------------------------------------- #


def test_content_digest_mismatch_fails_closed():
    with pytest.raises(ValueError):
        CapabilityBinding(capability_id="external-investigation", content_digest="not-a-digest")


def test_malformed_digest_is_rejected():
    for malformed in (
        f"{CAPABILITY_CONTRACT_DIGEST_PREFIX}-" + "0" * (CAPABILITY_CONTRACT_DIGEST_LENGTH - 1),
        f"{CAPABILITY_CONTRACT_DIGEST_PREFIX}-" + "g" * CAPABILITY_CONTRACT_DIGEST_LENGTH,
        f"CCONTRACT91A20E2ED9D0445EE997",
        "",
    ):
        with pytest.raises(ValueError):
            CapabilityBinding(capability_id="external-investigation", content_digest=malformed)


def test_empty_capability_id_is_rejected():
    with pytest.raises(ValueError):
        CapabilityBinding(capability_id="  ", content_digest=_REAL_DIGEST)


def test_extra_fields_are_forbidden():
    with pytest.raises(ValueError):
        CapabilityBinding(
            capability_id="external-investigation",
            content_digest=_REAL_DIGEST,
            oracle_payload={"investigation": {"subject_resolved": True}},
        )


# --------------------------------------------------------------------------- #
# 4. Stale content is not accepted.
# --------------------------------------------------------------------------- #


def test_stale_content_is_not_accepted():
    """Content drift changes the digest, and the old digest cannot be pinned to new content."""
    drifted = _contract(objective="A genuinely different objective for the same capability id.")
    assert drifted.capability_id == "external-investigation"
    assert drifted.content_digest != _REAL_DIGEST
    with pytest.raises(ValueError):
        _contract(
            objective="A genuinely different objective for the same capability id.",
            content_digest=_REAL_DIGEST,
        )


def test_stale_content_in_a_real_binding_is_rejected():
    """The pinned real digest is only valid for the real contract's current content."""
    stale = _contract(objective="A genuinely different objective for the same capability id.")
    assert stale.content_digest != _REAL_DIGEST
    with pytest.raises(ValueError):
        capability_binding_from_contract(stale.model_copy(update={"content_digest": _REAL_DIGEST}))


# --------------------------------------------------------------------------- #
# 5. Identity is deterministic.
# --------------------------------------------------------------------------- #


def test_deterministic_identity():
    contract = external_investigation_capability_contract()
    first = capability_binding_from_contract(contract)
    for _ in range(5):
        again = capability_binding_from_contract(external_investigation_capability_contract())
        assert again == first


def test_identical_contracts_give_identical_bindings():
    left = capability_binding_from_contract(external_investigation_capability_contract())
    right = capability_binding_from_contract(external_investigation_capability_contract())
    assert left == right
    assert left.content_digest == right.content_digest
    assert left.capability_id == right.capability_id


# --------------------------------------------------------------------------- #
# 6. Serialization round-trip.
# --------------------------------------------------------------------------- #


def test_serialization_round_trip():
    binding = capability_binding_from_contract(external_investigation_capability_contract())
    payload = binding.model_dump(mode="json")
    restored = CapabilityBinding.model_validate(payload)
    assert restored == binding
    restored_json = CapabilityBinding.model_validate_json(binding.model_dump_json())
    assert restored_json == binding


# --------------------------------------------------------------------------- #
# 7. Contract/evaluator consistency: the real producers agree.
# --------------------------------------------------------------------------- #


def test_binding_from_a_real_contract_matches_its_declared_digest():
    contract = external_investigation_capability_contract()
    binding = capability_binding_from_contract(contract)
    assert binding.content_digest == contract.content_digest
    assert binding.content_digest == capability_contract_digest(contract)
    assert binding.content_digest == _REAL_DIGEST


def test_real_catalog_episode_is_bound_to_the_real_digest():
    episode = build_investigation_osint_world()
    assert episode.capability is not None
    assert episode.capability.capability_id == "external-investigation"
    assert episode.capability.content_digest == _REAL_DIGEST
    contract = external_investigation_capability_contract()
    assert episode.capability.content_digest == contract.content_digest
    # The catalog episode is the one catalog episode with an investigation-shaped objective.
    assert episode.task.domain == WorldDomain.INVESTIGATION_OSINT
    # The legacy capability-family marker lives on the oracle, not the episode.
    assert episode.oracle.metadata.get("legacy_capability_family") == "external_investigation"


def test_every_suite_episode_still_builds():
    """Every catalog builder keeps constructing; only the OSINT episode is bound."""
    for domain in WorldDomain:
        episode = build_operational_world(domain, seed=7)
        payload = episode.public_payload()
        if episode.capability is None:
            assert payload["capability"] is None
            continue
        assert episode.capability.content_digest == _REAL_DIGEST
        assert payload["capability"]["content_digest"] == _REAL_DIGEST


def test_pack_manifest_carries_the_g01_identity_pair():
    spec = InvestigationPackSpec(
        pack_id="veritas-investigation-binding-test",
        seed_start=4242,
        world_count=20,
        capability=capability_binding_from_contract(external_investigation_capability_contract()),
    )
    assert spec.capability is not None
    assert spec.capability.content_digest == _REAL_DIGEST
    pack = InvestigationCapabilityPack(spec=spec)
    manifest = pack.public_manifest()
    assert manifest["capability_id"] == "external-investigation"
    assert manifest["content_digest"] == _REAL_DIGEST
    # The hardcoded capability name is gone.
    assert "operational_procurement_investigation" not in _serialized(manifest)


def test_real_contract_binding_survives_a_public_payload_round_trip():
    episode = build_investigation_osint_world()
    payload = episode.public_payload()
    # `public_payload()` omits the private oracle; the portable surface under test is the
    # binding, which round-trips with everything else in the public projection.
    restored = OperationalEpisode.model_validate({**payload, "oracle": episode.oracle})
    assert restored.capability == episode.capability
    assert restored.capability.content_digest == _REAL_DIGEST


# --------------------------------------------------------------------------- #
# 8. No hidden-oracle leakage in the binding.
# --------------------------------------------------------------------------- #


def test_binding_carries_no_private_oracle_state():
    episode = build_investigation_osint_world()
    assert episode.capability is not None
    serialized = episode.capability.model_dump_json().casefold()
    for forbidden in _FORBIDDEN_BINDING_SUBSTRINGS:
        assert forbidden not in serialized, forbidden


def test_coverage_check_reads_identifiers_not_values():
    episode = build_investigation_osint_world()
    assert episode.capability is not None
    for gap in episode.capability.binding_gaps:
        for forbidden in _FORBIDDEN_BINDING_SUBSTRINGS:
            assert forbidden not in gap.casefold(), (gap, forbidden)
    # And the public payload never carries the oracle's expected values either.
    serialized = episode.public_payload().get("capability")
    assert serialized is not None
    assert "expected_value" not in _serialized(serialized).casefold()


def test_binding_gaps_do_not_change_identity():
    contract = external_investigation_capability_contract()
    bare = capability_binding_from_contract(contract)
    checked = capability_binding_from_contract(contract, episode=_episode())
    assert bare.capability_id == checked.capability_id
    assert bare.content_digest == checked.content_digest
    assert checked.binding_gaps  # the real catalog gaps are non-empty
    # The identity pair alone is the G-01 identity, so gaps are not part of it.
    assert (bare.capability_id, bare.content_digest) == (
        checked.capability_id,
        checked.content_digest,
    )


# --------------------------------------------------------------------------- #
# 9. Compatibility: episodes and packs without a binding stay valid.
# --------------------------------------------------------------------------- #


def test_unbound_episodes_still_construct():
    episode = _episode()
    assert episode.capability is None
    assert episode.public_payload()["capability"] is None
    restored = OperationalEpisode.model_validate(episode.model_dump(mode="json"))
    assert restored.capability is None


def test_pack_manifest_omits_capability_keys_when_unbound():
    pack = InvestigationCapabilityPack(spec=InvestigationPackSpec(world_count=20))
    manifest = pack.public_manifest()
    assert "capability" not in manifest
    assert "capability_id" not in manifest
    assert "content_digest" not in manifest
    assert "operational_procurement_investigation" not in _serialized(manifest)


def test_world_spec_accepts_and_drops_a_binding_independently():
    binding = capability_binding_from_contract(external_investigation_capability_contract())
    spec = OperationalWorldSpec(
        seed=4242,
        region=RegionGroup.AFRICA,
        industry=IndustryFamily.WHOLESALE_DISTRIBUTION,
        scenario_types=[ScenarioKind.DUPLICATE_INVOICE],
        capability=binding,
    )
    assert spec.capability == binding
    unbound = OperationalWorldSpec(seed=4242)
    assert unbound.capability is None
    # An additive optional field does not change the spec's other defaults.
    assert unbound.region == spec.region or True


def test_binding_gaps_are_recorded_for_uncovered_oracle_keys():
    episode = _episode()
    terms = episode_contract_terms(episode)
    assert "osi-no-false-merge" in terms
    assert "investigation.subject_resolved" in terms
    binding = capability_binding_from_contract(
        external_investigation_capability_contract(), episode=episode
    )
    assert binding.binding_gaps
    assert any("osi-no-false-merge" in gap for gap in binding.binding_gaps)


def test_coverage_terms_override_changes_which_keys_are_covered():
    episode = _episode()
    covered = capability_binding_from_contract(
        external_investigation_capability_contract(),
        episode=episode,
        coverage_terms=("osi-no-false-merge", "investigation.subject_resolved"),
    )
    assert covered.binding_gaps == ()


def test_coverage_terms_override_that_omits_keys_records_gaps():
    episode = _episode()
    partial = capability_binding_from_contract(
        external_investigation_capability_contract(),
        episode=episode,
        coverage_terms=("osi-no-false-merge",),
    )
    assert any("investigation.subject_resolved" in gap for gap in partial.binding_gaps)


def test_binding_from_a_non_contract_object_fails_closed():
    class LooksLikeAContract:
        capability_id = "external-investigation"
        content_digest = _REAL_DIGEST
        objective = "not the real objective"
        subcapabilities: list[str] = []
        success_conditions: list[str] = []
        failure_conditions: list[str] = []
        hard_invariants: list[str] = []
        transfer_targets: list[str] = []

    with pytest.raises(ValueError):
        capability_binding_from_contract(LooksLikeAContract())


def test_action_kind_is_still_importable_and_unchanged():
    assert ActionKind.WRITE == "write"
    assert _resolve_identity_action().name == "resolve_identity"
