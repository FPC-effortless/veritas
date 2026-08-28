from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from investigation_world.core.models import InvestigationResult, Predicate, TruthStatus
from investigation_world.foundry.expert_trajectories import (
    DemonstrationSet,
    ExpertTrajectory,
    PreferencePair,
    TrainingUse,
    TrajectoryRole,
    VerifiedTrajectory,
    curate_verified_trace,
    make_preference_pair,
    qualify_expert_trace,
)
from investigation_world.foundry.external_runtime import ExternalInvestigationEpisode
from investigation_world.foundry.models import RolloutTrace, stable_hash
from investigation_world.foundry.tracing import TracingRuntimeProxy, replay_trace_prefix
from investigation_world.tasks.spec import TaskFamily


class ExternalInvestigationPolicy(Protocol):
    policy_id: str

    def run(
        self,
        runtime: Any,
        episode: ExternalInvestigationEpisode,
    ) -> InvestigationResult: ...


class CounterfactualMutation(StrEnum):
    ABSTAIN = "abstain"
    DROP_EVIDENCE = "drop_evidence"
    FLIP_IDENTITY = "flip_identity"
    DROP_RELATIONSHIP = "drop_relationship"


def _relationship_key(
    subject_id: str,
    predicate: Predicate,
    object_id: str,
) -> tuple[str, str, str]:
    return (subject_id, predicate.value, object_id)


def _provenance_roots(
    episode: ExternalInvestigationEpisode,
    document_ids: list[str],
) -> set[str]:
    parents = {
        key: set(value)
        for key, value in (
            episode.world.metadata.get("provenance_parents", {}) or {}
        ).items()
    }

    def root_set(document_id: str) -> set[str]:
        seen: set[str] = set()
        stack = [document_id]
        roots: set[str] = set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            current_parents = parents.get(current, set())
            if current_parents:
                stack.extend(current_parents)
            else:
                roots.add(current)
        return roots

    roots: set[str] = set()
    for document_id in document_ids:
        roots.update(root_set(document_id))
    return roots


def _supporting_documents(
    episode: ExternalInvestigationEpisode,
    *,
    maximum: int = 16,
) -> list[str]:
    world = episode.world
    oracle = episode.oracle
    task = episode.task
    documents = {document.document_id: document for document in world.documents}
    claims = {claim.claim_id: claim for claim in world.claims}
    source_reliability = {
        source.source_id: source.reliability_baseline for source in world.sources
    }

    if task.family == TaskFamily.PROVENANCE:
        return [
            document_id
            for document_id in oracle.provenance_document_ids
            if document_id in documents
        ][:maximum]

    def rank(candidates):
        return sorted(
            candidates,
            key=lambda document: (
                -source_reliability.get(document.source_id, 0.0),
                document.is_stale,
                -document.published_at.toordinal(),
                document.document_id,
            ),
        )

    chosen: list[str] = []
    all_candidates = []

    if task.family == TaskFamily.ENTITY_RESOLUTION:
        required_entities: set[str] = set()
        for target in oracle.identity_truth:
            required_entities.update(
                world.resolve_entity_ref(target.left_ref, allow_canonical_ids=False)
            )
            required_entities.update(
                world.resolve_entity_ref(target.right_ref, allow_canonical_ids=False)
            )
        for entity_id in sorted(required_entities):
            candidates = [
                document
                for document in world.documents
                if entity_id in document.entity_ids
            ]
            all_candidates.extend(candidates)
            ranked = rank(candidates)
            if ranked:
                chosen.append(ranked[0].document_id)
    else:
        target_keys = [
            _relationship_key(
                target.subject_id,
                target.predicate,
                target.object_id,
            )
            for target in oracle.relationship_truth
        ]
        documents_by_key: dict[tuple[str, str, str], list[Any]] = {
            key: [] for key in target_keys
        }
        for document in world.documents:
            for claim_id in document.claim_ids:
                claim = claims.get(claim_id)
                if (
                    claim is None
                    or claim.object_id is None
                    or claim.truth_status
                    not in {TruthStatus.TRUE, TruthStatus.PARTIALLY_TRUE}
                ):
                    continue
                key = _relationship_key(
                    claim.subject_id,
                    claim.predicate,
                    claim.object_id,
                )
                if key in documents_by_key:
                    documents_by_key[key].append(document)
                    all_candidates.append(document)
        for key in target_keys:
            ranked = rank(documents_by_key.get(key, []))
            if ranked:
                chosen.append(ranked[0].document_id)

    chosen = list(dict.fromkeys(chosen))
    covered_roots = _provenance_roots(episode, chosen)
    unique_candidates = list({item.document_id: item for item in all_candidates}.values())
    for document in rank(unique_candidates):
        if len(chosen) >= maximum:
            break
        if document.document_id in chosen:
            continue
        roots = _provenance_roots(episode, [document.document_id])
        if roots - covered_roots:
            chosen.append(document.document_id)
            covered_roots.update(roots)

    if len(chosen) < maximum:
        for document in rank(unique_candidates):
            if len(chosen) >= maximum:
                break
            if document.document_id not in chosen:
                chosen.append(document.document_id)

    return chosen[:maximum]


