"""Public deterministic recorder integration; all training/model records are CONSTRUCTED."""

import runpy
from dataclasses import replace
from pathlib import Path

import pytest

from investigation_world.capability_science import EvaluationPopulation, RetentionLink
from investigation_world.capability_science.core import CapabilitySpec
from investigation_world.experience import ExperienceReference
from investigation_world.experience_foundry.admission import authorized_registry
from investigation_world.experience_foundry.bundle_bridge import compile_verified_bundle
from investigation_world.experience_foundry.derivation import compile_learning_assets
from investigation_world.experience_selection import select_experiences
from investigation_world.foundry.training_product import (
    TrainerKind,
    TrainingRecipe,
    TrainingRunManifest,
)
from investigation_world.learning_efficiency import EfficiencyStudy, assess_efficiency
from investigation_world.training_qualification import (
    TrainingEvidence,
    TrainingPolicy,
    TrainingReplicate,
    assess_training,
)
from investigation_world.trajectory import canonical_hash

HELPERS = runpy.run_path(
    str(Path(__file__).parents[1] / "training_qualification" / "test_training_qualification.py")
)
SELECT = runpy.run_path(
    str(Path(__file__).parents[1] / "experience_selection" / "test_selection_policy.py")
)
ref, rebuild = HELPERS["ref"], HELPERS["rebuild"]


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    success, duplicate, longer, gaps = SELECT["pool"].__wrapped__(tmp_path_factory)
    candidates = (success, duplicate, longer, gaps[0][1], success)
    selection = select_experiences(candidates, gap_sources=gaps)
    selected_ids = {d.experience_id for d in selection.decisions if d.reason == "selected"}
    sources = tuple(
        {
            s.experience.experience_id: s
            for s in candidates
            if s.experience.experience_id in selected_ids
        }.values()
    )
    capability = CapabilitySpec(contract=sources[0].capability)
    recipe = TrainingRecipe(
        recipe_id="CONSTRUCTED",
        trainer=TrainerKind.SFT,
        capability_contract_id=capability.contract.capability_id,
    )
    bundle = compile_verified_bundle(list(sources), recipe, registry=authorized_registry()).bundle
    template = HELPERS["evidence"]()
    train = EvaluationPopulation(
        capability=capability,
        split="TRAIN",
        conditions=HELPERS["population"]("train").conditions,
        members=tuple(
            ExperienceReference(
                reference_id=row["source_id"],
                reference_type="CONSTRUCTED",
                digest=row["source_digest"],
            )
            for row in bundle.metadata["verified_learning_lineage"]
        ),
        evidence_references=(ref("CONSTRUCTED train population"),),
    )
    heldout = HELPERS["population"]("heldout", capability=capability)
    replicas = tuple(
        TrainingReplicate(
            seed=seed,
            manifest=TrainingRunManifest(
                run_id=f"CONSTRUCTED-{seed}",
                bundle_id=bundle.bundle_id,
                trainer=TrainerKind.SFT,
                base_model="model",
                trainer_version="v1",
                seed=seed,
            ),
            train=HELPERS["curve"](train, train, bundle, seed, before=(0.2,), after=(0.6,)),
            heldout=HELPERS["curve"](heldout, train, bundle, seed),
        )
        for seed in (1, 2)
    )
    evidence = TrainingEvidence(
        capability=capability,
        environment_identity=template.environment_identity,
        verifier_identity=template.verifier_identity,
        bundle=bundle,
        configuration_digest=canonical_hash({}),
        expected_seeds=(1, 2),
        replicates=replicas,
        provenance="CONSTRUCTED",
        evidence_references=(ref("CONSTRUCTED training study"),),
    )
    derivation = compile_learning_assets(sources)
    study = EfficiencyStudy(
        experiment_id="CONSTRUCTED public pipeline",
        training=assess_training(evidence, policy=TrainingPolicy(minimum_population=1)),
        selection=selection,
        derivation=derivation,
        evidence_references=(ref("CONSTRUCTED pipeline"),),
        panel_designations={heldout.record_id: "iid"},
        retention=(
            RetentionLink(
                acquired=replicas[0].heldout.points[0],
                later=replicas[0].heldout.points[1],
                intervention_references=(ref("CONSTRUCTED retention"),),
            ),
        ),
    )
    inputs = dict(
        selection_sources=candidates,
        gap_sources=gaps,
        expected_selection_policy=selection.policy,
        derivation_sources=sources,
        expected_transform_policy=derivation.policy,
    )
    return study, inputs


