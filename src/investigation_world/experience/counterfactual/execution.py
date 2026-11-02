"""Execute one public financial repair intervention using the canonical Foundry executor.

ponytail: only the fixed v1 and two closed v2 public financial profiles are supported.
New profiles require public-at-cut and replay proof, not a generic executor/plugin interface.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from investigation_world.experience import ExperienceReference, MachineExperience
from investigation_world.experience_foundry.admission import (
    PublicTrainingRecorder,
    RecordedExperience,
    runtime_source_digest,
)
from investigation_world.experience_foundry.public_profiles import (
    profile_fixture,
    profile_id_from_trace,
)
from investigation_world.foundry.models import (
    CapabilityContract,
    CounterfactualBranch,
    RolloutTrace,
    stable_hash,
)
from investigation_world.foundry.tracing import execute_counterfactual, replay_trace_prefix
from investigation_world.trajectory import ReverificationRecord, VisibilityClass, canonical_hash
from investigation_world.trajectory.reverify import (
    REPLAY_EVIDENCE_PRIVATE_KEY,
    OperationalReplayEvidence,
)

from .validation import verify_recorded

SCHEMA = "veritas.counterfactual-experience.v1"
POLICY = "public-financial-formula-at-cut.v1"


class VerifiedExecution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    experience: MachineExperience
    companion: RolloutTrace
    capability: CapabilityContract
    verification: ReverificationRecord
    breakdown: dict[str, Any]
    semantic_fingerprint: str
    content_digest: str

    def recorded(self) -> RecordedExperience:
        return RecordedExperience(self.experience, self.companion, self.capability)


def _snapshot(source: RecordedExperience) -> VerifiedExecution:
    source, evidence, verification, breakdown = verify_recorded(source)
    # Exact native identities retain local artifact paths. Semantic equality deliberately
    # excludes those identities and artifact byte hashes (ZIP timestamps may differ).
    native = evidence.native_submission
    if native is None:
        raise ValueError("NATIVE_RECEIPT_REQUIRED")
    native_semantics = json.loads(native.verification_json)
    native_semantics.pop("artifact_hash")
    semantic = {
        "native_verification": native_semantics,
        "actions": [e.model_dump(mode="json") for e in evidence.action_events],
        "initial": evidence.initial_state,
        "final": evidence.final_state,
        "submission": evidence.submission.model_dump(mode="json"),
        "tool_calls": evidence.tool_calls,
        "cost": evidence.cost_spent,
        "breakdown": breakdown,
    }
    if profile_id_from_trace(source.companion) is not None:
        # v1 had exactly one task. New structures must not become semantic aliases
        # merely because one action sequence has the same state/outcome on both.
        semantic["profile_contract"] = canonical_hash(evidence.portable_contract)
    return VerifiedExecution(
        experience=source.experience,
        companion=source.companion,
        capability=source.capability,
        verification=verification,
        breakdown=breakdown,
        semantic_fingerprint=canonical_hash(semantic),
        content_digest=canonical_hash(
            {
                "experience": source.experience.model_dump(mode="json"),
                "companion": source.companion.model_dump(mode="json"),
                "capability": source.capability.model_dump(mode="json"),
            }
        ),
    )


def _evidence(execution: VerifiedExecution) -> OperationalReplayEvidence:
    return OperationalReplayEvidence.model_validate(
        execution.experience.trajectory.private_metadata[REPLAY_EVIDENCE_PRIVATE_KEY]
    )


def _calls(execution: VerifiedExecution) -> list[dict[str, Any]]:
    return [copy.deepcopy(e.payload) for e in execution.companion.events if e.event_type == "act"]


def _call_arguments(payload: dict[str, Any]) -> dict[str, Any]:
    return {"method": payload["method"], "args": payload["args"], "kwargs": payload["kwargs"]}


def _protocol(source: VerifiedExecution, step: int, replacement: dict[str, Any]):
    profile_id = profile_id_from_trace(source.companion)
    events = source.companion.events
    acts = [e for e in events if e.event_type == "act"]
    if [e.step for e in events] != list(range(len(events))):
        raise ValueError("NONCONTIGUOUS_STEPS_UNSUPPORTED")
    if [e.event_type for e in events] != ["act"] * len(acts) + ["native_submission", "submit"]:
        raise ValueError("REPLAY_EVENT_UNSUPPORTED")
    if type(step) is not int or not 0 <= step < len(acts):
        raise ValueError("DIVERGENCE_STEP_UNSUPPORTED")
    for i, event in enumerate(acts):
        p = event.payload
        if (
            p.get("method") != "act"
            or set(p) != {"method", "action_name", "args", "kwargs", "success"}
            or p["args"] != [p["action_name"]]
            or not isinstance(p["kwargs"], dict)
        ):
            raise ValueError("REPLAY_EVENT_UNSUPPORTED")
        # The divergence is explicitly executed, even if it failed. Foundry skips failed
        # replay events, so no failed untouched prefix/suffix may enter that helper.
        if profile_id is None and i != step and p["success"] is not True:
            raise ValueError("FAILED_UNTOUCHED_REPLAY_UNSUPPORTED")
    if acts[step].payload["args"] != ["repair_formula"]:
        raise ValueError("INTERVENTION_ACTION_UNSUPPORTED")
    case, _ = profile_fixture(profile_id)
    # This profile's records are immutable and exposed in public_payload before any act.
    # No oracle, future receipt, hidden target or suffix outcome selects the replacement.
    public = case.episode.public_payload()
    audits = [r for r in public["records"] if r["record_type"] == "formula_audit"]
    if len(audits) != 1:
        raise ValueError("PUBLIC_AUDIT_REQUIRED")
    audit = audits[0]
    formula = f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})"
    allowed = {formula, audit["fields"]["formula"], "=0"}
    if (
        set(replacement) != {"cell", "formula"}
        or replacement["cell"] != audit["object_id"]
        or not isinstance(replacement["formula"], str)
        or replacement["formula"] not in allowed
    ):
        raise ValueError("PUBLIC_INTERVENTION_UNSUPPORTED")
    evidence = _evidence(source)
    state = copy.deepcopy(evidence.initial_state)
    for action_event in evidence.action_events[:step]:
        state.update(copy.deepcopy(action_event.state_changes))
    visibility = {
        "policy": POLICY if profile_id is None else "public-financial-formula-at-cut.v2",
        "available_at_step": step,
        "public_payload_digest": canonical_hash(public),
        "record": audit,
        "record_digest": canonical_hash(audit),
    }
    return state, visibility


class CounterfactualExperience(MachineExperience):
    """Evaluator-private derivative; explicit refusal reinforces the canonical root gate."""

    def public_payload(self):
        raise ValueError("COUNTERFACTUAL_DERIVATIVE_IS_EVALUATOR_PRIVATE")

    def buyer_safe_payload(self):
        raise ValueError("COUNTERFACTUAL_DERIVATIVE_IS_EVALUATOR_PRIVATE")


class CounterfactualReceipt(BaseModel):
    """Private material evidence; model parsing alone does NOT validate execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[
        "veritas.counterfactual-experience.v1", "veritas.counterfactual-experience.v2"
    ] = (
        "veritas.counterfactual-experience.v1"
    )
    receipt_id: str
    visibility: Literal[VisibilityClass.EVALUATOR_PRIVATE] = VisibilityClass.EVALUATOR_PRIVATE
    execution_status: Literal["VERIFIED_SIMULATED_CONTRAST"] = "VERIFIED_SIMULATED_CONTRAST"
    causal_status: Literal["UNKNOWN"] = "UNKNOWN"
    training_usefulness: Literal["UNKNOWN"] = "UNKNOWN"
    source_digest: str
    recorder_version: Literal[
        "veritas.public-financial-training-recorder.v1",
        "veritas.public-financial-training-recorder.v2",
    ] = (
        "veritas.public-financial-training-recorder.v1"
    )
    runtime_source_digest: str
    branch: CounterfactualBranch
    source: VerifiedExecution
    baseline: VerifiedExecution
    alternative: VerifiedExecution
    repeated: VerifiedExecution
    public_at_cut: dict[str, Any]
    bindings: dict[str, Any]
    state_delta: dict[str, Any]
    outcome_delta: dict[str, Any]
    recovery_status: Literal["success", "failure"]
    preference: dict[str, Any]

    def public_payload(self) -> dict[str, Any]:
        # No source/receipt hashes, paths, branch values or evaluator fields are public.
        return {
            "schema_version": self.schema_version,
            "details": "evaluator_private",
            "causal_status": "UNKNOWN",
            "training_usefulness": "UNKNOWN",
        }

    def derived_experience(self, *, source: RecordedExperience) -> MachineExperience:
        validate_counterfactual_receipt(self, source=source)
        return CounterfactualExperience.model_validate(
            {
                **self.alternative.experience.model_dump(mode="python"),
                "visibility": VisibilityClass.EVALUATOR_PRIVATE,
                "derivation_references": (
                    ExperienceReference(
                        reference_id=self.source.experience.experience_id,
                        reference_type="counterfactual_source",
                        digest=self.source_digest,
                        visibility=VisibilityClass.EVALUATOR_PRIVATE,
                    ),
                    ExperienceReference(
                        reference_id=self.receipt_id,
                        reference_type=self.schema_version,
                        digest=canonical_hash(self.model_dump(mode="json")),
                        visibility=VisibilityClass.EVALUATOR_PRIVATE,
                    ),
                ),
            }
        )