def _public_relationships(
    episode: ExternalInvestigationEpisode,
) -> list[dict[str, Any]]:
    world = episode.world
    output: list[dict[str, Any]] = []
    for target in episode.oracle.relationship_truth:
        when = target.valid_at or episode.task.query_date
        item: dict[str, Any] = {
            "subject": world.entity_display_name(target.subject_id, when),
            "predicate": target.predicate.value,
            "object": world.entity_display_name(target.object_id, when),
        }
        if when is not None:
            item["valid_at"] = when.isoformat()
        output.append(item)
    return output


def _oracle_result(
    episode: ExternalInvestigationEpisode,
    document_ids: list[str],
) -> InvestigationResult:
    task = episode.task
    oracle = episode.oracle
    evidence = [{"document_id": document_id} for document_id in document_ids]

    if not oracle.answerable:
        return InvestigationResult(
            unknowns=[oracle.answerability_reason or "insufficient public evidence"],
            conclusion="The available public evidence is insufficient for a defensible answer.",
            overall_confidence=0.0,
        )

    if task.family == TaskFamily.ENTITY_RESOLUTION:
        assertions = [
            {
                "left": target.left_ref,
                "right": target.right_ref,
                "same_entity": target.same_entity,
            }
            for target in oracle.identity_truth
        ]
        return InvestigationResult(
            identity_assertions=assertions,
            evidence=evidence,
            conclusion="Identity assessment supported by the cited public evidence.",
            overall_confidence=1.0,
        )

    if task.family == TaskFamily.PROVENANCE:
        return InvestigationResult(
            claims=[{"independent_source_count": oracle.provenance_root_count}],
            evidence=evidence,
            conclusion="Provenance roots reconstructed from the cited documents.",
            overall_confidence=1.0,
        )

    return InvestigationResult(
        relationships=_public_relationships(episode),
        evidence=evidence,
        conclusion="Relationship reconstruction supported by the cited public evidence.",
        overall_confidence=1.0,
    )


def _teacher_structural_guidance(
    episode: ExternalInvestigationEpisode,
) -> list[dict[str, Any]]:
    task = episode.task
    stages: list[dict[str, Any]] = [
        {
            "stage": "scope",
            "objective": "parse the requested target, time scope, and evidence constraints",
        },
        {
            "stage": "retrieve",
            "objective": "collect public evidence across independent source surfaces",
        },
    ]
    if task.family == TaskFamily.ENTITY_RESOLUTION:
        stages.append(
            {
                "stage": "resolve_identity",
                "objective": "compare aliases and records without forcing ambiguous merges",
            }
        )
    elif task.family == TaskFamily.PROVENANCE:
        stages.append(
            {
                "stage": "trace_provenance",
                "objective": "collapse derivative citations to independent root sources",
            }
        )
    else:
        stages.append(
            {
                "stage": "reconstruct",
                "objective": "reconstruct only relationships supported by public evidence",
            }
        )
        if task.query_date is not None:
            stages.append(
                {
                    "stage": "temporal_check",
                    "objective": "separate historical state from current state",
                }
            )
    stages.extend(
        [
            {
                "stage": "challenge",
                "objective": "adjudicate conflicts and preserve unresolved uncertainty",
            },
            {
                "stage": "verify",
                "objective": "check evidence support, provenance, calibration, and budget before submission",
            },
        ]
    )
    return stages