def test_full_rejected_generation_and_shared_native_execution_cost_remain(pipeline):
    study, inputs = pipeline
    result = assess_efficiency(study, **inputs)
    assert result.counts.raw_candidates == 5
    assert result.counts.selected_experiences == 1
    assert result.counts.rejected_experiences == 4
    assert result.counts.training_examples == 1
    assert result.counts.selected_not_in_training == 0
    assert result.counts.derived_candidates == len(study.derivation.assets)
    assert result.counts.derivation_rejections == len(study.derivation.rejections)
    # Independent arithmetic keyed by original trajectory + companion, not provider totals.
    executions = list(inputs["selection_sources"])
    for receipt, _ in inputs["gap_sources"]:
        executions.extend(
            x.recorded()
            for x in (
                receipt.source,
                receipt.baseline,
                receipt.alternative,
                receipt.repeated,
            )
        )
    costs = {
        (s.experience.trajectory.trajectory_id, s.companion.trace_id): s.companion.total_cost
        for s in executions
    }
    assert result.counts.native_runtime_budget_cost == pytest.approx(sum(costs.values()))
    assert result.counts.native_runtime_budget_cost > sum(
        s.companion.total_cost for s in inputs["derivation_sources"]
    )
    native = next(d for d in result.denominators if d.metric == "native_runtime_budget")
    assert native.ratio == pytest.approx(0.4 / sum(costs.values()))
    assert native.unit == "native_runtime_budget_units_not_compute_or_money"
    assert result.evaluation_coverage["iid"] == "DECLARED"
    assert result.evaluation_coverage["retention"] == "RECORDED"
    assert result.evaluation_coverage["adversarial"] == "UNKNOWN"
    assert result.resource_availability["monetary_cost"] == "UNKNOWN"


def test_saved_selection_requires_actual_full_pool_and_expected_policy(pipeline):
    study, inputs = pipeline
    with pytest.raises(ValueError, match="actual sources"):
        assess_efficiency(study)
    with pytest.raises(ValueError, match="actual inputs"):
        assess_efficiency(study, **{**inputs, "selection_sources": inputs["derivation_sources"]})
    with pytest.raises(ValueError, match="expected policy"):
        assess_efficiency(
            study,
            **{**inputs, "expected_selection_policy": rebuild(study.selection.policy, seed=19)},
        )


def test_source_and_derivation_tampering_are_not_report_authority(pipeline):
    study, inputs = pipeline
    first = inputs["selection_sources"][0]
    forged = replace(first, companion=first.companion.model_copy(update={"total_cost": 0.0}))
    with pytest.raises(ValueError):
        assess_efficiency(
            study, **{**inputs, "selection_sources": (forged, *inputs["selection_sources"][1:])}
        )
    fake = study.derivation.model_copy(deep=True)
    fake.assets[0].material["forged"] = "PRIVATE-SENTINEL"
    with pytest.raises(ValueError):
        assess_efficiency(study.model_copy(update={"record_id": "", "derivation": fake}), **inputs)


def test_foreign_training_lineage_and_arbitrary_panel_designation_reject(pipeline):
    study, _ = pipeline
    raw = study.model_dump(mode="python")
    raw["record_id"] = ""
    raw["training"]["record_id"] = ""
    raw["training"]["evidence"]["record_id"] = ""
    raw["training"]["evidence"]["bundle"]["metadata"]["verified_learning_lineage"][0][
        "experience_id"
    ] = "not-selected"
    with pytest.raises(ValueError):
        EfficiencyStudy.model_validate(raw)
    with pytest.raises(ValueError, match="population"):
        rebuild(study, panel_designations={"arbitrary-panel": "adversarial"})
    with pytest.raises(ValueError, match="population"):
        rebuild(study, panel_designations={next(iter(study.panel_designations)): "adversarial"})


def test_internally_consistent_forged_bundle_is_rejected_by_fresh_recompilation(pipeline):
    study, inputs = pipeline
    evidence = study.training.evidence
    bundle = evidence.bundle.model_copy(deep=True)
    bundle.train_examples[0].payload["invented-training-target"] = "CONSTRUCTED poison"
    replicas = []
    for rep in evidence.replicates:
        changed = {}
        for role in ("train", "heldout"):
            curve = getattr(rep, role)
            step = rebuild(curve.interventions[0], training_bundle_digest=canonical_hash(bundle))
            changed[role] = rebuild(curve, interventions=(step,))
        replicas.append(rebuild(rep, **changed))
    changed_evidence = rebuild(evidence, bundle=bundle, replicates=tuple(replicas))
    changed_training = assess_training(changed_evidence, policy=study.training.policy)
    forged = rebuild(study, training=changed_training)
    with pytest.raises(ValueError, match="freshly admitted"):
        assess_efficiency(forged, **inputs)


