from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from investigation_world.experience.models import (
    ExperienceSpan,
    MachineExperience,
    StructuralRecord,
)
from investigation_world.portable_contract import (
    PortableActionDefinition,
    PortableOperationalContract,
    PortableRuntimeOperation,
    PortableTransitionContract,
)
from investigation_world.trajectory import (
    ResourceCallSummary,
    TrajectoryEvent,
    TrajectoryV2,
    VisibilityClass,
    canonical_hash,
)

from .models import (
    AuthorityAnnotation,
    BudgetImpactAnnotation,
    EvidenceFlowAnnotation,
    InvariantEffectAnnotation,
    InvocationAnnotation,
    ProcessRequirementAnnotation,
    ResourceChargeAnnotation,
    SemanticAnnotationBundle,
    SemanticDerivationStatus,
    SemanticEventAnnotation,
    SemanticInvocationKind,
    StateTransitionAnnotation,
    VerifierRelevanceAnnotation,
)


class SemanticAnnotationError(ValueError):
    """Canonical evidence cannot support a deterministic annotation."""


_VISIBILITY_RANK = {
    VisibilityClass.PUBLIC: 0,
    VisibilityClass.BUYER_SAFE: 1,
    VisibilityClass.INTERNAL: 2,
    VisibilityClass.EVALUATOR_PRIVATE: 3,
    VisibilityClass.SEALED: 4,
}


def _max_visibility(*values: VisibilityClass) -> VisibilityClass:
    return max(values, key=lambda item: _VISIBILITY_RANK[item])


def _validated_trajectory(trajectory: TrajectoryV2) -> TrajectoryV2:
    try:
        return TrajectoryV2.model_validate(trajectory.model_dump(mode="python"))
    except (AttributeError, TypeError, ValidationError) as exc:
        raise SemanticAnnotationError(
            f"invalid canonical trajectory: {exc}"
        ) from exc


def _validated_contract(
    contract: PortableOperationalContract,
) -> PortableOperationalContract:
    try:
        return PortableOperationalContract.model_validate(
            contract.model_dump(mode="python")
        )
    except (AttributeError, TypeError, ValidationError) as exc:
        raise SemanticAnnotationError(
            f"invalid portable operational contract: {exc}"
        ) from exc


def _validate_binding(
    trajectory: TrajectoryV2,
    contract: PortableOperationalContract,
) -> None:
    if trajectory.task.task_id != contract.public.identity.task_id:
        raise SemanticAnnotationError(
            "trajectory task identity does not match portable contract task identity"
        )
    if (
        trajectory.world.world_id is not None
        and trajectory.world.world_id != contract.public.identity.world_id
    ):
        raise SemanticAnnotationError(
            "trajectory world identity does not match portable contract world identity"
        )
    reference = trajectory.world.portable_operational_contract
    if reference is None or reference.digest is None:
        return
    accepted = {contract.contract_id, contract.public.public_id}
    if reference.digest not in accepted:
        raise SemanticAnnotationError(
            "trajectory portable-contract digest does not match supplied contract"
        )


def _resource_calls_by_step(
    trajectory: TrajectoryV2,
) -> dict[int, tuple[ResourceCallSummary, ...]]:
    grouped: dict[int, list[ResourceCallSummary]] = {}
    for call in trajectory.resource_calls:
        step = call.public_metadata.get("source_event_step")
        if isinstance(step, int) and step >= 0:
            grouped.setdefault(step, []).append(call)
    return {step: tuple(items) for step, items in grouped.items()}