class OracleExpertPolicy:
    """Privileged reference policy used only to manufacture verified demonstrations.

    It may inspect hidden truth to choose an answer and supporting public documents, but
    all recorded observations and submitted evidence remain agent-visible objects.
    Never use this policy as an evaluated model baseline.
    """

    policy_id = "oracle-expert-v1"

    def __init__(self, *, max_documents: int = 16):
        self.max_documents = max_documents

    def _retrieve(
        self,
        runtime: Any,
        episode: ExternalInvestigationEpisode,
    ) -> list[str]:
        task = episode.task
        supporting = _supporting_documents(
            episode,
            maximum=self.max_documents,
        )

        refs = [reference for reference in task.target_refs if reference][:3]
        for reference in refs:
            runtime.document_search(reference, limit=5)
        if refs and task.family in {
            TaskFamily.OWNERSHIP,
            TaskFamily.CONFLICT,
            TaskFamily.DUE_DILIGENCE,
        }:
            runtime.registry_search(refs[0], limit=5)
            runtime.filing_search(refs[0], limit=5)
        elif refs and task.family == TaskFamily.TEMPORAL:
            runtime.archive_search(refs[0], limit=5)
        elif refs and task.family == TaskFamily.ENTITY_RESOLUTION:
            runtime.web_search(refs[0], limit=5)

        opened: list[str] = []
        for document_id in supporting:
            runtime.open_document(document_id)
            opened.append(document_id)
        return opened

    def run(
        self,
        runtime: Any,
        episode: ExternalInvestigationEpisode,
    ) -> InvestigationResult:
        documents = self._retrieve(runtime, episode)
        result = _oracle_result(episode, documents)
        runtime.submit(result)
        return result


def _trace_with_generation_metadata(
    trace: RolloutTrace,
    *,
    policy_id: str,
    invariant_pass: bool = True,
) -> RolloutTrace:
    return trace.model_copy(
        update={
            "metadata": {
                **trace.metadata,
                "generation_policy": policy_id,
                "privileged_generation": True,
                "invariant_pass": invariant_pass,
                "terminal_success": trace.total_reward > 0.0,
            }
        }
    )


def generate_verified_trajectory(
    episode: ExternalInvestigationEpisode,
    *,
    policy: ExternalInvestigationPolicy | None = None,
    environment_version: str = "external-investigation-v1",
    expert_threshold: float = 0.8,
) -> VerifiedTrajectory:
    policy = policy or OracleExpertPolicy()
    runtime = episode.runtime()
    proxy = TracingRuntimeProxy(
        runtime,
        episode.metadata,
        environment_version=environment_version,
    )
    try:
        policy.run(proxy, episode)
        provisional = proxy.trace(
            termination_reason=(
                "success"
                if proxy.verification is not None
                and float(getattr(proxy.verification, "overall_reward", 0.0))
                >= expert_threshold
                else "completed"
            )
        )
        trace = _trace_with_generation_metadata(
            provisional,
            policy_id=policy.policy_id,
        )
    finally:
        runtime.close()

    training_uses = [
        TrainingUse.SFT,
        TrainingUse.PREFERENCE,
        TrainingUse.RL,
        TrainingUse.VOPSD,
    ]
    annotations = {
        "policy_id": policy.policy_id,
        "privileged_reference": True,
        "public_task": episode.task.model_dump(mode="json"),
        "teacher_structural_guidance": _teacher_structural_guidance(episode),
    }
    if trace.total_reward >= expert_threshold:
        return qualify_expert_trace(
            trace,
            min_verifier_score=expert_threshold,
            training_uses=training_uses,
            annotations=annotations,
        )
    return curate_verified_trace(
        trace,
        role=TrajectoryRole.FAILURE,
        training_uses=[TrainingUse.EVAL_ONLY],
        annotations={
            **annotations,
            "expert_threshold": expert_threshold,
        },
    )


def mutate_investigation_result(
    result: InvestigationResult,
    mutation: CounterfactualMutation,
) -> InvestigationResult:
    if mutation == CounterfactualMutation.ABSTAIN:
        return InvestigationResult(
            unknowns=["counterfactual abstention"],
            conclusion="Insufficient evidence.",
            overall_confidence=0.0,
        )
    if mutation == CounterfactualMutation.DROP_EVIDENCE:
        return result.model_copy(update={"evidence": []}, deep=True)
    if mutation == CounterfactualMutation.FLIP_IDENTITY:
        assertions = [dict(item) for item in result.identity_assertions]
        if not assertions:
            return mutate_investigation_result(result, CounterfactualMutation.ABSTAIN)
        assertions[0]["same_entity"] = not bool(assertions[0].get("same_entity"))
        return result.model_copy(
            update={
                "identity_assertions": assertions,
                "overall_confidence": 1.0,
            },
            deep=True,
        )
    if mutation == CounterfactualMutation.DROP_RELATIONSHIP:
        if not result.relationships:
            return mutate_investigation_result(result, CounterfactualMutation.ABSTAIN)
        return result.model_copy(
            update={"relationships": result.relationships[1:]},
            deep=True,
        )
    raise ValueError(f"unsupported counterfactual mutation: {mutation}")


