"""Consume #449's complete frozen-panel replay without upgrading its proof boundary."""

from __future__ import annotations

from investigation_world.capability_science import (
    AcquisitionCurve,
    CaseOutcome,
    EvaluationConditions,
    EvaluationPoint,
    EvaluationPopulation,
    TrainingIntervention,
)
from investigation_world.experience import ExperienceReference
from investigation_world.experience_foundry.external_receipt import ReceiptValidation
from investigation_world.experience_foundry.paired_evaluation import (
    FrozenPanel,
    PanelAttempt,
    _training_membership,
    compare_frozen_panel,
)
from investigation_world.foundry.models import capability_contract_digest_payload
from investigation_world.foundry.training_product import TrainingBundle, TrainingRunManifest
from investigation_world.trajectory import VisibilityClass, canonical_hash
from investigation_world.trajectory.reverify import AuthorizedVerifierRegistry


def reverified_acquisition_curve(
    panel: FrozenPanel,
    baseline: tuple[PanelAttempt, ...],
    checkpoint: tuple[PanelAttempt, ...],
    *,
    receipt: ReceiptValidation,
    expected_manifest: TrainingRunManifest,
    training_bundle: TrainingBundle,
    registry: AuthorizedVerifierRegistry,
    training_population: EvaluationPopulation,
    conditions: EvaluationConditions,
) -> AcquisitionCurve:
    """Reverify every attempt afresh, then preserve complete, private, declared records.

    The caller's conditions specify what the reward is claimed to measure, not an
    attestation of capability validity. This adapter supports one exact environment
    and verifier identity per panel. Mixed environments need separate curves.
    No timestamps are invented; byte integrity is not execution or chronology proof.
    """
    training_population = training_population.checked()
    conditions = conditions.checked()
    panel = FrozenPanel.model_validate(panel.model_dump(mode="python"))
    if len(panel.cases) > 512:
        raise ValueError("bounded panel size exceeded")
    if conditions.metric != "criterion_score":
        raise ValueError("canonical reward requires declared criterion_score semantics")
    for case in panel.cases:
        if (
            conditions.environment_id,
            conditions.environment_revision,
            conditions.verifier_id,
            conditions.verifier_revision,
        ) != (
            case.world.environment_id or case.world.world_id,
            case.world.environment_version or case.world.world_version,
            case.verifier.verifier_id,
            case.verifier.version,
        ):
            raise ValueError("declared conditions do not bind exact panel environment/verifier")
    if training_population.capability.contract_digest != canonical_hash(
        capability_contract_digest_payload(training_bundle.capability_contract)
    ):
        raise ValueError("training population capability differs from exact bundle")
    source_conditions = training_population.conditions
    for field in (
        "environment_id",
        "environment_revision",
        "verifier_id",
        "verifier_revision",
        "metric",
        "metric_definition_digest",
    ):
        if getattr(source_conditions, field) != getattr(conditions, field):
            raise ValueError("training and evaluation measurement semantics differ")
    if training_population.split != "TRAIN":
        raise ValueError("training population must be TRAIN")
    _training_membership(training_bundle)
    mapping = {
        row["source_id"]: row["source_digest"]
        for row in training_bundle.metadata["verified_learning_lineage"]
    }
    if mapping != {member.reference_id: member.digest for member in training_population.members}:
        raise ValueError("training population must cover exact bundle lineage")
    comparison = compare_frozen_panel(
        panel,
        baseline,
        checkpoint,
        receipt=receipt,
        expected_manifest=expected_manifest,
        training_bundle=training_bundle,
        registry=registry,
    )

    def reference(identity: str, value: object) -> ExperienceReference:
        return ExperienceReference(
            reference_id=identity,
            reference_type="authorized_offline_reverification_not_execution_attestation",
            digest=canonical_hash(value),
            visibility=VisibilityClass.EVALUATOR_PRIVATE,
        )

    protocol_ref = reference(panel.panel_id, panel)
    population = EvaluationPopulation(
        capability=training_population.capability,
        conditions=conditions,
        split="HELD_OUT",
        members=tuple(
            ExperienceReference(
                reference_id=case.source_id,
                reference_type="frozen_panel_source",
                digest=case.source_digest,
                visibility=VisibilityClass.EVALUATOR_PRIVATE,
            )
            for case in panel.cases
        ),
        evidence_references=(protocol_ref,),
        visibility=VisibilityClass.EVALUATOR_PRIVATE,
    )
    cases = {case.case_id: case for case in panel.cases}
    points = []
    for index, phase in enumerate(("baseline", "checkpoint")):
        rows = []
        for pair in comparison["pairs"]:
            result, case = pair[phase], cases[pair["case_id"]]
            rows.append(
                CaseOutcome(
                    member_id=case.source_id,
                    member_digest=case.source_digest,
                    value=result["reward"],
                    evidence_references=(
                        reference(result["record_id"] or "unscored-record", result),
                    ),
                    unavailable_reason=result["reason_code"] or "reverification_unavailable"
                    if result["reward"] is None
                    else None,
                    visibility=VisibilityClass.EVALUATOR_PRIVATE,
                )
            )
        points.append(
            EvaluationPoint(
                population=population,
                model_id=expected_manifest.base_model,
                model_revision=receipt.base_model_revision
                if index == 0
                else receipt.checkpoint_digest,
                sequence_index=index,
                outcomes=tuple(rows),
                execution_provenance="DECLARED",
                evidence_references=(protocol_ref, reference(expected_manifest.run_id, comparison)),
                visibility=VisibilityClass.EVALUATOR_PRIVATE,
            )
        )
    before, after = points
    intervention = TrainingIntervention(
        before_point_id=before.record_id,
        after_point_id=after.record_id,
        training_population=training_population,
        trainer_id=expected_manifest.trainer.value,
        trainer_revision=expected_manifest.trainer_version,
        training_bundle_digest=canonical_hash(training_bundle),
        training_configuration_digest=canonical_hash(expected_manifest.parameters),
        execution_provenance="DECLARED",
        evidence_references=(reference(expected_manifest.run_id, receipt),),
        visibility=VisibilityClass.EVALUATOR_PRIVATE,
    )
    return AcquisitionCurve(
        points=(before, after),
        interventions=(intervention,),
        visibility=VisibilityClass.EVALUATOR_PRIVATE,
    )
