from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import investigation_world.operational.verifier as operational_verifier_module
from investigation_world.operational.models import (
    ActionEvent,
    AssertionComparison,
    EpisodeSubmission,
    HiddenActionEffect,
    HiddenOracle,
    OperationalInvariant,
    StateAssertion,
    VerificationBreakdown,
)
from investigation_world.operational.verifier import verify_operational_episode
from investigation_world.portable_contract.compiler import (
    CONTRACT_SCHEMA_VERSION,
    SOURCE_VERIFIER_BLOB,
    VERIFIER_ENTRYPOINT,
    VERIFIER_SEMANTICS_ID,
)
from investigation_world.portable_contract.models import (
    PortableOperationalContract,
    PortableStateAssertion,
)
from investigation_world.trajectory.models import CanonicalModel, VerifierIdentity
from investigation_world.trajectory.reverify.models import OperationalReplayEvidence


class OperationalEvaluatorInput(CanonicalModel):
    oracle: HiddenOracle
    state: dict[str, Any]
    events: tuple[ActionEvent, ...]
    submission: EpisodeSubmission
    tool_calls: int
    cost_spent: int


def _state_assertion(assertion: PortableStateAssertion) -> StateAssertion:
    return StateAssertion(
        object_id=assertion.object_id,
        field_name=assertion.field_name,
        expected_value=copy.deepcopy(assertion.expected_value),
        tolerance=assertion.tolerance,
        comparison=AssertionComparison(assertion.comparison),
    )


def _resource_limit(
    contract: PortableOperationalContract,
    *,
    resource: str,
    unit: str,
) -> int:
    matches = [
        limit.maximum
        for limit in contract.private.budgets.limits
        if limit.resource == resource and limit.unit == unit
    ]
    if len(matches) != 1:
        raise ValueError(f"portable contract does not define exactly one {resource!r} limit")
    return matches[0]


def _oracle(contract: PortableOperationalContract) -> HiddenOracle:
    if contract.schema_version != CONTRACT_SCHEMA_VERSION:
        raise ValueError("unsupported portable operational contract schema version")

    semantic_state = contract.private.semantic_state
    invariants = [
        OperationalInvariant(
            invariant_id=item.invariant_id,
            description=item.description,
            assertion=_state_assertion(item.assertion),
            severity=item.severity,
            scope=item.scope,
        )
        for item in semantic_state.invariants
    ]
    effects = [
        HiddenActionEffect(
            action_name=item.action_name,
            required_parameters=copy.deepcopy(dict(item.required_parameters)),
            required_state=[_state_assertion(assertion) for assertion in item.required_state],
            required_prior_actions=list(item.required_prior_actions),
            set_state=copy.deepcopy(dict(item.set_state)),
            observable_result=copy.deepcopy(dict(item.observable_result)),
            blocked_observable_result=copy.deepcopy(dict(item.blocked_observable_result)),
            emitted_side_effects=list(item.emitted_side_effects),
            forbidden=item.forbidden,
            consequence_severity=item.consequence_severity,
        )
        for item in contract.private.transitions
    ]
    return HiddenOracle(
        task_id=contract.private.oracle_task_id,
        initial_state=copy.deepcopy(dict(semantic_state.initial_state)),
        target_state=[_state_assertion(item) for item in semantic_state.target_assertions],
        invariants=invariants,
        required_actions=list(contract.private.process.required_actions),
        required_action_order=list(contract.private.process.required_action_order),
        required_action_counts=dict(contract.private.process.required_action_counts),
        forbidden_actions=list(contract.private.process.forbidden_actions),
        required_evidence_ids=list(contract.private.required_evidence_ids),
        action_effects=effects,
        max_cost=_resource_limit(contract, resource="cost", unit="cost_units"),
        max_tool_calls=_resource_limit(contract, resource="tool_calls", unit="calls"),
        metadata=copy.deepcopy(dict(contract.private.oracle_metadata)),
    )


def evaluator_input_from_evidence(evidence: OperationalReplayEvidence) -> OperationalEvaluatorInput:
    return OperationalEvaluatorInput(
        oracle=_oracle(evidence.portable_contract),
        state=copy.deepcopy(evidence.final_state),
        events=tuple(item.model_copy(deep=True) for item in evidence.action_events),
        submission=evidence.submission.model_copy(deep=True),
        tool_calls=evidence.tool_calls,
        cost_spent=evidence.cost_spent,
    )


def _git_blob_sha1(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n")
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()


@dataclass(frozen=True)
class OperationalVerifierBinding:
    """A statically authorized local verifier binding; it never resolves arbitrary entrypoints."""

    identity: VerifierIdentity
    entrypoint: str
    semantics_id: str
    source_git_blob_sha1: str

    def __post_init__(self) -> None:
        if self.entrypoint != VERIFIER_ENTRYPOINT:
            raise ValueError("unsupported operational verifier entrypoint")
        if self.semantics_id != VERIFIER_SEMANTICS_ID:
            raise ValueError("unsupported operational verifier semantics identity")
        if self.source_git_blob_sha1 != SOURCE_VERIFIER_BLOB:
            raise ValueError("unsupported operational verifier source identity")
        if self.identity.verifier_id != self.entrypoint:
            raise ValueError("verifier identity must name the authorized local entrypoint")
        if self.identity.version != self.semantics_id:
            raise ValueError(
                "verifier version must exactly equal the authorized semantics identity"
            )

    def verify(self, evaluator_input: OperationalEvaluatorInput) -> VerificationBreakdown:
        verifier_path = Path(str(operational_verifier_module.__file__))
        if not verifier_path.is_file():
            raise RuntimeError("authorized verifier source file is unavailable")
        if _git_blob_sha1(verifier_path) != self.source_git_blob_sha1:
            raise RuntimeError("authorized verifier source identity mismatch")
        return verify_operational_episode(
            oracle=evaluator_input.oracle,
            state=copy.deepcopy(evaluator_input.state),
            events=[item.model_copy(deep=True) for item in evaluator_input.events],
            submission=evaluator_input.submission.model_copy(deep=True),
            tool_calls=evaluator_input.tool_calls,
            cost_spent=evaluator_input.cost_spent,
        )


def current_operational_verifier_binding() -> OperationalVerifierBinding:
    return OperationalVerifierBinding(
        identity=VerifierIdentity(
            verifier_id=VERIFIER_ENTRYPOINT,
            version=VERIFIER_SEMANTICS_ID,
        ),
        entrypoint=VERIFIER_ENTRYPOINT,
        semantics_id=VERIFIER_SEMANTICS_ID,
        source_git_blob_sha1=SOURCE_VERIFIER_BLOB,
    )


class AuthorizedVerifierRegistry:
    """Exact-match registry. Unregistered verifier versions are not treated as equivalent."""

    def __init__(self, bindings: tuple[OperationalVerifierBinding, ...]):
        self._bindings: dict[tuple[str | None, str | None], OperationalVerifierBinding] = {}
        for binding in bindings:
            if not isinstance(binding, OperationalVerifierBinding):
                raise TypeError("only statically authorized offline verifier bindings are accepted")
            key = (binding.identity.verifier_id, binding.identity.version)
            if key in self._bindings:
                raise ValueError("duplicate authorized verifier identity")
            self._bindings[key] = binding

    def resolve(self, identity: VerifierIdentity) -> OperationalVerifierBinding | None:
        return self._bindings.get((identity.verifier_id, identity.version))