def _assemble(source, baseline, alternative, repeated, step, replacement):
    state, visibility = _protocol(source, step, replacement)
    executions = (source, baseline, alternative, repeated)
    evidence = [_evidence(x) for x in executions]
    original_calls = _calls(source)
    expected = [_call_arguments(c) for c in original_calls]
    alternate_calls = copy.deepcopy(expected)
    alternate_calls[step] = {"method": "act", "args": ["repair_formula"], "kwargs": replacement}
    if [_call_arguments(c) for c in _calls(baseline)] != expected:
        raise ValueError("BASELINE_ACTION_MISMATCH")
    for execution in (alternative, repeated):
        if [_call_arguments(c) for c in _calls(execution)] != alternate_calls:
            raise ValueError("PREFIX_SUFFIX_INTERVENTION_MISMATCH")
    for item in evidence[1:]:
        if (
            item.portable_contract != evidence[0].portable_contract
            or item.initial_state != evidence[0].initial_state
            or item.submission != evidence[0].submission
        ):
            raise ValueError("CONTRACT_INITIAL_SUBMISSION_MISMATCH")
    if baseline.semantic_fingerprint != source.semantic_fingerprint:
        raise ValueError("BASELINE_SEMANTIC_MISMATCH")
    if alternative.semantic_fingerprint != repeated.semantic_fingerprint:
        raise ValueError("REPEATABILITY_MISMATCH")
    receipts = [e.native_submission for e in evidence]
    if len({r.receipt_id for r in receipts}) != 4:
        raise ValueError("INDEPENDENT_NATIVE_RECEIPTS_REQUIRED")
    branch_data = {
        "parent_trace_id": source.companion.trace_id,
        "branch_step": step,
        "snapshot_hash": stable_hash(state),
        "alternate_action": alternate_calls[step],
        "metadata": {"policy": visibility["policy"]},
    }
    branch = CounterfactualBranch(
        branch_id="CF-BRANCH-" + canonical_hash(branch_data), **branch_data
    )
    before, after = baseline.breakdown, alternative.breakdown
    delta = {
        key: {"baseline": before[key], "alternative": after[key]}
        for key in before
        if before[key] != after[key]
    }
    state_delta = {
        key: {
            "baseline": evidence[1].final_state.get(key),
            "alternative": evidence[2].final_state.get(key),
        }
        for key in sorted(set(evidence[1].final_state) | set(evidence[2].final_state))
        if evidence[1].final_state.get(key) != evidence[2].final_state.get(key)
    }
    violation_keys = (
        "invariant_violations",
        "process_violations",
        "forbidden_actions_taken",
        "missing_required_actions",
        "missing_evidence_ids",
    )
    success = (
        after["outcome"] == 1
        and after["target_assertions_total"] > 0
        and after["target_assertions_met"] == after["target_assertions_total"]
        and all(after[k] == [] for k in violation_keys)
    )
    # Candidate only: no training admission, causal proof, or agent capability deficit.
    preferred = "NONE"
    if success and after["target_assertions_met"] > before["target_assertions_met"]:
        preferred = "ALTERNATIVE"
    elif before["outcome"] > after["outcome"] and all(before[k] == [] for k in violation_keys):
        preferred = "BASELINE"
    payload = dict(
        schema_version=(
            SCHEMA if profile_id_from_trace(source.companion) is None
            else "veritas.counterfactual-experience.v2"
        ),
        recorder_version=source.companion.harness_version,
        source_digest=canonical_hash(source.experience.model_dump(mode="json")),
        runtime_source_digest=runtime_source_digest(),
        branch=branch,
        source=source,
        baseline=baseline,
        alternative=alternative,
        repeated=repeated,
        public_at_cut=visibility,
        bindings={
            "source_experience_id": source.experience.experience_id,
            "source_trajectory_id": source.experience.trajectory.trajectory_id,
            "source_companion_digest": canonical_hash(source.companion.model_dump(mode="json")),
            "capability": source.capability.model_dump(mode="json"),
            "portable_contract_id": evidence[0].portable_contract.contract_id,
            "initial_state_digest": evidence[0].initial_state_digest,
            "cut_state_digest": stable_hash(state),
            "prefix": expected[:step],
            "original_call": expected[step],
            "replacement_call": alternate_calls[step],
            "suffix": expected[step + 1 :],
            "submission": evidence[0].submission.model_dump(mode="json"),
            "native_receipt_ids": [r.receipt_id for r in receipts],
            "native_receipt_digests": [r.receipt_digest for r in receipts],
            "native_verifier": {
                "id": receipts[0].verifier_id,
                "version": receipts[0].verifier_version,
                "sources": receipts[0].artifact_sources,
            },
        },
        state_delta=state_delta,
        outcome_delta=delta,
        recovery_status="success" if success else "failure",
        preference={
            "status": "CANDIDATE_ONLY",
            "preferred": preferred,
            "rationale": (
                "Fresh verifier target counts and residual violations; not scalar reward alone"
            ),
            "baseline_reasons": {k: before[k] for k in violation_keys},
            "alternative_reasons": {k: after[k] for k in violation_keys},
            "target_counts": {
                "baseline": [before["target_assertions_met"], before["target_assertions_total"]],
                "alternative": [after["target_assertions_met"], after["target_assertions_total"]],
            },
        },
    )
    preliminary = CounterfactualReceipt(receipt_id="", **payload)
    return CounterfactualReceipt(
        **{
            **preliminary.model_dump(mode="python"),
            "receipt_id": "CF-RECEIPT-"
            + canonical_hash(preliminary.model_dump(mode="json", exclude={"receipt_id"})),
        }
    )


