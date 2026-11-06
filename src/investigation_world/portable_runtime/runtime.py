from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

import investigation_world.operational.models as operational_models_module
import investigation_world.operational.runtime as operational_runtime_module
import investigation_world.operational.verifier as operational_verifier_module
from investigation_world.operational.models import (
    EpisodeSubmission,
    HiddenActionEffect,
    HiddenOracle,
    OperationalEpisode,
    OperationalInvariant,
    OperationalRecord,
    PublicActionSpec,
    StateAssertion,
    TaskContract,
)
from investigation_world.operational.runtime import OperationalRuntime
from investigation_world.portable_contract import (
    InteractionMode,
    PortableActionDefinition,
    PortableOperationalContract,
    PortableResourceCharge,
    PortableRuntimeOperation,
)
from investigation_world.portable_runtime.models import (
    PortableBudgetResourceStatus,
    PortableBudgetStatus,
    PortableFailureStatus,
    PortableInvocationKind,
    PortableResetResult,
    PortableRewardComponents,
    PortableRuntimeFailureCode,
    PortableStepRequest,
    PortableStepResult,
    PortableSubmission,
)
from investigation_world.portable_runtime.validation import (
    SchemaValidationError,
    UnsupportedSchemaError,
    ensure_supported_schema,
    validate_json_instance,
)


class PortableRuntimeError(RuntimeError):
    """Base error for evaluator-side portable runtime construction failures."""


class PortableRuntimeContractError(PortableRuntimeError):
    """The portable contract cannot be executed losslessly by the native runtime."""


_EXPECTED_EVALUATOR_ENTRYPOINT = (
    "investigation_world.operational.verifier:verify_operational_episode"
)
_EXPECTED_REWARD_WEIGHTS = {
    "outcome": 0.30,
    "state": 0.20,
    "constraints": 0.15,
    "side_effects": 0.10,
    "process": 0.10,
    "efficiency": 0.05,
    "evidence": 0.10,
}
_EXPECTED_BUDGETS = {
    "cost": ("cost_units", "reject_if_post_charge_usage_gt_maximum"),
    "tool_calls": ("calls", "reject_if_current_usage_gte_maximum_before_charge"),
}
_EXPECTED_OPERATION_CHARGES = {
    "search": {"cost": ("cost_units", 1), "tool_calls": ("calls", 1)},
    "search_all": {"cost": ("cost_units", 2), "tool_calls": ("calls", 1)},
    "open_record": {"cost": ("cost_units", 1), "tool_calls": ("calls", 1)},
    "submit": {},
}


