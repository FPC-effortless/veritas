"""Actual native execution and merged adapter, not a constructed canonical-object substitute."""

import hashlib

from test_admission import recorded
from test_bundle_bridge import recipe

from investigation_world.experience_foundry.admission import authorized_registry
from investigation_world.experience_foundry.bundle_bridge import compile_verified_bundle
from investigation_world.experience_foundry.external_receipt import (
    ExternalRunReceipt,
    validate_external_receipt,
)
from investigation_world.foundry.training_product import TrainingRunManifest, TrainingRunResult
from investigation_world.trajectory import canonical_hash


def test_public_runtime_bundle_constructed_receipt_roundtrip(tmp_path):
    source = recorded(tmp_path / "native")
    assert source.experience.trajectory.provenance[0].adapter_id == (
        "veritas.operational-runtime-to-trajectory-v2"
    )
    output = compile_verified_bundle([source], recipe(source), registry=authorized_registry())
    inputs = tmp_path / "trainer-input.jsonl"
    checkpoint = tmp_path / "constructed-checkpoint.bin"
    inputs.write_bytes(output.trainer_bytes)
    # Constructed bytes exercise receipt plumbing ONLY, no actual training/model claim.
    checkpoint.write_bytes(b"constructed fixture, not a trained checkpoint")
    manifest = TrainingRunManifest(
        run_id="constructed-plumbing",
        bundle_id=output.bundle.bundle_id,
        trainer="sft",
        base_model="constructed-base",
        trainer_version="fixture-v1",
        seed=19,
    )
    receipt = ExternalRunReceipt(
        result=TrainingRunResult(manifest=manifest, artifact_ref=str(checkpoint)),
        status="completed",
        base_model_revision="fixture-revision-v1",
        bundle_digest=canonical_hash(output.bundle.model_dump(mode="python")),
        input_digest=hashlib.sha256(output.trainer_bytes).hexdigest(),
        checkpoint_digest=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
    )
    validation = validate_external_receipt(
        receipt,
        bundle=output.bundle,
        expected_manifest=manifest,
        expected_base_model_revision="fixture-revision-v1",
        expected_input_bytes=output.trainer_bytes,
        input_path=inputs,
        checkpoint_path=checkpoint,
    )
    assert validation.status == "byte_integrity_checked"
    assert validation.independent_execution_attestation == "unknown"
    assert validation.training_validated is False
    assert validation.elapsed_s is None
    assert output.provenance[0]["experience_id"] == source.experience.experience_id