def test_removed_public_artifacts_invalidate_cached_accounting(tmp_path):
    import shutil

    source, _ = SELECT["recorded"](tmp_path / "recording")
    selection = select_experiences((source,))
    evidence = rebuild(HELPERS["evidence"](), bundle=None)
    study = EfficiencyStudy(
        experiment_id="CONSTRUCTED missing artifacts",
        training=assess_training(evidence),
        selection=selection,
        evidence_references=(ref("CONSTRUCTED stale"),),
    )
    inputs = dict(selection_sources=(source,), expected_selection_policy=selection.policy)
    assess_efficiency(study, **inputs)
    shutil.rmtree(tmp_path / "recording")
    with pytest.raises(ValueError, match="actual inputs"):
        assess_efficiency(study, **inputs)


def test_existing_byte_receipt_identity_is_retained_without_inventing_money_or_gpu(tmp_path):
    from investigation_world.learning_efficiency import RunReceipt
    from investigation_world.qualification.maturity import EnvironmentIdentity, VerifierIdentity
    from investigation_world.training_qualification import reverified_acquisition_curve

    helper = runpy.run_path(
        str(Path(__file__).parents[1] / "training_qualification" / "test_reverified_panel.py")
    )
    panel, before, after, kwargs = helper["inputs"].__wrapped__(tmp_path)
    curve = reverified_acquisition_curve(panel, before, after, **kwargs)
    conditions = kwargs["conditions"]
    receipt = kwargs["receipt"].model_copy(update={"cost": 45.0, "elapsed_s": 123.0})
    manifest = kwargs["expected_manifest"]
    evidence = TrainingEvidence(
        capability=kwargs["training_population"].capability,
        environment_identity=EnvironmentIdentity(
            environment_id=conditions.environment_id,
            environment_version=conditions.environment_revision,
            content_sha256=canonical_hash(panel.cases[0].world),
        ),
        verifier_identity=VerifierIdentity(
            verifier_id=conditions.verifier_id,
            verifier_version=conditions.verifier_revision,
            content_sha256=canonical_hash(panel.cases[0].verifier),
        ),
        bundle=kwargs["training_bundle"],
        configuration_digest=canonical_hash(manifest.parameters),
        expected_seeds=(manifest.seed,),
        replicates=(TrainingReplicate(seed=manifest.seed, manifest=manifest, heldout=curve),),
        provenance="CONSTRUCTED",
        evidence_references=(ref("CONSTRUCTED byte receipt"),),
    )
    binding = RunReceipt(seed=manifest.seed, receipt=receipt)
    study = EfficiencyStudy(
        experiment_id="CONSTRUCTED byte binding",
        training=assess_training(evidence),
        receipts=(binding,),
        evidence_references=(ref("CONSTRUCTED binding"),),
    )
    report = assess_efficiency(study)
    assert report.study.receipts[0].receipt.checkpoint_digest == after[0].checkpoint_identity
    assert report.resource_availability["monetary_cost"] == "UNKNOWN"
    assert report.resource_availability["gpu_hours"] == "UNKNOWN"
    assert report.verified_capability_efficiency == "UNKNOWN"
    wrong = rebuild(binding, receipt=receipt.model_copy(update={"run_id": "wrong-run"}))
    with pytest.raises(ValueError, match="receipt"):
        rebuild(study, receipts=(wrong,))
    with pytest.raises(ValueError, match="digest"):
        rebuild(binding, receipt=receipt.model_copy(update={"input_digest": "not-a-sha256"}))
    for field, value in (
        ("manifest_digest", "f" * 64),
        ("bundle_digest", "f" * 64),
        ("base_model_revision", "wrong-base"),
        ("checkpoint_digest", "f" * 64),
    ):
        wrong = rebuild(binding, receipt=receipt.model_copy(update={field: value}))
        with pytest.raises(ValueError, match="receipt"):
            rebuild(study, receipts=(wrong,))
    with pytest.raises(ValueError, match="receipt"):
        rebuild(study, receipts=(rebuild(binding, seed=19),))
    for field, value in (("cost", -1.0), ("elapsed_s", -1.0), ("peak_memory_bytes", -1)):
        with pytest.raises(ValueError, match="receipt"):
            rebuild(binding, receipt=receipt.model_copy(update={field: value}))


def test_within_family_transfer_is_not_relabelled_structural_ood():
    evidence = HELPERS["evidence"]()
    replicas = []
    for rep in evidence.replicates:
        population = HELPERS["population"]("other-distribution")
        transfer = HELPERS["curve"](
            population, rep.train.points[0].population, evidence.bundle, rep.seed
        )
        replicas.append(rebuild(rep, transfer=(transfer,)))
    evidence = rebuild(evidence, replicates=tuple(replicas))
    study = EfficiencyStudy(
        experiment_id="CONSTRUCTED within-family",
        training=assess_training(evidence),
        evidence_references=(ref("CONSTRUCTED within-family"),),
    )
    result = assess_efficiency(study)
    assert result.evaluation_coverage["ood"] == "WITHIN_FAMILY_ONLY"