def _git_blob_sha1(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n")
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    if isinstance(value, frozenset):
        return [_thaw(item) for item in sorted(value, key=repr)]
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _thaw(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _validation_error_details(exc: ValidationError) -> dict[str, Any]:
    errors = exc.errors(include_url=False)
    if not errors:
        return {}
    first = errors[0]
    return {
        "location": [str(item) for item in first.get("loc", ())],
        "type": str(first.get("type", "validation_error")),
    }


def _charge_map(
    charges: tuple[PortableResourceCharge, ...],
) -> dict[str, tuple[str, int]]:
    result: dict[str, tuple[str, int]] = {}
    for charge in charges:
        if charge.resource in result:
            raise PortableRuntimeContractError(
                f"duplicate runtime charge for resource {charge.resource!r}"
            )
        result[charge.resource] = (charge.unit, charge.amount)
    return result


def _required_parameter_names(action: PortableActionDefinition) -> tuple[str, ...]:
    schema = action.input_schema
    if not isinstance(schema, Mapping):
        raise PortableRuntimeContractError(
            f"action {action.name!r} input schema must be an object schema"
        )
    type_spec = schema.get("type")
    types = {type_spec} if isinstance(type_spec, str) else set(type_spec or ())
    if type_spec is not None and "object" not in types:
        raise PortableRuntimeContractError(
            f"action {action.name!r} input schema must accept an object"
        )
    composed = ("allOf", "anyOf", "oneOf", "if")
    if "$ref" in schema or any(key in schema for key in composed):
        raise PortableRuntimeContractError(
            f"action {action.name!r} must declare root properties/required directly"
        )
    properties = schema.get("properties", {})
    required = schema.get("required", ())
    if not isinstance(properties, Mapping):
        raise PortableRuntimeContractError(
            f"action {action.name!r} properties must be an object"
        )
    if not isinstance(required, (list, tuple)) or any(
        not isinstance(name, str) for name in required
    ):
        raise PortableRuntimeContractError(
            f"action {action.name!r} required must be an array of strings"
        )
    declared = set(action.parameter_names)
    property_names = set(properties)
    if property_names != declared:
        raise PortableRuntimeContractError(
            f"action {action.name!r} parameter_names and input properties differ"
        )
    if not set(required).issubset(declared):
        raise PortableRuntimeContractError(
            f"action {action.name!r} required inputs reference undeclared parameters"
        )
    if len(required) != len(set(required)):
        raise PortableRuntimeContractError(
            f"action {action.name!r} required inputs contain duplicates"
        )
    return tuple(required)


def _portable_assertion(assertion: Any) -> StateAssertion:
    return StateAssertion(
        object_id=assertion.object_id,
        field_name=assertion.field_name,
        expected_value=_thaw(assertion.expected_value),
        tolerance=assertion.tolerance,
        comparison=assertion.comparison,
    )


def _validate_native_source_pins(contract: PortableOperationalContract) -> None:
    model_path = Path(str(operational_models_module.__file__))
    runtime_path = Path(str(operational_runtime_module.__file__))
    verifier_path = Path(str(operational_verifier_module.__file__))
    expected = {
        model_path: contract.public.provenance.source_model_git_blob_sha1,
        runtime_path: contract.public.provenance.source_runtime_git_blob_sha1,
        verifier_path: contract.private.evaluator.source_git_blob_sha1,
    }
    for path, expected_blob in expected.items():
        if not path.is_file():
            raise PortableRuntimeContractError(
                f"required native source file is unavailable: {path}"
            )
        actual = _git_blob_sha1(path)
        if actual != expected_blob:
            raise PortableRuntimeContractError(
                f"native source semantics changed for {path.name}: "
                f"expected {expected_blob}, got {actual}"
            )
    if (
        contract.public.provenance.source_verifier_git_blob_sha1
        != contract.private.evaluator.source_git_blob_sha1
    ):
        raise PortableRuntimeContractError(
            "public provenance and evaluator binding disagree on verifier semantics"
        )


def _validate_reward_binding(contract: PortableOperationalContract) -> None:
    evaluator = contract.private.evaluator
    if evaluator.entrypoint != _EXPECTED_EVALUATOR_ENTRYPOINT:
        raise PortableRuntimeContractError(
            f"unsupported evaluator entrypoint: {evaluator.entrypoint!r}"
        )
    weights = {
        component.name: component.weight
        for component in evaluator.reward.components
    }
    if set(weights) != set(_EXPECTED_REWARD_WEIGHTS):
        raise PortableRuntimeContractError(
            "portable reward component names do not match native verifier"
        )
    for name, expected in _EXPECTED_REWARD_WEIGHTS.items():
        if abs(weights[name] - expected) > 1e-12:
            raise PortableRuntimeContractError(
                f"portable reward weight for {name!r} does not match native verifier"
            )
    if evaluator.reward.aggregate_rule != "weighted_sum_clamped_0_1":
        raise PortableRuntimeContractError("unsupported reward aggregation rule")
    if evaluator.reward.output_round_decimal_places != 6:
        raise PortableRuntimeContractError(
            "native verifier reward rounding must remain six decimals"
        )


def _validate_budgets(contract: PortableOperationalContract) -> dict[str, int]:
    limits = {limit.resource: limit for limit in contract.private.budgets.limits}
    if set(limits) != set(_EXPECTED_BUDGETS):
        raise PortableRuntimeContractError(
            "native OperationalRuntime supports exactly cost and tool_calls budgets"
        )
    maximums: dict[str, int] = {}
    for resource, (unit, exhaustion_rule) in _EXPECTED_BUDGETS.items():
        limit = limits[resource]
        if limit.unit != unit or limit.exhaustion_rule != exhaustion_rule:
            raise PortableRuntimeContractError(
                f"budget semantics for {resource!r} do not match native OperationalRuntime"
            )
        if limit.maximum < 1:
            raise PortableRuntimeContractError(
                f"native OperationalRuntime requires {resource!r} maximum >= 1"
            )
        maximums[resource] = limit.maximum
    return maximums


def _validate_charges(contract: PortableOperationalContract) -> None:
    for action in contract.public.actions:
        expected = {
            "cost": ("cost_units", action.cost),
            "tool_calls": ("calls", 1),
        }
        if _charge_map(action.charges) != expected:
            raise PortableRuntimeContractError(
                f"action {action.name!r} charges do not match native OperationalRuntime"
            )
    operations = {
        operation.name: operation
        for operation in contract.public.runtime.builtin_operations
    }
    if len(operations) != len(contract.public.runtime.builtin_operations):
        raise PortableRuntimeContractError(
            "portable runtime operation names must be unique"
        )
    if set(operations) != set(_EXPECTED_OPERATION_CHARGES):
        raise PortableRuntimeContractError(
            "portable runtime must expose exactly search, search_all, open_record, and submit"
        )
    for name, expected in _EXPECTED_OPERATION_CHARGES.items():
        if _charge_map(operations[name].charges) != expected:
            raise PortableRuntimeContractError(
                f"runtime operation {name!r} charges do not match native OperationalRuntime"
            )
    expected_modes = {
        "search": InteractionMode.RETRIEVAL,
        "search_all": InteractionMode.RETRIEVAL,
        "open_record": InteractionMode.RETRIEVAL,
        "submit": InteractionMode.SUBMISSION,
    }
    for name, mode in expected_modes.items():
        if operations[name].interaction_mode != mode:
            raise PortableRuntimeContractError(
                f"runtime operation {name!r} has incompatible interaction mode"
            )


def _validate_schemas(contract: PortableOperationalContract) -> None:
    schemas: list[tuple[str, Any]] = [
        ("public.state.observation_schema", contract.public.state.observation_schema)
    ]
    for action in contract.public.actions:
        _required_parameter_names(action)
        schemas.extend(
            [
                (f"action.{action.name}.input_schema", action.input_schema),
                (f"action.{action.name}.output_schema", action.output_schema),
            ]
        )
        if action.interaction_mode != InteractionMode.ACTION:
            raise PortableRuntimeContractError(
                f"public action {action.name!r} must use action interaction mode"
            )
    for operation in contract.public.runtime.builtin_operations:
        schemas.extend(
            [
                (f"operation.{operation.name}.input_schema", operation.input_schema),
                (f"operation.{operation.name}.output_schema", operation.output_schema),
            ]
        )
    for path, schema in schemas:
        try:
            ensure_supported_schema(schema)
        except UnsupportedSchemaError as exc:
            raise PortableRuntimeContractError(f"{path}: {exc.detail}") from exc


def _validate_runtime_semantics(contract: PortableOperationalContract) -> None:
    runtime = contract.public.runtime
    termination = runtime.termination
    if not runtime.stateful or not runtime.deterministic_reset:
        raise PortableRuntimeContractError(
            "native portable runtime requires stateful deterministic reset"
        )
    if contract.public.state.state_snapshot_agent_visible:
        raise PortableRuntimeContractError(
            "dynamic hidden state snapshots cannot be exposed through the public runtime"
        )
    if contract.public.state.hidden_state_updates_agent_visible:
        raise PortableRuntimeContractError(
            "hidden state updates cannot be agent-visible"
        )
    if termination.terminal_operation != "submit" or not termination.closes_after_evaluation:
        raise PortableRuntimeContractError(
            "native termination semantics require submit to close"
        )
    if termination.post_terminal_behavior != (
        "raise_value_error_episode_already_submitted"
    ):
        raise PortableRuntimeContractError("unsupported post-terminal behavior")
    if termination.budget_exhaustion_behavior != (
        "raise_value_error_investigation_budget_exhausted_without_closing"
    ):
        raise PortableRuntimeContractError(
            "unsupported native budget exhaustion behavior"
        )


def _validated_contract(
    contract: PortableOperationalContract,
) -> PortableOperationalContract:
    try:
        validated = PortableOperationalContract.model_validate(
            contract.model_dump(mode="python")
        )
    except (AttributeError, TypeError, ValidationError) as exc:
        raise PortableRuntimeContractError(
            f"invalid PortableOperationalContract: {exc}"
        ) from exc
    _validate_native_source_pins(validated)
    _validate_reward_binding(validated)
    _validate_budgets(validated)
    _validate_charges(validated)
    _validate_schemas(validated)
    _validate_runtime_semantics(validated)
    return validated


def _episode_from_contract(
    contract: PortableOperationalContract,
) -> tuple[OperationalEpisode, dict[str, Any]]:
    public = contract.public
    private = contract.private
    maximums = _validate_budgets(contract)

    public_actions = [
        PublicActionSpec(
            name=action.name,
            kind=action.kind,
            system=action.system,
            description=action.description,
            parameter_names=list(action.parameter_names),
            cost=action.cost,
        )
        for action in public.actions
    ]
    task = TaskContract(
        task_id=public.identity.task_id,
        world_id=public.identity.world_id,
        domain=public.identity.domain,
        objective=public.objective,
        role=public.role,
        permitted_systems=list(public.permitted_systems),
        available_actions=public_actions,
        constraints=list(public.constraints),
        success_description=public.success_description,
        metadata=_thaw(public.task_metadata),
    )
    records = [
        OperationalRecord(
            record_id=record.record_id,
            system=record.system,
            record_type=record.record_type,
            object_id=record.object_id,
            fields=_thaw(record.fields),
            related_object_ids=list(record.related_object_ids),
            searchable_text=record.searchable_text,
            observed_at=record.observed_at,
            valid_from=record.valid_from,
            valid_to=record.valid_to,
            source_authority=record.source_authority,
            confidence=record.confidence,
            freshness=record.freshness,
            provenance_ids=list(record.provenance_ids),
        )
        for record in public.evidence.records
    ]
    oracle = HiddenOracle(
        task_id=private.oracle_task_id,
        initial_state=_thaw(private.semantic_state.initial_state),
        target_state=[
            _portable_assertion(assertion)
            for assertion in private.semantic_state.target_assertions
        ],
        invariants=[
            OperationalInvariant(
                invariant_id=invariant.invariant_id,
                description=invariant.description,
                assertion=_portable_assertion(invariant.assertion),
                severity=invariant.severity,
                scope=invariant.scope,
            )
            for invariant in private.semantic_state.invariants
        ],
        required_actions=list(private.process.required_actions),
        required_action_order=list(private.process.required_action_order),
        required_action_counts=_thaw(private.process.required_action_counts),
        forbidden_actions=list(private.process.forbidden_actions),
        required_evidence_ids=list(private.required_evidence_ids),
        action_effects=[
            HiddenActionEffect(
                action_name=transition.action_name,
                required_parameters=_thaw(transition.required_parameters),
                required_state=[
                    _portable_assertion(assertion)
                    for assertion in transition.required_state
                ],
                required_prior_actions=list(transition.required_prior_actions),
                set_state=_thaw(transition.set_state),
                observable_result=_thaw(transition.observable_result),
                blocked_observable_result=_thaw(
                    transition.blocked_observable_result
                ),
                emitted_side_effects=list(transition.emitted_side_effects),
                forbidden=transition.forbidden,
                consequence_severity=transition.consequence_severity,
            )
            for transition in private.transitions
        ],
        max_cost=maximums["cost"],
        max_tool_calls=maximums["tool_calls"],
        metadata=_thaw(private.oracle_metadata),
    )
    validated_episode = OperationalEpisode(
        episode_id=public.identity.episode_id,
        world_id=public.identity.world_id,
        task=task,
        records=records,
        oracle=oracle,
        metadata=_thaw(public.episode_metadata),
    )
    public_observation = _thaw(validated_episode.public_payload())

    required_by_action = {
        action.name: _required_parameter_names(action)
        for action in public.actions
    }
    runtime_actions = [
        action.model_copy(
            update={"parameter_names": list(required_by_action[action.name])}
        )
        for action in validated_episode.task.available_actions
    ]
    runtime_task = validated_episode.task.model_copy(
        update={"available_actions": runtime_actions}
    )
    runtime_episode = validated_episode.model_copy(
        update={"task": runtime_task},
        deep=True,
    )
    return runtime_episode, public_observation


class PortableOperationalRuntime:
    """Stable evaluator-side façade that delegates execution to OperationalRuntime."""

    def __init__(self, contract: PortableOperationalContract):
        self._contract = _validated_contract(contract)
        self._episode_template, self._public_observation = _episode_from_contract(
            self._contract
        )
        self._actions = {
            action.name: action for action in self._contract.public.actions
        }
        self._operations = {
            operation.name: operation
            for operation in self._contract.public.runtime.builtin_operations
        }
        self._native: OperationalRuntime
        self._seed = 0
        self._terminated = False
        self._truncated = False
        self._submitted = False
        self._budget_exhaustion_resources: tuple[str, ...] = ()
        self.reset(seed=0)

    def reset(self, *, seed: int | None = 0) -> PortableResetResult:
        if seed is None:
            seed = 0
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError("portable runtime seed must be an integer or None")
        self._seed = seed
        self._native = OperationalRuntime(
            self._episode_template.model_copy(deep=True)
        )
        self._terminated = False
        self._truncated = False
        self._submitted = False
        self._budget_exhaustion_resources = ()
        return PortableResetResult(
            observation=self.public_state(),
            state_digest=self.state_digest(),
            budget_status=self.budget_state(),
        )

    def public_state(self) -> dict[str, Any]:
        """Return only the static agent-visible operational observation."""

        observation = _thaw(self._public_observation)
        try:
            validate_json_instance(
                observation,
                self._contract.public.state.observation_schema,
            )
        except (SchemaValidationError, UnsupportedSchemaError) as exc:
            raise PortableRuntimeContractError(
                f"public observation violates portable state schema: {exc}"
            ) from exc
        return observation

    def state_digest(self) -> str:
        """Return an opaque keyed digest without exposing evaluator-private state bytes."""

        payload = _canonical_json_bytes(
            {
                "protocol": "portable-runtime-state-v1",
                "seed": self._seed,
                "state": self._native.state_snapshot(),
            }
        )
        digest = hmac.new(
            self._contract.contract_id.encode("ascii"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return f"hmac-sha256:{digest}"

    def budget_state(self) -> PortableBudgetStatus:
        snapshot = self._native.budget_snapshot()
        used_by_resource = {
            "cost": int(snapshot["spent"]),
            "tool_calls": int(snapshot["calls"]),
        }
        resources: list[PortableBudgetResourceStatus] = []
        exhausted = set(self._budget_exhaustion_resources)
        for limit in self._contract.private.budgets.limits:
            used = used_by_resource[limit.resource]
            remaining = max(0, limit.maximum - used)
            at_limit = remaining == 0
            if at_limit:
                exhausted.add(limit.resource)
            resources.append(
                PortableBudgetResourceStatus(
                    resource=limit.resource,
                    unit=limit.unit,
                    maximum=limit.maximum,
                    used=used,
                    remaining=remaining,
                    exhausted=(
                        at_limit
                        or limit.resource in self._budget_exhaustion_resources
                    ),
                )
            )
        ordered_exhausted = tuple(
            limit.resource
            for limit in self._contract.private.budgets.limits
            if limit.resource in exhausted
        )
        return PortableBudgetStatus(
            resources=tuple(resources),
            exhausted=bool(ordered_exhausted),
            exhausted_resources=ordered_exhausted,
        )

    def step(
        self,
        request: PortableStepRequest | Mapping[str, Any] | str,
        arguments: Mapping[str, Any] | None = None,
    ) -> PortableStepResult:
        parsed = self._parse_step_request(request, arguments)
        if isinstance(parsed, PortableStepResult):
            return parsed
        if parsed.kind == PortableInvocationKind.ACTION:
            return self._step_action(parsed)
        return self._step_operation(parsed)

    def verify(
        self,
        submission: PortableSubmission | Mapping[str, Any] | None = None,
    ) -> PortableStepResult:
        """Alias for submit(); native verification remains the only reward authority."""

        return self.submit(submission)

    def submit(
        self,
        submission: PortableSubmission | Mapping[str, Any] | None = None,
    ) -> PortableStepResult:
        if self._submitted or self._terminated:
            return self._session_failure_result()

        payload = {} if submission is None else submission
        try:
            portable_submission = (
                payload
                if isinstance(payload, PortableSubmission)
                else PortableSubmission.model_validate(payload)
            )
        except ValidationError as exc:
            return self._failure_result(
                PortableRuntimeFailureCode.INVALID_SUBMISSION,
                "submission does not satisfy the portable submission model",
                operation="submit",
                details=_validation_error_details(exc),
            )

        operation = self._operations["submit"]
        input_payload = portable_submission.model_dump(mode="json")
        try:
            validate_json_instance(input_payload, operation.input_schema)
        except SchemaValidationError as exc:
            return self._failure_result(
                PortableRuntimeFailureCode.INVALID_SUBMISSION,
                "submission does not satisfy the portable contract schema",
                operation="submit",
                details={"path": exc.path, "reason": exc.message},
            )
        except UnsupportedSchemaError as exc:
            return self._failure_result(
                PortableRuntimeFailureCode.CONTRACT_SCHEMA_UNSUPPORTED,
                "portable submission schema cannot be enforced losslessly",
                operation="submit",
                details={"path": exc.path},
            )

        native_submission = EpisodeSubmission(**input_payload)
        was_truncated = self._truncated
        try:
            breakdown = self._native.submit(native_submission)
        except ValueError as exc:
            if str(exc) == "episode already submitted":
                self._submitted = True
                if not was_truncated:
                    self._terminated = True
                return self._session_failure_result()
            return self._failure_result(
                PortableRuntimeFailureCode.INTERNAL_RUNTIME_ERROR,
                "native verifier rejected the submission unexpectedly",
                operation="submit",
            )

        breakdown_payload = breakdown.model_dump(mode="json")
        try:
            validate_json_instance(breakdown_payload, operation.output_schema)
        except (SchemaValidationError, UnsupportedSchemaError) as exc:
            self._submitted = True
            if not was_truncated:
                self._terminated = True
            return self._failure_result(
                PortableRuntimeFailureCode.OUTPUT_SCHEMA_VIOLATION,
                "native verifier output violates the portable contract",
                operation="submit",
                details={"path": getattr(exc, "path", "$output")},
            )

        components = PortableRewardComponents(
            outcome=breakdown.outcome,
            state=breakdown.state,
            constraints=breakdown.constraints,
            side_effects=breakdown.side_effects,
            process=breakdown.process,
            efficiency=breakdown.efficiency,
            evidence=breakdown.evidence,
        )
        self._submitted = True
        self._terminated = not was_truncated
        return PortableStepResult(
            observation={"submitted": True},
            reward=breakdown.overall_reward,
            reward_components=components,
            terminated=self._terminated,
            truncated=was_truncated,
            state_digest=self.state_digest(),
            budget_status=self.budget_state(),
            failure=None,
        )

    def _parse_step_request(
        self,
        request: PortableStepRequest | Mapping[str, Any] | str,
        arguments: Mapping[str, Any] | None,
    ) -> PortableStepRequest | PortableStepResult:
        if isinstance(request, str):
            payload: Any = {
                "kind": PortableInvocationKind.ACTION,
                "name": request,
                "arguments": dict(arguments or {}),
            }
        else:
            if arguments is not None:
                return self._failure_result(
                    PortableRuntimeFailureCode.INVALID_REQUEST,
                    "arguments must be embedded when request is not a string",
                )
            payload = request
        try:
            if isinstance(payload, PortableStepRequest):
                return payload
            return PortableStepRequest.model_validate(payload)
        except ValidationError as exc:
            return self._failure_result(
                PortableRuntimeFailureCode.INVALID_REQUEST,
                "step request does not satisfy the portable request model",
                details=_validation_error_details(exc),
            )

    def _step_action(self, request: PortableStepRequest) -> PortableStepResult:
        if self._terminated or self._truncated:
            return self._session_failure_result(action_name=request.name)
        action = self._actions.get(request.name)
        if action is None:
            return self._failure_result(
                PortableRuntimeFailureCode.INVALID_ACTION,
                "action is not declared by the portable contract",
                action_name=request.name,
            )
        try:
            validate_json_instance(request.arguments, action.input_schema)
        except SchemaValidationError as exc:
            return self._failure_result(
                PortableRuntimeFailureCode.INVALID_ACTION_INPUT,
                "action arguments do not satisfy the portable input schema",
                action_name=action.name,
                details={"path": exc.path, "reason": exc.message},
            )
        except UnsupportedSchemaError as exc:
            return self._failure_result(
                PortableRuntimeFailureCode.CONTRACT_SCHEMA_UNSUPPORTED,
                "portable action schema cannot be enforced losslessly",
                action_name=action.name,
                details={"path": exc.path},
            )

        before_state = self._native.state_snapshot()
        event_count = len(self._native.events)
        try:
            observation = self._native.act(
                action.name,
                **dict(request.arguments),
            )
        except ValueError as exc:
            if str(exc) == "investigation budget exhausted":
                self._mark_budget_exhausted(action.charges)
                return self._failure_result(
                    PortableRuntimeFailureCode.BUDGET_EXHAUSTED,
                    "action charge exceeds the remaining runtime budget",
                    action_name=action.name,
                    details={
                        "resources": list(self._budget_exhaustion_resources)
                    },
                )
            if str(exc) == "episode already submitted":
                self._terminated = True
                return self._session_failure_result(action_name=action.name)
            return self._failure_result(
                PortableRuntimeFailureCode.INTERNAL_RUNTIME_ERROR,
                "native OperationalRuntime rejected a schema-valid action unexpectedly",
                action_name=action.name,
            )
        except KeyError:
            return self._failure_result(
                PortableRuntimeFailureCode.INTERNAL_RUNTIME_ERROR,
                "portable action is missing from the reconstructed native runtime",
                action_name=action.name,
            )

        try:
            validate_json_instance(observation, action.output_schema)
        except (SchemaValidationError, UnsupportedSchemaError) as exc:
            return self._failure_result(
                PortableRuntimeFailureCode.OUTPUT_SCHEMA_VIOLATION,
                "native action observation violates the portable output schema",
                action_name=action.name,
                details={"path": getattr(exc, "path", "$output")},
            )

        event = (
            self._native.events[-1]
            if len(self._native.events) > event_count
            else None
        )
        if event is not None and event.blocked:
            if before_state != self._native.state_snapshot():
                return self._failure_result(
                    PortableRuntimeFailureCode.INTERNAL_RUNTIME_ERROR,
                    "native blocked action mutated evaluator state",
                    action_name=action.name,
                )
            public_reason = (
                observation.get("reason")
                if isinstance(observation, Mapping)
                else None
            )
            details = (
                {"reason": public_reason}
                if isinstance(public_reason, str)
                else {}
            )
            precondition = bool(
                event.blocked_reason
                and (
                    event.blocked_reason.startswith("state:")
                    or event.blocked_reason.startswith("prior_action:")
                )
            )
            code = (
                PortableRuntimeFailureCode.PRECONDITION_REJECTED
                if precondition
                else PortableRuntimeFailureCode.ACTION_REJECTED
            )
            return self._failure_result(
                code,
                "native action transition was rejected without mutating state",
                observation=observation,
                action_name=action.name,
                details=details,
            )

        return self._success_result(observation=observation)

    def _step_operation(self, request: PortableStepRequest) -> PortableStepResult:
        operation = self._operations.get(request.name)
        if operation is None:
            return self._failure_result(
                PortableRuntimeFailureCode.INVALID_OPERATION,
                "operation is not declared by the portable runtime contract",
                operation=request.name,
            )
        if operation.name == "submit":
            return self.submit(request.arguments)
        if self._truncated:
            return self._session_failure_result(operation=operation.name)

        permission_failure = self._permission_failure_precedes_closed(
            operation,
            request.arguments,
        )
        if self._terminated and not permission_failure:
            return self._session_failure_result(operation=operation.name)

        validation_schema = self._operation_input_schema(
            operation,
            request.arguments,
            permission_failure=permission_failure,
        )
        try:
            validate_json_instance(request.arguments, validation_schema)
        except SchemaValidationError as exc:
            return self._failure_result(
                PortableRuntimeFailureCode.INVALID_OPERATION_INPUT,
                "operation arguments do not satisfy the portable input schema",
                operation=operation.name,
                details={"path": exc.path, "reason": exc.message},
            )
        except UnsupportedSchemaError as exc:
            return self._failure_result(
                PortableRuntimeFailureCode.CONTRACT_SCHEMA_UNSUPPORTED,
                "portable operation schema cannot be enforced losslessly",
                operation=operation.name,
                details={"path": exc.path},
            )

        try:
            observation = self._invoke_operation(
                operation,
                request.arguments,
            )
        except ValueError as exc:
            if str(exc) == "investigation budget exhausted":
                self._mark_budget_exhausted(operation.charges)
                return self._failure_result(
                    PortableRuntimeFailureCode.BUDGET_EXHAUSTED,
                    "operation charge exceeds the remaining runtime budget",
                    operation=operation.name,
                    details={
                        "resources": list(self._budget_exhaustion_resources)
                    },
                )
            if str(exc) == "episode already submitted":
                self._terminated = True
                return self._session_failure_result(operation=operation.name)
            return self._failure_result(
                PortableRuntimeFailureCode.INTERNAL_RUNTIME_ERROR,
                "native OperationalRuntime rejected a schema-valid operation unexpectedly",
                operation=operation.name,
            )
        except KeyError:
            return self._failure_result(
                PortableRuntimeFailureCode.RESOURCE_NOT_FOUND,
                "requested public record does not exist",
                operation=operation.name,
                details={"record_id": request.arguments.get("record_id")},
            )

        try:
            validate_json_instance(observation, operation.output_schema)
        except (SchemaValidationError, UnsupportedSchemaError) as exc:
            return self._failure_result(
                PortableRuntimeFailureCode.OUTPUT_SCHEMA_VIOLATION,
                "native operation observation violates the portable output schema",
                operation=operation.name,
                details={"path": getattr(exc, "path", "$output")},
            )
        return self._success_result(observation=observation)

    def _operation_input_schema(
        self,
        operation: PortableRuntimeOperation,
        arguments: Mapping[str, Any],
        *,
        permission_failure: bool,
    ) -> Any:
        if not permission_failure or operation.name != "search":
            return operation.input_schema

        schema = _thaw(operation.input_schema)
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            raise PortableRuntimeContractError(
                "search permission semantics require root properties"
            )
        system_schema = properties.get("system")
        if not isinstance(system_schema, dict):
            raise PortableRuntimeContractError(
                "search permission semantics require a system property schema"
            )
        system_schema.pop("enum", None)
        return schema

    def _invoke_operation(
        self,
        operation: PortableRuntimeOperation,
        arguments: Mapping[str, Any],
    ) -> Any:
        if operation.name == "search":
            return self._native.search(
                str(arguments["system"]),
                str(arguments["query"]),
                int(arguments.get("limit", 10)),
            )
        if operation.name == "search_all":
            return self._native.search_all(
                str(arguments["query"]),
                int(arguments.get("limit", 10)),
            )
        if operation.name == "open_record":
            return self._native.open_record(str(arguments["record_id"]))
        raise PortableRuntimeContractError(
            f"unsupported builtin operation: {operation.name!r}"
        )

    def _permission_failure_precedes_closed(
        self,
        operation: PortableRuntimeOperation,
        arguments: Mapping[str, Any],
    ) -> bool:
        if not operation.permission_check_precedes_open_check:
            return False
        if operation.name != "search":
            return False
        system = arguments.get("system")
        return (
            isinstance(system, str)
            and system not in self._contract.public.permitted_systems
        )

    def _mark_budget_exhausted(
        self,
        charges: tuple[PortableResourceCharge, ...],
    ) -> None:
        snapshot = self._native.budget_snapshot()
        used = {
            "cost": int(snapshot["spent"]),
            "tool_calls": int(snapshot["calls"]),
        }
        limits = {
            limit.resource: limit
            for limit in self._contract.private.budgets.limits
        }
        blocked: list[str] = []
        for charge in charges:
            limit = limits[charge.resource]
            current = used[charge.resource]
            if limit.exhaustion_rule == (
                "reject_if_post_charge_usage_gt_maximum"
            ):
                is_blocked = current + charge.amount > limit.maximum
            elif limit.exhaustion_rule == (
                "reject_if_current_usage_gte_maximum_before_charge"
            ):
                is_blocked = current >= limit.maximum
            else:
                raise PortableRuntimeContractError(
                    "unsupported budget exhaustion rule: "
                    f"{limit.exhaustion_rule!r}"
                )
            if is_blocked:
                blocked.append(charge.resource)
        if not blocked:
            blocked = [charge.resource for charge in charges]
        self._budget_exhaustion_resources = tuple(dict.fromkeys(blocked))
        self._truncated = True

    def _success_result(self, *, observation: Any) -> PortableStepResult:
        return PortableStepResult(
            observation=observation,
            reward=None,
            reward_components=None,
            terminated=self._terminated,
            truncated=self._truncated,
            state_digest=self.state_digest(),
            budget_status=self.budget_state(),
            failure=None,
        )

    def _failure_result(
        self,
        code: PortableRuntimeFailureCode,
        message: str,
        *,
        observation: Any = None,
        operation: str | None = None,
        action_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> PortableStepResult:
        return PortableStepResult(
            observation=observation,
            reward=None,
            reward_components=None,
            terminated=self._terminated,
            truncated=self._truncated,
            state_digest=self.state_digest(),
            budget_status=self.budget_state(),
            failure=PortableFailureStatus(
                code=code,
                message=message,
                operation=operation,
                action_name=action_name,
                retryable=False,
                details=details or {},
            ),
        )

    def _session_failure_result(
        self,
        *,
        operation: str | None = None,
        action_name: str | None = None,
    ) -> PortableStepResult:
        if self._truncated:
            code = PortableRuntimeFailureCode.EPISODE_TRUNCATED
            message = "portable runtime episode has already been truncated"
        else:
            code = PortableRuntimeFailureCode.EPISODE_TERMINATED
            message = "portable runtime episode has already terminated"
        return self._failure_result(
            code,
            message,
            operation=operation,
            action_name=action_name,
        )
