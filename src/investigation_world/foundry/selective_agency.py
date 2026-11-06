from __future__ import annotations

from collections.abc import Iterable

from investigation_world.benchmark.selective_agency import (
    SelectiveAgencyCase,
    SelectiveAgencyTaskClass,
)
from investigation_world.foundry.models import (
    DifficultyVector,
    DistributionSplit,
    FoundryTaskMetadata,
)


_CLASS_CAPABILITIES: dict[SelectiveAgencyTaskClass, list[str]] = {
    SelectiveAgencyTaskClass.ACTION_WARRANTED: [
        "state_awareness",
        "action_boundary",
        "consequence_reasoning",
        "execution_judgment",
    ],
    SelectiveAgencyTaskClass.FALSE_PREMISE: [
        "premise_validation",
        "epistemic_calibration",
        "correction",
    ],
    SelectiveAgencyTaskClass.IMPOSSIBLE: [
        "feasibility_judgment",
        "epistemic_calibration",
        "decline_or_reframe",
    ],
    SelectiveAgencyTaskClass.CONTRADICTORY: [
        "constraint_reasoning",
        "feasibility_judgment",
        "clarification",
    ],
    SelectiveAgencyTaskClass.UNDERSPECIFIED: [
        "ambiguity_detection",
        "clarification",
        "action_boundary",
    ],
    SelectiveAgencyTaskClass.REDUNDANT: [
        "state_awareness",
        "no_op_judgment",
        "resource_proportionality",
    ],
    SelectiveAgencyTaskClass.GOAL_DEFEATING: [
        "goal_instruction_alignment",
        "consequence_reasoning",
        "reframing",
    ],
    SelectiveAgencyTaskClass.ABSURD_BUT_VALID: [
        "pragmatic_judgment",
        "engagement",
        "anti_overrefusal",
    ],
    SelectiveAgencyTaskClass.TRIVIAL: [
        "resource_proportionality",
        "direct_answering",
        "anti_overthinking",
    ],
    SelectiveAgencyTaskClass.UNANSWERABLE: [
        "epistemic_calibration",
        "abstention",
        "evidence_sufficiency",
    ],
    SelectiveAgencyTaskClass.PREMATURE_ACTION: [
        "ambiguity_detection",
        "action_boundary",
        "consequence_reasoning",
    ],
    SelectiveAgencyTaskClass.EXCESSIVE_SOLUTION: [
        "resource_proportionality",
        "solution_minimality",
        "goal_instruction_alignment",
    ],
    SelectiveAgencyTaskClass.NO_OP: [
        "state_awareness",
        "no_op_judgment",
        "action_boundary",
    ],
}


def infer_selective_agency_difficulty(case: SelectiveAgencyCase) -> DifficultyVector:
    task = case.public
    oracle = case.oracle
    visible_items = len(task.visible_state)
    action_count = len(task.available_actions)
    adversarial_classes = {
        SelectiveAgencyTaskClass.FALSE_PREMISE,
        SelectiveAgencyTaskClass.GOAL_DEFEATING,
        SelectiveAgencyTaskClass.ABSURD_BUT_VALID,
        SelectiveAgencyTaskClass.EXCESSIVE_SOLUTION,
    }
    ambiguity_classes = {
        SelectiveAgencyTaskClass.UNDERSPECIFIED,
        SelectiveAgencyTaskClass.PREMATURE_ACTION,
        SelectiveAgencyTaskClass.CONTRADICTORY,
    }
    return DifficultyVector(
        entities=max(1, visible_items),
        tools=action_count,
        steps=2 if oracle.requires_clarification else 1,
        distractors=max(0, visible_items - 1),
        missing_probability=0.5 if task.task_class in ambiguity_classes else 0.0,
        conflict_probability=0.5
        if task.task_class == SelectiveAgencyTaskClass.CONTRADICTORY
        else 0.0,
        dependency_depth=max(1, visible_items),
        budget_ratio=0.5
        if task.task_class == SelectiveAgencyTaskClass.EXCESSIVE_SOLUTION
        else 1.0,
        stochasticity=0.0,
        adversarial_pressure=0.75 if task.task_class in adversarial_classes else 0.25,
    )


def selective_agency_task_metadata(
    case: SelectiveAgencyCase,
    *,
    split: DistributionSplit,
    taskset_version: str,
    harness_version: str,
    runtime_version: str,
    seed: int,
) -> FoundryTaskMetadata:
    task = case.public
    return FoundryTaskMetadata(
        task_id=task.task_id,
        split=split,
        capability_tags=[
            "selective_agency",
            *_CLASS_CAPABILITIES[task.task_class],
        ],
        difficulty=infer_selective_agency_difficulty(case),
        seed=seed,
        taskset_version=taskset_version,
        harness_version=harness_version,
        runtime_version=runtime_version,
        generator_parameters={
            "capability_family": "selective_agency",
            "task_class": task.task_class.value,
            "available_actions": list(task.available_actions),
            "contrast_group": task.metadata.get("contrast_group"),
        },
    )


def adapt_selective_agency_tasks(
    cases: Iterable[SelectiveAgencyCase],
    *,
    split: DistributionSplit,
    taskset_version: str,
    harness_version: str,
    runtime_version: str,
    seed_start: int,
) -> list[FoundryTaskMetadata]:
    return [
        selective_agency_task_metadata(
            case,
            split=split,
            taskset_version=taskset_version,
            harness_version=harness_version,
            runtime_version=runtime_version,
            seed=seed_start + index,
        )
        for index, case in enumerate(cases)
    ]