def validate_counterfactual_receipt(
    receipt: CounterfactualReceipt, *, source: RecordedExperience
) -> CounterfactualReceipt:
    """Freshly verify every retained artifact and recompute every nested binding/status.

    Caller must authorize access to the retained public-fixture artifacts. Content binding
    and repeatability are not cryptographic independent execution attestation.
    """
    receipt = CounterfactualReceipt.model_validate(receipt.model_dump(mode="json"))
    actual = _snapshot(source)
    if actual != receipt.source:
        raise ValueError("SOURCE_BINDING_MISMATCH")
    snapshots = [
        _snapshot(x.recorded()) for x in (receipt.baseline, receipt.alternative, receipt.repeated)
    ]
    expected = _assemble(
        actual,
        snapshots[0],
        snapshots[1],
        snapshots[2],
        receipt.branch.branch_step,
        receipt.branch.alternate_action.get("kwargs", {}),
    )
    if receipt.model_dump(mode="json") != expected.model_dump(mode="json"):
        raise ValueError("COUNTERFACTUAL_RECEIPT_BINDING_MISMATCH")
    return expected


def execute_counterfactual_experience(
    source: RecordedExperience,
    *,
    branch_step: int,
    replacement: dict[str, Any],
    artifact_root: str | Path,
) -> CounterfactualReceipt:
    """Actual baseline, alternative and independent repeat; never synthesize an outcome."""
    original = _snapshot(source)
    profile_id = profile_id_from_trace(original.companion)
    cut_state, public_at_cut = _protocol(original, branch_step, replacement)

    class CutRecorder(PublicTrainingRecorder):
        # Instrument the existing recorder at the actual cut, without another executor.
        def act(self, action_name, **parameters):
            if len(self.events) == branch_step:
                if (
                    self.runtime.state_snapshot() != cut_state
                    or canonical_hash(self.runtime.public_payload())
                    != public_at_cut["public_payload_digest"]
                ):
                    raise ValueError("ACTUAL_PUBLIC_CUT_MISMATCH")
            return super().act(action_name, **parameters)

    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=False)  # Never overwrite the source or another run.
    evidence = _evidence(original)
    trace = original.companion
    suffix = trace.model_copy(
        deep=True,
        update={
            "events": [e for e in trace.events if e.event_type == "act" and e.step > branch_step]
        },
    )
    original_kwargs = trace.events[branch_step].payload["kwargs"]
    results = []
    for label, params in [
        ("baseline", original_kwargs),
        ("alternative", replacement),
        ("repeated", replacement),
    ]:
        def factory():
            recorder = CutRecorder(root / label, profile_id=profile_id)
            if profile_id is not None:
                # Only verified deterministic native act events are admitted above.
                # Unlike legacy replay, execute blocked calls too: they consume budget,
                # retain violations and can affect whether later calls are permissible.
                for event in trace.events[:branch_step]:
                    recorder.act(
                        event.payload["action_name"], **copy.deepcopy(event.payload["kwargs"])
                    )
            return recorder

        replay_input = trace if profile_id is None else trace.model_copy(update={"events": []})
        recorder = execute_counterfactual(
            factory,
            replay_input,
            branch_step=branch_step,
            alternate_method="act",
            alternate_args=["repair_formula"],
            alternate_kwargs=copy.deepcopy(params),
        )
        if (
            recorder.contract != evidence.portable_contract
            or recorder.initial != evidence.initial_state
            or recorder.runtime_digest != trace.runtime_version
        ):
            raise ValueError("RUNTIME_INITIAL_CONTRACT_MISMATCH")
        if profile_id is None:
            replay_trace_prefix(recorder, suffix)
        else:
            for event in suffix.events:
                recorder.act(event.payload["action_name"], **copy.deepcopy(event.payload["kwargs"]))
        results.append(_snapshot(recorder.submit(evidence.submission.model_copy(deep=True))))
    return _assemble(
        original, results[0], results[1], results[2], branch_step, copy.deepcopy(replacement)
    )
