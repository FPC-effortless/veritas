from __future__ import annotations

import hashlib
import tempfile
from collections import Counter, defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.operational.distribution import OperationalDistributionCase
from investigation_world.operational.models import EpisodeSubmission, WorldDomain
from investigation_world.operational.native_runtime import NativeOperationalRuntime


class NativeArtifactCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    domain: str
    split: str
    engine: str
    artifact_hash: str
    native_valid: bool
    state_score: float
    outcome_score: float
    overall_reward: float
    checks: dict[str, bool] = Field(default_factory=dict)


class NativeArtifactValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    cases_sampled: int
    expected_coverage: int
    domain_split_coverage: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    cases: list[NativeArtifactCaseResult] = Field(default_factory=list)


def _selection_index(domain: str, split: str, seed: int, size: int) -> int:
    digest = hashlib.sha256(f"{domain}|{split}|{seed}|native-validation-v1".encode()).hexdigest()
    return int(digest[:12], 16) % size


def _execute_oracle_procedure(runtime: NativeOperationalRuntime) -> list[str]:
    episode = runtime.episode
    errors: list[str] = []
    executed: Counter[str] = Counter()
    ordered_plan = list(episode.oracle.required_action_order)
    for action in episode.oracle.required_actions:
        if action not in ordered_plan:
            ordered_plan.append(action)

    for action_name in ordered_plan:
        required_count = max(
            1 if action_name in episode.oracle.required_actions else 0,
            episode.oracle.required_action_counts.get(action_name, 0),
        )
        remaining = max(0, required_count - executed[action_name])
        effects = [
            effect
            for effect in episode.oracle.action_effects
            if effect.action_name == action_name
        ]
        if remaining and not effects:
            errors.append(f"{action_name}: required action has no evaluator transition")
            continue
        for offset in range(remaining):
            effect = effects[min(executed[action_name] + offset, len(effects) - 1)]
            try:
                runtime.act(action_name, **dict(effect.required_parameters))
            except Exception as exc:  # evaluator validation should report the exact failed step
                errors.append(f"{action_name}: {type(exc).__name__}: {exc}")
                break
            event = runtime.events[-1]
            if event.blocked or not event.effect_applied:
                errors.append(
                    f"{action_name}: evaluator procedure was blocked ({event.blocked_reason or 'unknown'})"
                )
                break
        executed[action_name] += remaining
    return errors


def validate_native_artifact_distribution(
    cases: list[OperationalDistributionCase],
    *,
    seed: int = 42,
) -> NativeArtifactValidationReport:
    """Materialize and verify one deterministic case per domain × split cell.

    This is an evaluator-only release gate. It intentionally samples native bytes
    rather than materializing all 4,480 episodes, while the ordinary distribution
    validator continues to check descriptors and lineage for every case.
    """

    grouped: dict[tuple[str, str], list[OperationalDistributionCase]] = defaultdict(list)
    for case in cases:
        grouped[(case.episode.task.domain.value, case.split.value)].append(case)

    expected_keys = {
        (domain.value, split)
        for domain in WorldDomain
        for split in ("train", "iid_test", "ood", "adversarial")
    }
    errors: list[str] = []
    results: list[NativeArtifactCaseResult] = []
    coverage: dict[str, list[str]] = defaultdict(list)

    missing = sorted(expected_keys - set(grouped))
    if missing:
        errors.extend(f"missing native validation cell: {domain}/{split}" for domain, split in missing)

    for domain, split in sorted(expected_keys & set(grouped)):
        candidates = sorted(grouped[(domain, split)], key=lambda case: case.episode.task.task_id)
        selected = candidates[_selection_index(domain, split, seed, len(candidates))]
        episode = selected.episode
        descriptor = episode.task.metadata.get("native_artifact", {})
        with tempfile.TemporaryDirectory(prefix=f"veritas-native-{domain[:8]}-") as root:
            runtime = NativeOperationalRuntime(episode, artifact_root=root)
            procedure_errors = _execute_oracle_procedure(runtime)
            if procedure_errors:
                errors.extend(
                    f"{episode.task.task_id}: {item}" for item in procedure_errors
                )
                continue
            try:
                native = runtime.artifact_verification()
                verification = runtime.submit(
                    EpisodeSubmission(
                        conclusion="evaluator native-artifact release validation",
                        evidence_ids=list(episode.oracle.required_evidence_ids),
                        confidence=1.0,
                    )
                )
            except Exception as exc:
                errors.append(
                    f"{episode.task.task_id}: native verification {type(exc).__name__}: {exc}"
                )
                continue

            case_valid = (
                native.valid
                and verification.state == 1.0
                and verification.outcome == 1.0
                and not any(
                    item.startswith("native_artifact:")
                    for item in verification.process_violations
                )
            )
            if not case_valid:
                errors.append(
                    f"{episode.task.task_id}: native artifact or shared verifier did not fully pass"
                )
            coverage[domain].append(split)
            results.append(
                NativeArtifactCaseResult(
                    task_id=episode.task.task_id,
                    domain=domain,
                    split=split,
                    engine=str(descriptor.get("engine", runtime.artifact_descriptor()["engine"])),
                    artifact_hash=native.artifact_hash,
                    native_valid=native.valid,
                    state_score=verification.state,
                    outcome_score=verification.outcome,
                    overall_reward=verification.overall_reward,
                    checks=native.checks,
                )
            )

    normalized_coverage = {
        domain: sorted(splits)
        for domain, splits in sorted(coverage.items())
    }
    return NativeArtifactValidationReport(
        valid=not errors and len(results) == len(expected_keys),
        cases_sampled=len(results),
        expected_coverage=len(expected_keys),
        domain_split_coverage=normalized_coverage,
        errors=errors,
        cases=results,
    )
