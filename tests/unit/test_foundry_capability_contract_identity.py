from __future__ import annotations

import copy
import pathlib
import re
import subprocess
import sys

import pytest

from investigation_world.foundry import (
    CapabilityContract,
    companyworld_capability_contract,
    external_investigation_capability_contract,
    selective_agency_capability_contract,
)
from investigation_world.foundry.cli import _artifact_run_id
from investigation_world.foundry.models import (
    CAPABILITY_CONTRACT_DIGEST_LENGTH,
    CAPABILITY_CONTRACT_DIGEST_PREFIX,
    capability_contract_digest,
    capability_contract_digest_payload,
    stable_hash,
)
from investigation_world.foundry.training_product import TrainerKind

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

_DIGEST_PATTERN = re.compile(
    r"^" + CAPABILITY_CONTRACT_DIGEST_PREFIX
    + r"-[0-9A-F]{" + str(CAPABILITY_CONTRACT_DIGEST_LENGTH) + r"}$"
)

_BASE_CONTRACT: dict = {
    "capability_id": "contract-identity-fixture",
    "version": "1",
    "objective": "Audit a canonical evidence lifecycle end to end.",
    "subcapabilities": ["discover", "verify", "communicate"],
    "success_conditions": ["claims are supported by public evidence"],
    "failure_conditions": ["unsupported claim"],
    "hard_invariants": ["no privileged oracle access"],
    "transfer_targets": ["unseen entities"],
}

# Substrings that must never appear in a digest payload. The contract is a public
# declaration, so a sealed/private identifier leaking into it is a falsifier. Kept
# disjoint from the fixture text above so the assertion is self-checking.
_FORBIDDEN_PAYLOAD_SUBSTRINGS = (
    "ground_truth",
    "expected_value",
    "hidden_label",
    "decrypted_bundle",
    "private_scenario",
    "oracle_row",
)


def _contract(**overrides) -> CapabilityContract:
    payload = copy.deepcopy(_BASE_CONTRACT)
    payload.update(overrides)
    return CapabilityContract(**payload)


def _real_contracts() -> list[tuple[str, CapabilityContract]]:
    return [
        ("external_investigation", external_investigation_capability_contract()),
        ("selective_agency", selective_agency_capability_contract()),
        ("companyworld", companyworld_capability_contract()),
    ]


def test_digest_is_derived_and_matches_expected_format():
    contract = _contract()
    assert contract.content_digest == capability_contract_digest(contract)
    assert _DIGEST_PATTERN.match(contract.content_digest), contract.content_digest
    prefix, digest = contract.content_digest.split("-", 1)
    assert prefix == CAPABILITY_CONTRACT_DIGEST_PREFIX
    assert len(digest) == CAPABILITY_CONTRACT_DIGEST_LENGTH
    # Truncation is to the leading hex characters of the full sha256 digest.
    assert digest == stable_hash(capability_contract_digest_payload(contract))[
        :CAPABILITY_CONTRACT_DIGEST_LENGTH
    ].upper()


def test_digest_is_stable_across_repeated_construction():
    first = _contract()
    for _ in range(5):
        assert _contract().content_digest == first.content_digest


_SUBPROCESS_LOADER = (
    "import importlib.util, sys, types;\n"
    "root = sys.argv[1];\n"
    "def load(name, rel):\n"
    "    spec = importlib.util.spec_from_file_location(name, root + '/' + rel);\n"
    "    module = importlib.util.module_from_spec(spec);\n"
    "    sys.modules[name] = module;\n"
    "    spec.loader.exec_module(module);\n"
    "    return module;\n"
    "pkg = types.ModuleType('investigation_world'); pkg.__path__ = [];\n"
    "sys.modules['investigation_world'] = pkg;\n"
    "foundry = types.ModuleType('investigation_world.foundry'); foundry.__path__ = [];\n"
    "sys.modules['investigation_world.foundry'] = foundry;\n"
    "load('investigation_world.foundry.models', 'src/investigation_world/foundry/models.py');\n"
)


def _digest_in_subprocess(remainder: str) -> str:
    """Compute a digest in a fresh interpreter that never imports the package root.

    The foundry package `__init__` pulls in a native dependency that is unavailable in
    every development environment, so loading the source files directly keeps this
    determinism check honest without masking an import failure.
    """
    result = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_LOADER + remainder, str(_REPO_ROOT)],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(_REPO_ROOT),
    )
    return result.stdout.strip()