def _submitted_result(trace: RolloutTrace) -> InvestigationResult:
    submit = next(
        (event for event in reversed(trace.events) if event.event_type == "submit"),
        None,
    )
    if submit is None:
        raise ValueError("trace contains no submission")
    args = submit.payload.get("args", [])
    if not isinstance(args, list) or not args:
        raise ValueError("submit trace event contains no result argument")
    return InvestigationResult.model_validate(args[0])


def _default_counterfactual(task_family: TaskFamily) -> CounterfactualMutation:
    if task_family == TaskFamily.ENTITY_RESOLUTION:
        return CounterfactualMutation.FLIP_IDENTITY
    return CounterfactualMutation.DROP_EVIDENCE


def generate_counterfactual_trajectory(
    episode: ExternalInvestigationEpisode,
    chosen: VerifiedTrajectory,
    *,
    mutation: CounterfactualMutation | None = None,
    environment_version: str = "external-investigation-v1",
) -> VerifiedTrajectory:
    mutation = mutation or _default_counterfactual(episode.task.family)
    original = _submitted_result(chosen.trace)
    counterfactual = mutate_investigation_result(original, mutation)

    runtime = episode.runtime()
    proxy = TracingRuntimeProxy(
        runtime,
        episode.metadata,
        environment_version=environment_version,
        trace_id=f"{chosen.source_trace_id}-CF-{mutation.value}",
    )
    try:
        replay_trace_prefix(proxy, chosen.trace)
        proxy.submit(counterfactual)
        trace = _trace_with_generation_metadata(
            proxy.trace(termination_reason="counterfactual"),
            policy_id=f"counterfactual:{mutation.value}",
        )
    finally:
        runtime.close()

    return curate_verified_trace(
        trace,
        role=TrajectoryRole.PREFERENCE_REJECTED,
        training_uses=[TrainingUse.PREFERENCE, TrainingUse.EVAL_ONLY],
        annotations={
            "mutation": mutation.value,
            "parent_trajectory_id": chosen.trajectory_id,
            "privileged_reference": True,
            "public_task": episode.task.model_dump(mode="json"),
            "teacher_structural_guidance": _teacher_structural_guidance(episode),
        },
    )


def generate_demonstration_set(
    episodes: list[ExternalInvestigationEpisode],
    *,
    capability_contract_id: str,
    version: str = "1",
    policy: ExternalInvestigationPolicy | None = None,
    expert_threshold: float = 0.8,
    include_counterfactuals: bool = True,
    maximum_episodes: int | None = None,
) -> DemonstrationSet:
    selected = episodes if maximum_episodes is None else episodes[:maximum_episodes]
    trajectories: list[VerifiedTrajectory] = []
    preference_pairs: list[PreferencePair] = []

    for episode in selected:
        chosen = generate_verified_trajectory(
            episode,
            policy=policy,
            expert_threshold=expert_threshold,
        )
        trajectories.append(chosen)
        if (
            include_counterfactuals
            and isinstance(chosen, ExpertTrajectory)
            and episode.oracle.answerable
        ):
            rejected = generate_counterfactual_trajectory(episode, chosen)
            trajectories.append(rejected)
            if chosen.assessment.verifier_score > rejected.assessment.verifier_score:
                preference_pairs.append(
                    make_preference_pair(
                        chosen,
                        rejected,
                        reason="higher independently verified outcome",
                    )
                )

    payload = {
        "contract": capability_contract_id,
        "version": version,
        "trajectories": [item.trajectory_id for item in trajectories],
        "pairs": [item.pair_id for item in preference_pairs],
    }
    return DemonstrationSet(
        dataset_id=f"demos-{stable_hash(payload)[:20]}",
        version=version,
        capability_contract_id=capability_contract_id,
        trajectories=trajectories,
        preference_pairs=preference_pairs,
        metadata={
            "expert_threshold": expert_threshold,
            "counterfactuals": include_counterfactuals,
            "privileged_generation": True,
            "evaluation_use_of_oracle_policy_forbidden": True,
        },
    )
