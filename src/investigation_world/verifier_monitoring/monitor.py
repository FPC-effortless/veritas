from __future__ import annotations

from datetime import datetime
from typing import Any

from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    GateOutcome,
    VerifierIdentity,
)
from investigation_world.verifier_monitoring.models import (
    BuyerSafeExploitSummary,
    BuyerSafePublicFinding,
    DisclosureLevel,
    ExploitCorpus,
    ExploitDispositionStatus,
    ExploitMonitorGate,
    ExploitMonitorPolicy,
    ExploitMonitorReport,
    ExploitRegressionObservation,
    RegressionOutcome,
)


def _gate(
    name: str,
    outcome: GateOutcome,
    observed: Any,
    required: Any,
    detail: str,
) -> ExploitMonitorGate:
    return ExploitMonitorGate(
        name=name,
        outcome=outcome,
        observed=observed,
        required=required,
        detail=detail,
    )


def monitor_exploits(
    corpus: ExploitCorpus,
    *,
    environment_identity: EnvironmentIdentity,
    verifier_identity: VerifierIdentity,
    observations: tuple[ExploitRegressionObservation, ...]
    | list[ExploitRegressionObservation],
    generated_at: datetime,
    provenance: dict[str, Any],
    policy: ExploitMonitorPolicy | None = None,
) -> ExploitMonitorReport:
    cfg = policy or ExploitMonitorPolicy()
    if not provenance:
        raise ValueError("exploit monitoring requires provenance")

    applicable = tuple(
        finding
        for finding in corpus.findings
        if finding.applies_to(environment_identity, verifier_identity)
        and corpus.latest_disposition(finding.exploit_id).status
        != ExploitDispositionStatus.SUPERSEDED
    )
    applicable_ids = tuple(sorted(finding.exploit_id for finding in applicable))
    applicable_set = set(applicable_ids)

    by_exploit: dict[str, ExploitRegressionObservation] = {}
    for observation in observations:
        if observation.exploit_id not in applicable_set:
            raise ValueError(
                f"regression observation is not applicable to the target: {observation.exploit_id}"
            )
        if observation.exploit_id in by_exploit:
            raise ValueError(f"duplicate regression observation: {observation.exploit_id}")
        if observation.environment_identity != environment_identity:
            raise ValueError("regression observation environment identity mismatch")
        if observation.verifier_identity != verifier_identity:
            raise ValueError("regression observation verifier identity mismatch")
        by_exploit[observation.exploit_id] = observation

    missing = tuple(exploit_id for exploit_id in applicable_ids if exploit_id not in by_exploit)
    unknown = tuple(
        exploit_id
        for exploit_id, observation in by_exploit.items()
        if observation.outcome in {RegressionOutcome.ERROR, RegressionOutcome.NOT_RUN}
    )
    succeeded = tuple(
        exploit_id
        for exploit_id, observation in by_exploit.items()
        if observation.outcome == RegressionOutcome.SUCCEEDED
    )
    parity_failures = tuple(
        exploit_id
        for exploit_id, observation in by_exploit.items()
        if not observation.score_parity
    )
    severe_open = tuple(
        finding.exploit_id
        for finding in applicable
        if finding.severity.rank >= cfg.blocking_severity.rank
        and corpus.latest_disposition(finding.exploit_id).status
        == ExploitDispositionStatus.OPEN
    )

    coverage_outcome = (
        GateOutcome.UNKNOWN
        if missing or unknown
        else GateOutcome.PASS
    )
    regression_outcome = (
        GateOutcome.FAIL
        if succeeded
        else GateOutcome.UNKNOWN
        if missing or unknown
        else GateOutcome.PASS
    )
    severe_outcome = GateOutcome.FAIL if severe_open else GateOutcome.PASS
    parity_outcome = (
        GateOutcome.FAIL
        if parity_failures
        else GateOutcome.PASS
    )
    gates = (
        _gate(
            "applicable_exploit_replay_coverage",
            coverage_outcome,
            {"missing": list(missing), "unknown": list(unknown)},
            {"missing": [], "unknown": []},
            "every applicable known exploit requires target-version regression evidence",
        ),
        _gate(
            "known_exploit_regression_resistance",
            regression_outcome,
            list(succeeded),
            [],
            "an applicable exploit must not succeed against the target verifier",
        ),
        _gate(
            "unresolved_severe_exploits",
            severe_outcome,
            list(severe_open),
            [],
            "open high/critical exploits block verifier and training qualification evidence",
        ),
        _gate(
            "canonical_score_parity",
            parity_outcome,
            list(parity_failures),
            [],
            "monitoring observes canonical scores and must not change them",
        ),
    )
    status = (
        GateOutcome.FAIL
        if any(gate.outcome == GateOutcome.FAIL for gate in gates)
        else GateOutcome.UNKNOWN
        if any(gate.outcome == GateOutcome.UNKNOWN for gate in gates)
        else GateOutcome.PASS
    )
    return ExploitMonitorReport(
        policy_version=cfg.policy_version,
        corpus_id=corpus.corpus_id,
        environment_identity=environment_identity,
        verifier_identity=verifier_identity,
        applicable_exploit_ids=applicable_ids,
        observation_ids=tuple(
            by_exploit[exploit_id].observation_id
            for exploit_id in applicable_ids
            if exploit_id in by_exploit
        ),
        gates=gates,
        status=status,
        generated_at=generated_at,
        provenance=provenance,
    )