def test_digest_is_deterministic_across_separate_processes():
    # A real producer is reconstructed in a fresh interpreter, so no in-process state
    # (insertion order, object identity, caches) can be feeding the digest.
    loader = (
        "families = load('iw_families',\n"
        "             'src/investigation_world/foundry/capability_families.py');\n"
    )
    emitted = "print(families.external_investigation_capability_contract().content_digest);\n"
    in_subprocess = _digest_in_subprocess(loader + emitted)
    assert in_subprocess == external_investigation_capability_contract().content_digest


def test_synthetic_contract_is_deterministic_across_separate_processes():
    expected = _contract().content_digest
    remainder = (
        "import copy;\n"
        "models = sys.modules['investigation_world.foundry.models'];\n"
        f"base = {_BASE_CONTRACT!r};\n"
        "print(models.CapabilityContract(**copy.deepcopy(base)).content_digest);\n"
    )
    assert _digest_in_subprocess(remainder) == expected


@pytest.mark.parametrize(
    "field,alt_value",
    [
        ("capability_id", "contract-identity-fixture-2"),
        ("version", "2"),
        ("objective", "Audit a different lifecycle."),
        ("subcapabilities", ["discover", "verify", "communicate", "abstain"]),
        ("success_conditions", ["claims are supported by verified public evidence"]),
        ("failure_conditions", ["unsupported or laundered claim"]),
        ("hard_invariants", ["no private oracle access", "public evidence is immutable"]),
        ("transfer_targets", ["unseen entities", "adversarial provenance"]),
    ],
)
def test_every_content_bearing_field_changes_the_digest(field, alt_value):
    base = _contract()
    mutated = _contract(**{field: alt_value})
    assert mutated.content_digest != base.content_digest


def test_field_order_does_not_change_the_digest():
    ordered = CapabilityContract(
        capability_id="c",
        version="1",
        objective="o",
        subcapabilities=["a", "b", "c"],
        success_conditions=["s"],
        failure_conditions=["f"],
        hard_invariants=["h"],
        transfer_targets=["t"],
    )
    reordered = CapabilityContract(
        transfer_targets=["t"],
        hard_invariants=["h"],
        failure_conditions=["f"],
        success_conditions=["s"],
        subcapabilities=["a", "b", "c"],
        objective="o",
        version="1",
        capability_id="c",
    )
    assert reordered.content_digest == ordered.content_digest


def test_identical_content_yields_identical_digest():
    assert _contract().content_digest == _contract().content_digest


def test_digest_field_is_excluded_from_its_own_payload():
    contract = _contract()
    assert "content_digest" not in capability_contract_digest_payload(contract)
    # Supplying a digest that came from genuinely different content must fail, proving
    # the digest is not merely echoed back into the payload.
    other = _contract(objective="A genuinely different objective.")
    with pytest.raises(ValueError):
        _contract(content_digest=other.content_digest)


def test_mismatched_explicit_digest_raises_value_error():
    valid = _contract()
    with pytest.raises(ValueError):
        _contract(content_digest=valid.content_digest[:-4] + "0000")


def test_correct_explicit_digest_is_accepted():
    valid = _contract()
    pinned = _contract(content_digest=valid.content_digest)
    assert pinned.content_digest == valid.content_digest


def test_digest_defaults_unset_so_existing_constructions_stay_valid():
    contract = CapabilityContract(capability_id="c", objective="o")
    assert contract.content_digest != ""
    assert _DIGEST_PATTERN.match(contract.content_digest)


@pytest.mark.parametrize("name,contract", _real_contracts())
def test_all_three_real_producers_derive_a_stable_digest(name, contract):
    assert _DIGEST_PATTERN.match(contract.content_digest), (name, contract.content_digest)
    assert contract.content_digest == capability_contract_digest(contract)
    # The producers never pass a digest; it is always derived here.
    rebuilt = contract.model_copy(update={})
    assert rebuilt.content_digest == contract.content_digest


def test_round_trip_serialization_preserves_the_digest():
    contract = _contract()
    payload = contract.model_dump(mode="json")
    assert payload["content_digest"] == contract.content_digest
    restored = CapabilityContract.model_validate_json(contract.model_dump_json())
    assert restored == contract
    assert restored.content_digest == contract.content_digest


def test_restored_contract_resists_content_drift():
    contract = _contract()
    payload = contract.model_dump(mode="json")
    payload["objective"] = "Drifted objective after serialization."
    with pytest.raises(ValueError):
        CapabilityContract.model_validate(payload)


