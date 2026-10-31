"""Use the existing constructed #449 runtime fixture, never private empirical data."""

import runpy
from pathlib import Path

import pytest

from investigation_world.capability_science import EvaluationConditions, EvaluationPopulation
from investigation_world.capability_science.core import CapabilitySpec
from investigation_world.experience import ExperienceReference
from investigation_world.training_qualification import reverified_acquisition_curve
from investigation_world.trajectory import canonical_hash
from investigation_world.trajectory.reverify import REPLAY_EVIDENCE_PRIVATE_KEY


@pytest.fixture
def inputs(tmp_path):
    # Reuse the provider's public deterministic fixture; installed verification copies
    # both owned tests and provider tests, not package source or private datasets.
    fixture = runpy.run_path(
        str(Path(__file__).parents[1] / "experience_foundry" / "test_paired_evaluation.py")
    )["comparison"]
    panel, before, after, kwargs = fixture.__wrapped__(tmp_path)
    case = panel.cases[0]
    conditions = EvaluationConditions(
        environment_id=case.world.environment_id or case.world.world_id,
        environment_revision=case.world.environment_version or case.world.world_version,
        verifier_id=case.verifier.verifier_id,
        verifier_revision=case.verifier.version,
        metric="criterion_score",
        metric_definition_digest=canonical_hash("canonical_reward"),
        distribution_id="CONSTRUCTED-heldout",
        structure_id="fixture",
        interface_id="fixture",
        evidence_references=(
            ExperienceReference(
                reference_id="constructed-conditions",
                reference_type="CONSTRUCTED",
                digest=canonical_hash("conditions"),
            ),
        ),
    )
    bundle = kwargs["training_bundle"]
    train = EvaluationPopulation(
        capability=CapabilitySpec(contract=bundle.capability_contract),
        conditions=conditions,
        split="TRAIN",
        members=tuple(
            ExperienceReference(
                reference_id=row["source_id"],
                reference_type="CONSTRUCTED",
                digest=row["source_digest"],
            )
            for row in bundle.metadata["verified_learning_lineage"]
        ),
        evidence_references=(
            ExperienceReference(
                reference_id=bundle.bundle_id,
                reference_type="CONSTRUCTED",
                digest=canonical_hash(bundle),
            ),
        ),
    )
    return panel, before, after, {**kwargs, "training_population": train, "conditions": conditions}


def test_fresh_reverification_retains_full_regression_and_unknown_attestations(inputs):
    panel, before, after, kwargs = inputs
    record = reverified_acquisition_curve(panel, before, after, **kwargs)
    assert len(record.points[0].outcomes) == len(record.points[1].outcomes) == len(panel.cases) == 1
    assert record.recorded_metric_deltas[0] < 0
    assert record.model_execution_attestation == record.chronology_attestation == "UNKNOWN"
    assert record.capability_gain is None
    assert all(point.observed_at is None for point in record.points)
    assert record.public_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}


def test_missing_fresh_replay_is_preserved_as_unscored_not_original_score(inputs):
    panel, before, after, kwargs = inputs
    trajectory = after[0].trajectory
    metadata = dict(trajectory.private_metadata)
    metadata.pop(REPLAY_EVIDENCE_PRIVATE_KEY)
    trajectory = trajectory.model_copy(update={"private_metadata": metadata})
    changed = (after[0].model_copy(update={"trajectory": trajectory}),)
    record = reverified_acquisition_curve(panel, before, changed, **kwargs)
    assert record.points[1].outcomes[0].value is None
    assert record.points[1].outcomes[0].unavailable_reason
    assert record.recorded_metric_deltas == (None,)


def test_dropped_case_or_wrong_verifier_declaration_is_rejected(inputs):
    panel, before, after, kwargs = inputs
    with pytest.raises(ValueError):
        reverified_acquisition_curve(panel, (), after, **kwargs)
    condition = kwargs["conditions"]
    payload = condition.model_dump(mode="python")
    payload.update(record_id="", verifier_revision="different-verifier")
    kwargs["conditions"] = EvaluationConditions.model_validate(payload)
    with pytest.raises(ValueError, match="exact panel"):
        reverified_acquisition_curve(panel, before, after, **kwargs)


def test_adapter_rejects_substituted_capability_despite_same_training_sources(inputs):
    from investigation_world.foundry.models import CapabilityContract

    panel, before, after, kwargs = inputs
    payload = kwargs["training_population"].model_dump(mode="python")
    payload.update(
        record_id="",
        capability=CapabilitySpec(
            contract=CapabilityContract(capability_id="different-capability", objective="unrelated")
        ),
    )
    kwargs["training_population"] = EvaluationPopulation.model_validate(payload)
    with pytest.raises(ValueError, match="capability"):
        reverified_acquisition_curve(panel, before, after, **kwargs)