def _nested_request(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    request = payload.get("request")
    if isinstance(request, Mapping):
        return request
    return None


def _invocation_candidates(
    event: TrajectoryEvent,
    related_calls: tuple[ResourceCallSummary, ...],
    action_names: set[str],
    operation_names: set[str],
) -> tuple[tuple[str, SemanticInvocationKind, str], ...]:
    raw: list[tuple[str, Any]] = [
        ("payload.action", event.payload.get("action")),
        ("payload.method", event.payload.get("method")),
        ("payload.name", event.payload.get("name")),
        ("event_type", event.event_type),
    ]
    request = _nested_request(event.payload)
    if request is not None:
        raw.append(("payload.request.name", request.get("name")))
    for index, call in enumerate(related_calls):
        source = f"resource_call[{index}].operation"
        raw.append((source, call.operation))

    candidates: list[tuple[str, SemanticInvocationKind, str]] = []
    for source, value in raw:
        if not isinstance(value, str) or not value:
            continue
        in_action = value in action_names
        in_operation = value in operation_names
        if in_action and in_operation:
            raise SemanticAnnotationError(
                f"invocation {value!r} is both action and runtime operation"
            )
        if in_action:
            candidates.append((value, SemanticInvocationKind.ACTION, source))
        elif in_operation:
            candidates.append((value, SemanticInvocationKind.OPERATION, source))
    return tuple(candidates)


def _derive_invocation(
    event: TrajectoryEvent,
    related_calls: tuple[ResourceCallSummary, ...],
    actions: dict[str, PortableActionDefinition],
    operations: dict[str, PortableRuntimeOperation],
) -> InvocationAnnotation:
    candidates = _invocation_candidates(
        event,
        related_calls,
        set(actions),
        set(operations),
    )
    identities = {(name, kind) for name, kind, _source in candidates}
    if len(identities) > 1:
        raise SemanticAnnotationError(
            f"event {event.step} has conflicting structured invocation identities"
        )
    if not identities:
        return InvocationAnnotation(
            status=SemanticDerivationStatus.UNKNOWN,
            reason="no structured invocation identity matches the contract",
            visibility=event.visibility,
        )

    name, kind = next(iter(identities))
    sources = tuple(sorted({source for _name, _kind, source in candidates}))
    if kind is SemanticInvocationKind.ACTION:
        action_definition = actions[name]
        return InvocationAnnotation(
            status=SemanticDerivationStatus.DERIVED,
            kind=kind,
            name=name,
            system=action_definition.system,
            action_kind=action_definition.kind,
            interaction_mode=action_definition.interaction_mode.value,
            source_fields=sources,
            visibility=event.visibility,
        )

    operation_definition = operations[name]
    return InvocationAnnotation(
        status=SemanticDerivationStatus.DERIVED,
        kind=kind,
        name=name,
        interaction_mode=operation_definition.interaction_mode.value,
        source_fields=sources,
        visibility=event.visibility,
    )


def _structured_arguments(event: TrajectoryEvent) -> dict[str, Any] | None:
    candidates: list[Mapping[str, Any]] = []
    for key in ("kwargs", "arguments"):
        value = event.payload.get(key)
        if isinstance(value, Mapping):
            candidates.append(value)
    request = _nested_request(event.payload)
    if request is not None:
        value = request.get("arguments")
        if isinstance(value, Mapping):
            candidates.append(value)
    if not candidates:
        return None

    normalized = [dict(item) for item in candidates]
    first = normalized[0]
    if any(item != first for item in normalized[1:]):
        raise SemanticAnnotationError(
            f"event {event.step} has conflicting structured argument mappings"
        )
    return first


def _state_transition(event: TrajectoryEvent) -> StateTransitionAnnotation:
    before = event.state_before.digest if event.state_before is not None else None
    after = event.state_after.digest if event.state_after is not None else None
    if before is None or after is None:
        return StateTransitionAnnotation(
            status=SemanticDerivationStatus.UNKNOWN,
            state_before_digest=before,
            state_after_digest=after,
            reason="trajectory does not preserve both state digests",
            visibility=event.visibility,
        )
    return StateTransitionAnnotation(
        status=SemanticDerivationStatus.DERIVED,
        state_before_digest=before,
        state_after_digest=after,
        changed=before != after,
        visibility=event.visibility,
    )


def _process_requirement(
    invocation: InvocationAnnotation,
    contract: PortableOperationalContract,
) -> ProcessRequirementAnnotation:
    if invocation.status is not SemanticDerivationStatus.DERIVED:
        return ProcessRequirementAnnotation(
            status=SemanticDerivationStatus.UNKNOWN,
            reason="process relevance requires a derived action identity",
        )
    if invocation.kind is not SemanticInvocationKind.ACTION:
        return ProcessRequirementAnnotation(
            status=SemanticDerivationStatus.NOT_APPLICABLE,
            reason="runtime operations are not task actions",
        )
    if invocation.name is None:
        return ProcessRequirementAnnotation(
            status=SemanticDerivationStatus.UNKNOWN,
            reason="derived action is missing its name",
        )

    process = contract.private.process
    positions = tuple(
        index
        for index, action_name in enumerate(process.required_action_order)
        if action_name == invocation.name
    )
    return ProcessRequirementAnnotation(
        status=SemanticDerivationStatus.DERIVED,
        required=invocation.name in process.required_actions,
        forbidden=invocation.name in process.forbidden_actions,
        required_order_positions=positions,
        required_count=process.required_action_counts.get(invocation.name),
    )


def _transition_candidates(
    invocation: InvocationAnnotation,
    arguments: dict[str, Any] | None,
    contract: PortableOperationalContract,
) -> tuple[PortableTransitionContract, ...]:
    if (
        invocation.status is not SemanticDerivationStatus.DERIVED
        or invocation.kind is not SemanticInvocationKind.ACTION
        or invocation.name is None
    ):
        return ()

    output: list[PortableTransitionContract] = []
    for transition in contract.private.transitions:
        if transition.action_name != invocation.name:
            continue
        required = dict(transition.required_parameters)
        if required and arguments is None:
            continue
        if required and arguments is not None:
            mismatch = any(
                arguments.get(key) != value
                for key, value in required.items()
            )
            if mismatch:
                continue
        output.append(transition)
    return tuple(output)


def _invariant_effect(
    invocation: InvocationAnnotation,
    candidates: tuple[PortableTransitionContract, ...],
    contract: PortableOperationalContract,
) -> InvariantEffectAnnotation:
    if invocation.status is not SemanticDerivationStatus.DERIVED:
        return InvariantEffectAnnotation(
            status=SemanticDerivationStatus.UNKNOWN,
            reason="invariant relevance requires a derived action identity",
        )
    if invocation.kind is not SemanticInvocationKind.ACTION:
        return InvariantEffectAnnotation(
            status=SemanticDerivationStatus.NOT_APPLICABLE,
            reason="runtime operation has no action transition",
        )
    if not candidates:
        return InvariantEffectAnnotation(
            status=SemanticDerivationStatus.UNKNOWN,
            reason="no transition is selectable from preserved structured arguments",
        )

    changed_keys = {
        str(key)
        for transition in candidates
        for key in transition.set_state
    }
    affected = tuple(
        sorted(
            invariant.invariant_id
            for invariant in contract.private.semantic_state.invariants
            if (
                f"{invariant.assertion.object_id}."
                f"{invariant.assertion.field_name}"
            )
            in changed_keys
        )
    )
    return InvariantEffectAnnotation(
        status=SemanticDerivationStatus.DERIVED,
        affected_invariant_ids=affected,
        candidate_transition_indices=tuple(
            sorted(item.declaration_index for item in candidates)
        ),
        effect_verified=False,
        reason=(
            "transition overlap is structural; digest-only state cannot prove "
            "field-level invariant satisfaction"
        ),
    )


def _ids_from_value(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (tuple, list)):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _evidence_flow(
    event: TrajectoryEvent,
    arguments: dict[str, Any] | None,
    related_calls: tuple[ResourceCallSummary, ...],
    contract: PortableOperationalContract,
) -> EvidenceFlowAnnotation:
    known = {record.record_id for record in contract.public.evidence.records}
    created: set[str] = set()
    consumed: set[str] = set()
    referenced: set[str] = set()
    visibilities = [event.visibility]

    if arguments is not None:
        for key in ("created_evidence_ids", "emitted_evidence_ids"):
            created.update(
                item
                for item in _ids_from_value(arguments.get(key))
                if item in known
            )
        consume_keys = (
            "evidence_id",
            "evidence_ids",
            "consumed_evidence_ids",
            "required_evidence_ids",
            "record_id",
        )
        for key in consume_keys:
            consumed.update(
                item
                for item in _ids_from_value(arguments.get(key))
                if item in known
            )

    for reference in event.evidence_references:
        if reference.reference_id in known:
            referenced.add(reference.reference_id)
            visibilities.append(reference.visibility)

    for call in related_calls:
        for reference in call.evidence_references:
            if reference.reference_id in known:
                referenced.add(reference.reference_id)
                visibilities.append(reference.visibility)
        resource_id = call.resource_id or ""
        for prefix in ("record_id:", "target:"):
            if not resource_id.startswith(prefix):
                continue
            candidate = resource_id[len(prefix) :]
            read_operations = {"open_record", "open_document"}
            if candidate in known and call.operation in read_operations:
                consumed.add(candidate)

    visibility = _max_visibility(*visibilities)
    if created or consumed:
        return EvidenceFlowAnnotation(
            status=SemanticDerivationStatus.DERIVED,
            created_ids=tuple(sorted(created)),
            consumed_ids=tuple(sorted(consumed)),
            referenced_ids=tuple(sorted(referenced)),
            direction_complete=True,
            visibility=visibility,
        )
    if referenced:
        return EvidenceFlowAnnotation(
            status=SemanticDerivationStatus.UNKNOWN,
            referenced_ids=tuple(sorted(referenced)),
            direction_complete=False,
            reason="evidence direction is not represented by the trajectory",
            visibility=visibility,
        )
    return EvidenceFlowAnnotation(
        status=SemanticDerivationStatus.NOT_APPLICABLE,
        direction_complete=True,
        reason="no contract-bound evidence flow is represented",
        visibility=event.visibility,
    )


def _authority(
    invocation: InvocationAnnotation,
    operations: dict[str, PortableRuntimeOperation],
    contract: PortableOperationalContract,
) -> AuthorityAnnotation:
    if invocation.status is not SemanticDerivationStatus.DERIVED:
        return AuthorityAnnotation(
            status=SemanticDerivationStatus.UNKNOWN,
            reason="authority requires a derived invocation identity",
            visibility=invocation.visibility,
        )
    if invocation.kind is SemanticInvocationKind.ACTION:
        permitted = (
            invocation.system is not None
            and invocation.system in set(contract.public.permitted_systems)
        )
        return AuthorityAnnotation(
            status=SemanticDerivationStatus.DERIVED,
            system=invocation.system,
            statically_permitted=permitted,
            dynamic_permission_known=False,
            reason=(
                "public contract proves static system permission only; "
                "dynamic actor permission is not represented"
            ),
            visibility=invocation.visibility,
        )
    if invocation.name is None:
        return AuthorityAnnotation(
            status=SemanticDerivationStatus.UNKNOWN,
            reason="runtime operation name is absent",
            visibility=invocation.visibility,
        )

    operation = operations[invocation.name]
    if operation.permission_failure_behavior is None:
        return AuthorityAnnotation(
            status=SemanticDerivationStatus.NOT_APPLICABLE,
            reason="runtime operation declares no permission condition",
            visibility=invocation.visibility,
        )
    return AuthorityAnnotation(
        status=SemanticDerivationStatus.UNKNOWN,
        dynamic_permission_known=False,
        reason="permission-sensitive operation lacks dynamic authority state",
        visibility=invocation.visibility,
    )


def _resource_charges(
    charges: tuple[Any, ...],
) -> tuple[ResourceChargeAnnotation, ...]:
    return tuple(
        ResourceChargeAnnotation(
            resource=charge.resource,
            unit=charge.unit,
            amount=charge.amount,
        )
        for charge in charges
    )


def _budget_impact(
    event: TrajectoryEvent,
    invocation: InvocationAnnotation,
    actions: dict[str, PortableActionDefinition],
    operations: dict[str, PortableRuntimeOperation],
) -> BudgetImpactAnnotation:
    if (
        invocation.status is not SemanticDerivationStatus.DERIVED
        or invocation.name is None
    ):
        return BudgetImpactAnnotation(
            status=SemanticDerivationStatus.UNKNOWN,
            observed_event_cost=event.cost,
            remaining_budget_known=False,
            reason="declared charges require a derived invocation identity",
            visibility=event.visibility,
        )

    if invocation.kind is SemanticInvocationKind.ACTION:
        charges = _resource_charges(actions[invocation.name].charges)
    else:
        charges = _resource_charges(operations[invocation.name].charges)
    return BudgetImpactAnnotation(
        status=SemanticDerivationStatus.DERIVED,
        declared_charges=charges,
        observed_event_cost=event.cost,
        remaining_budget_known=False,
        reason="remaining evaluator-private budget is not inferred",
        visibility=event.visibility,
    )


def _verifier_relevance(
    invocation: InvocationAnnotation,
    process: ProcessRequirementAnnotation,
    invariant: InvariantEffectAnnotation,
    evidence: EvidenceFlowAnnotation,
    budget: BudgetImpactAnnotation,
    candidates: tuple[PortableTransitionContract, ...],
    contract: PortableOperationalContract,
) -> VerifierRelevanceAnnotation:
    available = {
        component.name
        for component in contract.private.evaluator.reward.components
    }
    relevance: set[str] = set()
    basis: set[str] = set()

    if process.status is SemanticDerivationStatus.DERIVED:
        process_relevant = (
            bool(process.required)
            or process.required_count is not None
            or bool(process.required_order_positions)
        )
        if process_relevant:
            relevance.add("process")
            basis.add("portable_process_requirement")
        if process.forbidden:
            relevance.add("constraints")
            basis.add("portable_forbidden_action")
    if invariant.affected_invariant_ids:
        relevance.add("constraints")
        basis.add("portable_invariant_transition_overlap")
    if candidates and any(item.set_state for item in candidates):
        relevance.add("state")
        basis.add("portable_transition_state_effect")
    if candidates and any(item.emitted_side_effects for item in candidates):
        relevance.add("side_effects")
        basis.add("portable_transition_side_effect")
    if evidence.created_ids or evidence.consumed_ids or evidence.referenced_ids:
        relevance.add("evidence")
        basis.add("contract_bound_evidence_flow")
    if budget.declared_charges or budget.observed_event_cost is not None:
        relevance.add("efficiency")
        basis.add("declared_or_observed_resource_cost")

    terminal = contract.public.runtime.termination.terminal_operation
    if (
        invocation.status is SemanticDerivationStatus.DERIVED
        and invocation.name == terminal
    ):
        relevance.add("outcome")
        basis.add("terminal_operation")

    filtered = tuple(sorted(relevance & available))
    if filtered:
        return VerifierRelevanceAnnotation(
            status=SemanticDerivationStatus.DERIVED,
            component_names=filtered,
            basis=tuple(sorted(basis)),
        )
    return VerifierRelevanceAnnotation(
        status=SemanticDerivationStatus.UNKNOWN,
        reason="no verifier relevance is provable from structured relations",
    )


def _span_id(payload: dict[str, Any]) -> str:
    return f"SEMSPAN-{canonical_hash(payload)[:24].upper()}"


def _record_id(payload: dict[str, Any]) -> str:
    return f"SEMREC-{canonical_hash(payload)[:24].upper()}"


def _experience_outputs(
    trajectory: TrajectoryV2,
    contract: PortableOperationalContract,
    annotations: tuple[SemanticEventAnnotation, ...],
) -> tuple[tuple[ExperienceSpan, ...], tuple[StructuralRecord, ...]]:
    spans: list[ExperienceSpan] = []
    records: list[StructuralRecord] = []

    if trajectory.events and trajectory.capability_tags:
        start = min(event.step for event in trajectory.events)
        end = max(event.step for event in trajectory.events)
        payload = {
            "kind": "capability_candidate",
            "trajectory_id": trajectory.trajectory_id,
            "start": start,
            "end": end,
            "capability_tags": list(trajectory.capability_tags),
        }
        spans.append(
            ExperienceSpan(
                span_id=_span_id(payload),
                span_type="capability_candidate",
                start_step=start,
                end_step=end,
                capability_tags=trajectory.capability_tags,
                reference_ids=(trajectory.trajectory_id,),
                visibility=trajectory.visibility,
            )
        )

    for annotation in annotations:
        invocation = annotation.invocation
        if (
            invocation.status is SemanticDerivationStatus.DERIVED
            and invocation.name is not None
        ):
            payload = {
                "kind": "semantic_invocation",
                "annotation_id": annotation.annotation_id,
                "name": invocation.name,
                "invocation_kind": invocation.kind.value,
                "step": annotation.step,
            }
            spans.append(
                ExperienceSpan(
                    span_id=_span_id(payload),
                    span_type="semantic_invocation",
                    start_step=annotation.step,
                    end_step=annotation.step,
                    capability_tags=trajectory.capability_tags,
                    reference_ids=(annotation.annotation_id,),
                    visibility=annotation.visibility,
                )
            )

        process = annotation.process_requirement
        process_subgoal = (
            process.status is SemanticDerivationStatus.DERIVED
            and (
                bool(process.required)
                or process.required_count is not None
                or bool(process.required_order_positions)
            )
        )
        if (
            invocation.kind is SemanticInvocationKind.ACTION
            and invocation.name is not None
            and process_subgoal
        ):
            payload = {
                "kind": "subgoal_candidate",
                "contract_id": contract.contract_id,
                "annotation_id": annotation.annotation_id,
                "action_name": invocation.name,
                "step": annotation.step,
            }
            spans.append(
                ExperienceSpan(
                    span_id=_span_id(payload),
                    span_type="subgoal_candidate",
                    start_step=annotation.step,
                    end_step=annotation.step,
                    capability_tags=trajectory.capability_tags,
                    reference_ids=(annotation.annotation_id,),
                    visibility=VisibilityClass.EVALUATOR_PRIVATE,
                )
            )
            records.append(
                StructuralRecord(
                    record_id=_record_id(payload),
                    step=annotation.step,
                    record_type="subgoal",
                    subject_references=(annotation.annotation_id,),
                    attributes={
                        "action_name": invocation.name,
                        "required": process.required,
                        "required_count": process.required_count,
                        "required_order_positions": list(
                            process.required_order_positions
                        ),
                        "contract_id": contract.contract_id,
                    },
                    visibility=VisibilityClass.EVALUATOR_PRIVATE,
                )
            )

        state = annotation.state_transition
        if state.status is SemanticDerivationStatus.DERIVED:
            payload = {
                "kind": "state_digest_relation",
                "annotation_id": annotation.annotation_id,
                "before": state.state_before_digest,
                "after": state.state_after_digest,
                "changed": state.changed,
            }
            records.append(
                StructuralRecord(
                    record_id=_record_id(payload),
                    step=annotation.step,
                    record_type="relation",
                    subject_references=(annotation.annotation_id,),
                    attributes={
                        "relation": "state_digest_transition",
                        "state_before_digest": state.state_before_digest,
                        "state_after_digest": state.state_after_digest,
                        "changed": state.changed,
                    },
                    visibility=state.visibility,
                )
            )

        evidence = annotation.evidence_flow
        if evidence.created_ids or evidence.consumed_ids:
            payload = {
                "kind": "evidence_flow",
                "annotation_id": annotation.annotation_id,
                "created": list(evidence.created_ids),
                "consumed": list(evidence.consumed_ids),
            }
            records.append(
                StructuralRecord(
                    record_id=_record_id(payload),
                    step=annotation.step,
                    record_type="relation",
                    subject_references=(annotation.annotation_id,),
                    attributes={
                        "relation": "evidence_flow",
                        "created_ids": list(evidence.created_ids),
                        "consumed_ids": list(evidence.consumed_ids),
                    },
                    visibility=evidence.visibility,
                )
            )

        invariant = annotation.invariant_effect
        if invariant.affected_invariant_ids:
            payload = {
                "kind": "invariant_effect_candidate",
                "contract_id": contract.contract_id,
                "annotation_id": annotation.annotation_id,
                "invariants": list(invariant.affected_invariant_ids),
            }
            records.append(
                StructuralRecord(
                    record_id=_record_id(payload),
                    step=annotation.step,
                    record_type="relation",
                    subject_references=(annotation.annotation_id,),
                    attributes={
                        "relation": "candidate_invariant_effect",
                        "invariant_ids": list(
                            invariant.affected_invariant_ids
                        ),
                        "effect_verified": False,
                        "contract_id": contract.contract_id,
                    },
                    visibility=VisibilityClass.EVALUATOR_PRIVATE,
                )
            )

    return tuple(spans), tuple(records)


def compile_semantic_annotations(
    trajectory: TrajectoryV2,
    contract: PortableOperationalContract,
) -> SemanticAnnotationBundle:
    """Compile canonical structured evidence into semantic annotations."""

    validated_trajectory = _validated_trajectory(trajectory)
    validated_contract = _validated_contract(contract)
    _validate_binding(validated_trajectory, validated_contract)

    actions = {
        action.name: action
        for action in validated_contract.public.actions
    }
    operations = {
        operation.name: operation
        for operation in validated_contract.public.runtime.builtin_operations
    }
    related_calls = _resource_calls_by_step(validated_trajectory)

    annotations: list[SemanticEventAnnotation] = []
    for event_index, event in enumerate(validated_trajectory.events):
        calls = related_calls.get(event.step, ())
        invocation = _derive_invocation(event, calls, actions, operations)
        arguments = _structured_arguments(event)
        process = _process_requirement(invocation, validated_contract)
        candidates = _transition_candidates(
            invocation,
            arguments,
            validated_contract,
        )
        invariant = _invariant_effect(
            invocation,
            candidates,
            validated_contract,
        )
        evidence = _evidence_flow(
            event,
            arguments,
            calls,
            validated_contract,
        )
        budget = _budget_impact(event, invocation, actions, operations)
        annotations.append(
            SemanticEventAnnotation(
                event_index=event_index,
                step=event.step,
                event_type=event.event_type,
                invocation=invocation,
                state_transition=_state_transition(event),
                process_requirement=process,
                invariant_effect=invariant,
                evidence_flow=evidence,
                authority=_authority(
                    invocation,
                    operations,
                    validated_contract,
                ),
                budget_impact=budget,
                verifier_relevance=_verifier_relevance(
                    invocation,
                    process,
                    invariant,
                    evidence,
                    budget,
                    candidates,
                    validated_contract,
                ),
                visibility=event.visibility,
            )
        )

    annotation_tuple = tuple(annotations)
    spans, structural_records = _experience_outputs(
        validated_trajectory,
        validated_contract,
        annotation_tuple,
    )
    return SemanticAnnotationBundle(
        trajectory_id=validated_trajectory.trajectory_id,
        contract_id=validated_contract.contract_id,
        public_contract_id=validated_contract.public.public_id,
        contract_schema_version=validated_contract.schema_version,
        trajectory_verifier_id=validated_trajectory.verifier.verifier_id,
        trajectory_verifier_version=validated_trajectory.verifier.version,
        evaluator_semantics_id=(
            validated_contract.private.evaluator.semantics_id
        ),
        event_annotations=annotation_tuple,
        spans=spans,
        structural_records=structural_records,
    )


def apply_semantic_annotations(
    experience: MachineExperience,
    bundle: SemanticAnnotationBundle,
) -> MachineExperience:
    """Compose annotations into a new immutable MachineExperience."""

    try:
        validated_experience = MachineExperience.model_validate(
            experience.model_dump(mode="python")
        )
        validated_bundle = SemanticAnnotationBundle.model_validate(
            bundle.model_dump(mode="python")
        )
    except (AttributeError, TypeError, ValidationError) as exc:
        raise SemanticAnnotationError(
            f"invalid annotation composition input: {exc}"
        ) from exc

    if validated_bundle.trajectory_id != validated_experience.trajectory.trajectory_id:
        raise SemanticAnnotationError(
            "semantic annotation bundle references a different trajectory"
        )

    existing_spans = {item.span_id for item in validated_experience.spans}
    new_spans = {item.span_id for item in validated_bundle.spans}
    if existing_spans & new_spans:
        raise SemanticAnnotationError(
            "semantic annotation span already exists on experience"
        )

    existing_records = {
        item.record_id
        for item in validated_experience.structural_records
    }
    new_records = {
        item.record_id
        for item in validated_bundle.structural_records
    }
    if existing_records & new_records:
        raise SemanticAnnotationError(
            "semantic annotation structural record already exists on experience"
        )

    payload = validated_experience.model_dump(mode="python")
    payload["spans"] = (
        *validated_experience.spans,
        *validated_bundle.spans,
    )
    payload["structural_records"] = (
        *validated_experience.structural_records,
        *validated_bundle.structural_records,
    )
    return MachineExperience.model_validate(payload)
