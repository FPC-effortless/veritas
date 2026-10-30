"""Constructed local files test interchange integrity, not a training experiment."""

from __future__ import annotations

import hashlib

import pytest

from investigation_world.experience_foundry.external_receipt import (
    ExternalRunReceipt,
    validate_external_receipt,
)
from investigation_world.foundry.models import CapabilityContract
from investigation_world.foundry.training_product import (
    TrainerKind,
    TrainingBundle,
    TrainingRecipe,
    TrainingRunManifest,
    TrainingRunResult,
)
from investigation_world.trajectory import canonical_hash


@pytest.fixture
def case(tmp_path):
    contract = CapabilityContract(capability_id="constructed", objective="plumbing only")
    recipe = TrainingRecipe(
        recipe_id="fixture", trainer=TrainerKind.SFT, capability_contract_id=contract.capability_id
    )
    bundle = TrainingBundle(bundle_id="fixture-bundle", recipe=recipe, capability_contract=contract)
    manifest = TrainingRunManifest(
        run_id="constructed-run",
        bundle_id=bundle.bundle_id,
        trainer=TrainerKind.SFT,
        base_model="fixture-model",
        trainer_version="fixture-v1",
        seed=17,
        parameters={"frozen_panel_id": "panel-fixture"},
    )
    inputs = b'{"prompt":"constructed","target":"example"}\n'
    input_path, checkpoint_path = tmp_path / "input.jsonl", tmp_path / "checkpoint.bin"
    input_path.write_bytes(inputs)
    checkpoint_path.write_bytes(b"constructed checkpoint bytes, NOT a model")
    receipt = ExternalRunReceipt(
        result=TrainingRunResult(manifest=manifest, artifact_ref=str(checkpoint_path)),
        status="completed",
        base_model_revision="fixture-revision-1",
        bundle_digest=canonical_hash(bundle.model_dump(mode="json")),
        input_digest=hashlib.sha256(inputs).hexdigest(),
        checkpoint_digest=hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
    )
    kwargs = dict(
        bundle=bundle,
        expected_manifest=manifest,
        expected_base_model_revision="fixture-revision-1",
        expected_input_bytes=inputs,
        input_path=input_path,
        checkpoint_path=checkpoint_path,
    )
    return receipt, kwargs


def test_constructed_receipt_checks_bytes_not_training_or_attestation(case):
    receipt, kwargs = case
    before = receipt.model_dump(mode="json")
    result = validate_external_receipt(receipt, **kwargs)
    assert result.status == "byte_integrity_checked"
    assert result.checkpoint_digest == receipt.checkpoint_digest
    expected_digest = canonical_hash(kwargs["expected_manifest"].model_dump(mode="json"))
    assert result.manifest_digest == expected_digest
    assert result.independent_execution_attestation == "unknown"
    assert result.training_validated is False
    assert result.elapsed_s is None and result.cost is None and result.peak_memory_bytes is None
    assert receipt.model_dump(mode="json") == before
    assert result == validate_external_receipt(receipt, **kwargs)


@pytest.mark.parametrize("status", ["failed", "not_run", "unknown", "incomplete"])
def test_noncompleted_receipts_reject(case, status):
    receipt, kwargs = case
    with pytest.raises(ValueError, match="RUN_NOT_COMPLETED"):
        validate_external_receipt(receipt.model_copy(update={"status": status}), **kwargs)


@pytest.mark.parametrize("field", ["input_path", "checkpoint_path"])
def test_actual_file_tampering_and_missing_files_reject(case, field):
    receipt, kwargs = case
    kwargs[field].write_bytes(b"substituted")
    with pytest.raises(ValueError, match="BYTES_MISMATCH"):
        validate_external_receipt(receipt, **kwargs)
    kwargs[field].unlink()
    with pytest.raises(ValueError, match="ARTIFACT_UNAVAILABLE"):
        validate_external_receipt(receipt, **kwargs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("seed", 99),
        ("trainer_version", "other"),
        ("base_model", "other"),
        ("run_id", "other"),
        ("parameters", {"frozen_panel_id": "substituted"}),
    ],
)
def test_manifest_identity_config_and_seed_cannot_self_authorize(case, field, value):
    receipt, kwargs = case
    changed = receipt.result.manifest.model_copy(update={field: value})
    result = receipt.result.model_copy(update={"manifest": changed})
    with pytest.raises(ValueError, match="MANIFEST_MISMATCH"):
        validate_external_receipt(receipt.model_copy(update={"result": result}), **kwargs)


def test_exact_bundle_and_recipe_bytes_not_bundle_id_alone(case):
    receipt, kwargs = case
    kwargs["bundle"].recipe.version = "changed-with-same-id"
    with pytest.raises(ValueError, match="BUNDLE_MISMATCH"):
        validate_external_receipt(receipt, **kwargs)