def buyer_safe_summary(
    corpus: ExploitCorpus,
    report: ExploitMonitorReport,
    observations: tuple[ExploitRegressionObservation, ...]
    | list[ExploitRegressionObservation],
) -> BuyerSafeExploitSummary:
    if report.corpus_id != corpus.corpus_id:
        raise ValueError("buyer-safe summary corpus does not match monitor report")
    observation_map: dict[str, ExploitRegressionObservation] = {}
    for observation in observations:
        if observation.exploit_id in observation_map:
            raise ValueError("buyer-safe summary received duplicate observations")
        if observation.environment_identity != report.environment_identity:
            raise ValueError("buyer-safe summary observation environment mismatch")
        if observation.verifier_identity != report.verifier_identity:
            raise ValueError("buyer-safe summary observation verifier mismatch")
        observation_map[observation.exploit_id] = observation
    if set(observation_map) - set(report.applicable_exploit_ids):
        raise ValueError("buyer-safe summary received a non-applicable observation")
    applicable = [
        finding
        for finding in corpus.findings
        if finding.exploit_id in set(report.applicable_exploit_ids)
    ]
    outcomes = {
        finding.exploit_id: (
            observation_map[finding.exploit_id].outcome
            if finding.exploit_id in observation_map
            else None
        )
        for finding in applicable
    }
    severe_gate = next(gate for gate in report.gates if gate.name == "unresolved_severe_exploits")
    severe_count = len(severe_gate.observed)
    return BuyerSafeExploitSummary(
        environment_id=report.environment_identity.environment_id,
        environment_version=report.environment_identity.environment_version,
        verifier_id=report.verifier_identity.verifier_id,
        verifier_version=report.verifier_identity.verifier_version,
        status=report.status,
        applicable_count=len(applicable),
        blocked_count=sum(outcome == RegressionOutcome.BLOCKED for outcome in outcomes.values()),
        active_count=sum(outcome == RegressionOutcome.SUCCEEDED for outcome in outcomes.values()),
        unknown_count=sum(
            outcome in {None, RegressionOutcome.ERROR, RegressionOutcome.NOT_RUN}
            for outcome in outcomes.values()
        ),
        severe_unresolved_count=severe_count,
        private_finding_count=sum(
            finding.disclosure != DisclosureLevel.PUBLIC for finding in applicable
        ),
        public_findings=tuple(
            BuyerSafePublicFinding(
                exploit_id=finding.exploit_id,
                exploit_class=finding.exploit_class,
                severity=finding.severity,
                outcome=outcomes[finding.exploit_id],
            )
            for finding in sorted(applicable, key=lambda item: item.exploit_id)
            if finding.disclosure == DisclosureLevel.PUBLIC
        ),
    )