def test_digest_payload_carries_no_private_material():
    payload = capability_contract_digest_payload(_contract())
    assert "content_digest" not in payload
    serialized = repr(payload)
    for forbidden in _FORBIDDEN_PAYLOAD_SUBSTRINGS:
        assert forbidden not in serialized.casefold()


def test_digest_is_a_second_identifier_and_replaces_nothing():
    contract = _contract()
    assert contract.capability_id == _BASE_CONTRACT["capability_id"]
    assert contract.content_digest != contract.capability_id


# --------------------------------------------------------------------------- #
# Run identity: the CLI consequence of the digest.
# --------------------------------------------------------------------------- #
# `export-training-artifacts` feeds `contract.content_digest` into the inputs used to
# derive `TrainingRunManifest.run_id`, which is consumed downstream as a join key. Two
# artifacts built against different capability-contract content must therefore not resolve
# to the same run identity. These tests cover only that G-01 invariant; the CLI command's
# argument handling, adapters, and artifact writing belong to the existing CLI tests.

_RUN_ID_FIXTURE: dict = {
    "capability_id": "run-identity-fixture",
    "version": "1",
    "objective": "Pin an artifact to the capability contract it was built for.",
    "subcapabilities": ["bind", "verify"],
    "success_conditions": ["run identity follows contract content"],
    "failure_conditions": ["run identity ignores contract content"],
    "hard_invariants": ["digest is content-derived"],
    "transfer_targets": ["unseen contract revisions"],
}


def _run_id_contract(**overrides) -> CapabilityContract:
    payload = copy.deepcopy(_RUN_ID_FIXTURE)
    payload.update(overrides)
    return CapabilityContract(**payload)


def test_identical_contract_content_produces_the_same_derived_run_identity():
    """Invariant 1: identical capability-contract content → identical run identity."""
    digest = _run_id_contract().content_digest
    first = _artifact_run_id(TrainerKind.SFT, "dataset-a", "bundle-a", "model-a", digest)
    for _ in range(5):
        again = _run_id_contract().content_digest
        assert _artifact_run_id(TrainerKind.SFT, "dataset-a", "bundle-a", "model-a", again) == first


def test_changed_contract_content_changes_the_derived_run_identity():
    """Invariant 2: changing capability-contract content changes the run identity.

    `objective` is the drifted field because it is unambiguously content-bearing, so the
    precondition is a genuine content change rather than a field the payload ignores.
    """
    original = _run_id_contract().content_digest
    drifted = _run_id_contract(
        objective="A genuinely different capability contract objective."
    ).content_digest
    assert original != drifted
    assert _DIGEST_PATTERN.match(original)
    assert _DIGEST_PATTERN.match(drifted)

    original_run = _artifact_run_id(TrainerKind.SFT, "dataset-a", "bundle-a", "model-a", original)
    drifted_run = _artifact_run_id(TrainerKind.SFT, "dataset-a", "bundle-a", "model-a", drifted)
    assert original_run != drifted_run
    # The trainer prefix and the 12-hex suffix shape survive the change.
    assert original_run.startswith("artifact-sft-")
    assert drifted_run.startswith("artifact-sft-")


@pytest.mark.parametrize("field", ["dataset_id", "bundle_id", "base_model"])
def test_existing_run_id_inputs_retain_their_influence(field):
    """Invariant 3: the digest is additive, not a replacement for the prior inputs."""
    digest = _run_id_contract().content_digest
    baseline = _artifact_run_id(TrainerKind.SFT, "dataset-a", "bundle-a", "model-a", digest)
    altered = _artifact_run_id(
        TrainerKind.SFT,
        "dataset-b" if field == "dataset_id" else "dataset-a",
        "bundle-b" if field == "bundle_id" else "bundle-a",
        "model-b" if field == "base_model" else "model-a",
        digest,
    )
    assert altered != baseline


def test_the_digest_is_not_recoverable_from_the_derived_run_identity():
    """`run_id` keeps 12 hex characters, which cannot carry the 20-character digest.

    Only sensitivity of run identity to contract content is preserved — not the digest
    itself. This pins the documentation wording: the digest is one hash input among several,
    never encoded in or recoverable from the identifier.
    """
    digest = _run_id_contract().content_digest
    run_id = _artifact_run_id(TrainerKind.SFT, "dataset-a", "bundle-a", "model-a", digest)
    assert digest not in run_id
    assert not run_id.endswith(digest)
    assert run_id.rsplit("-", 1)[1] != digest.split("-", 1)[1][:12]