@pytest.mark.parametrize("field", ["elapsed_s", "cost", "peak_memory_bytes"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_resources_reject_even_model_copy(case, field, value):
    receipt, kwargs = case
    with pytest.raises(ValueError):
        validate_external_receipt(receipt.model_copy(update={field: value}), **kwargs)


def test_missing_checkpoint_ref_and_false_completion_reject(case):
    receipt, kwargs = case
    for result in [
        receipt.result.model_copy(update={"artifact_ref": None}),
        receipt.result.model_copy(update={"metadata": {"status": "failed"}}),
        receipt.result.model_copy(update={"post_training_evaluation_required": False}),
    ]:
        with pytest.raises(ValueError):
            validate_external_receipt(receipt.model_copy(update={"result": result}), **kwargs)


def test_nonfinite_metrics_reject(case):
    receipt, kwargs = case
    result = receipt.result.model_copy(update={"metrics": {"loss": float("nan")}})
    with pytest.raises(ValueError, match="NONFINITE"):
        validate_external_receipt(receipt.model_copy(update={"result": result}), **kwargs)


def test_base_revision_and_expected_input_are_independent(case):
    receipt, kwargs = case
    kwargs["expected_base_model_revision"] = "other-revision"
    with pytest.raises(ValueError, match="BASE_REVISION_MISMATCH"):
        validate_external_receipt(receipt, **kwargs)
    kwargs["expected_base_model_revision"] = receipt.base_model_revision
    kwargs["expected_input_bytes"] = b"another input"
    with pytest.raises(ValueError, match="INPUT_BYTES_MISMATCH"):
        validate_external_receipt(receipt, **kwargs)


def test_symlinks_directories_empty_and_oversized_files_reject(case, tmp_path):
    receipt, kwargs = case
    original = kwargs["checkpoint_path"]
    link = tmp_path / "link"
    link.symlink_to(original)
    with pytest.raises(ValueError, match="ARTIFACT_UNAVAILABLE"):
        validate_external_receipt(receipt, **{**kwargs, "checkpoint_path": link})
    with pytest.raises(ValueError):
        validate_external_receipt(receipt, **{**kwargs, "checkpoint_path": tmp_path})
    with pytest.raises(ValueError, match="ARTIFACT_SIZE"):
        validate_external_receipt(receipt, **kwargs, max_artifact_bytes=1)
    original.write_bytes(b"")
    with pytest.raises(ValueError, match="ARTIFACT_SIZE"):
        validate_external_receipt(receipt, **kwargs)


def test_explicit_seed_and_trainer_identity_required(case):
    receipt, kwargs = case
    manifest = TrainingRunManifest(
        run_id="constructed-run",
        bundle_id="fixture-bundle",
        trainer=TrainerKind.SFT,
        base_model="fixture-model",
    )
    with pytest.raises(ValueError, match="MANIFEST_IDENTITY_INCOMPLETE"):
        validate_external_receipt(receipt, **{**kwargs, "expected_manifest": manifest})


@pytest.mark.parametrize("field", ["bundle_digest", "input_digest", "checkpoint_digest"])
def test_declared_digest_substitution_rejects(case, field):
    receipt, kwargs = case
    with pytest.raises(ValueError, match="MISMATCH"):
        validate_external_receipt(receipt.model_copy(update={field: "0" * 64}), **kwargs)


def test_known_resources_preserved_but_not_attested(case):
    receipt, kwargs = case
    receipt = receipt.model_copy(update={"elapsed_s": 1.5, "cost": 0.25, "peak_memory_bytes": 42})
    result = validate_external_receipt(receipt, **kwargs)
    assert (result.elapsed_s, result.cost, result.peak_memory_bytes) == (1.5, 0.25, 42)
    assert result.independent_execution_attestation == "unknown"
    result.expected_manifest.parameters["changed"] = True
    assert "changed" not in kwargs["expected_manifest"].parameters


@pytest.mark.parametrize("revision", ["", "main", "latest", "unknown"])
def test_mutable_or_missing_base_revision_reject(case, revision):
    receipt, kwargs = case
    with pytest.raises(ValueError, match="BASE_REVISION_MISMATCH"):
        validate_external_receipt(receipt, **{**kwargs, "expected_base_model_revision": revision})


def test_receipt_never_follows_its_artifact_reference(case):
    receipt, kwargs = case
    result = receipt.result.model_copy(
        update={"artifact_ref": "https://invalid.example/checkpoint"}
    )
    with pytest.raises(ValueError, match="CHECKPOINT_REFERENCE_MISMATCH"):
        validate_external_receipt(receipt.model_copy(update={"result": result}), **kwargs)


def test_nonfinite_config_rejects(case):
    receipt, kwargs = case
    kwargs["expected_manifest"].parameters["learning_rate"] = float("inf")
    with pytest.raises(ValueError):
        validate_external_receipt(receipt, **kwargs)
