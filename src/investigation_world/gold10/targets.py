from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from investigation_world.trajectory import canonical_hash


@dataclass(frozen=True)
class HypothesisTarget:
    target_id: str
    role: str
    statement: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class UncertaintyTarget:
    target_id: str
    statement: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class CaseVerifierTargets:
    primary: HypothesisTarget
    alternative: HypothesisTarget
    uncertainty: UncertaintyTarget | None = None


_TARGETS: dict[str, CaseVerifierTargets] = {
    "2005-04-I-TX": CaseVerifierTargets(
        primary=HypothesisTarget(
            target_id="hypothesis:2005-04-I-TX:primary",
            role="primary",
            statement=(
                "A startup-related process upset involving overfill and hydrocarbon release "
                "is the leading working hypothesis for the Texas City explosion and fire."
            ),
            evidence_ids=("csb-preliminary-findings-2005-10-27",),
        ),
        alternative=HypothesisTarget(
            target_id="hypothesis:2005-04-I-TX:alternative",
            role="alternative",
            statement=(
                "A separate equipment-failure or ignition pathway not caused by startup "
                "overfill remains a plausible alternative explanation for the Texas City "
                "explosion and fire."
            ),
            evidence_ids=("csb-preliminary-findings-2005-10-27",),
        ),
    ),
    "2008-03-I-FL": CaseVerifierTargets(
        primary=HypothesisTarget(
            target_id="hypothesis:2008-03-I-FL:primary",
            role="primary",
            statement=(
                "A runaway reactive-chemical event in the production process is the leading "
                "working hypothesis for the T2 Laboratories explosion."
            ),
            evidence_ids=("csb-t2-deployment-2007-12-19",),
        ),
        alternative=HypothesisTarget(
            target_id="hypothesis:2008-03-I-FL:alternative",
            role="alternative",
            statement=(
                "A non-runaway initiating event such as an external fire or mechanical "
                "failure remains a plausible alternative pending later process evidence."
            ),
            evidence_ids=("csb-t2-deployment-2007-12-19",),
        ),
    ),
    "2008-05-I-GA": CaseVerifierTargets(
        primary=HypothesisTarget(
            target_id="hypothesis:2008-05-I-GA:primary",
            role="primary",
            statement=(
                "Combustible sugar dust participating in a primary explosion with secondary "
                "dust propagation is the leading working hypothesis for the Imperial Sugar "
                "event."
            ),
            evidence_ids=("csb-imperial-deployment-2008-02-08",),
        ),
        alternative=HypothesisTarget(
            target_id="hypothesis:2008-05-I-GA:alternative",
            role="alternative",
            statement=(
                "A non-dust initiating explosion followed by dust-fueled secondary "
                "propagation remains a plausible alternative for the Imperial Sugar event."
            ),
            evidence_ids=("csb-imperial-deployment-2008-02-08",),
        ),
    ),
    "2010-08-I-WA": CaseVerifierTargets(
        primary=HypothesisTarget(
            target_id="hypothesis:2010-08-I-WA:primary",
            role="primary",
            statement=(
                "A heat-exchanger integrity failure during startup is the leading working "
                "hypothesis for the Tesoro Anacortes explosion and fire."
            ),
            evidence_ids=("csb-tesoro-deployment-2010-04-02",),
        ),
        alternative=HypothesisTarget(
            target_id="hypothesis:2010-08-I-WA:alternative",
            role="alternative",
            statement=(
                "A startup process upset without a pre-existing heat-exchanger integrity "
                "failure remains a plausible alternative for the Tesoro Anacortes event."
            ),
            evidence_ids=("csb-tesoro-deployment-2010-04-02",),
        ),
    ),
    "2013-03-I-LA": CaseVerifierTargets(
        primary=HypothesisTarget(
            target_id="hypothesis:2013-03-I-LA:primary",
            role="primary",
            statement=(
                "Overpressure during a non-routine operation is the leading working "
                "hypothesis for the Williams Olefins equipment failure."
            ),
            evidence_ids=("csb-williams-deployment-2013-06-14",),
        ),
        alternative=HypothesisTarget(
            target_id="hypothesis:2013-03-I-LA:alternative",
            role="alternative",
            statement=(
                "A mechanical-integrity failure independent of non-routine overpressure "
                "remains a plausible alternative for the Williams Olefins event."
            ),
            evidence_ids=("csb-williams-deployment-2013-06-14",),
        ),
    ),
    "2017-08-I-TX": CaseVerifierTargets(
        primary=HypothesisTarget(
            target_id="hypothesis:2017-08-I-TX:primary",
            role="primary",
            statement=(
                "Flood-driven loss of safety infrastructure and refrigeration is the leading "
                "working hypothesis for the Arkema organic-peroxide fires."
            ),
            evidence_ids=("csb-arkema-investigation-statement-2017-08-31",),
        ),
        alternative=HypothesisTarget(
            target_id="hypothesis:2017-08-I-TX:alternative",
            role="alternative",
            statement=(
                "An initiating fire or equipment failure independent of flood-driven "
                "safeguard loss remains a plausible alternative for the Arkema event."
            ),
            evidence_ids=("csb-arkema-investigation-statement-2017-08-31",),
        ),
    ),
    "2012-03-I-CA": CaseVerifierTargets(
        primary=HypothesisTarget(
            target_id="hypothesis:2012-03-I-CA:primary",
            role="primary",
            statement=(
                "A process-pipe integrity failure causing the hydrocarbon release is the "
                "leading working hypothesis for the Chevron Richmond fire."
            ),
            evidence_ids=("csb-chevron-surveillance-2012-09-11",),
        ),
        alternative=HypothesisTarget(
            target_id="hypothesis:2012-03-I-CA:alternative",
            role="alternative",
            statement=(
                "A different process-equipment source causing the release remains a "
                "plausible alternative because the surveillance record alone does not "
                "establish the degradation mechanism."
            ),
            evidence_ids=("csb-chevron-surveillance-2012-09-11",),
        ),
        uncertainty=UncertaintyTarget(
            target_id="uncertainty:2012-03-I-CA:degradation-mechanism",
            statement=(
                "The surveillance evidence available at the frozen cut does not establish "
                "the degradation mechanism that caused the process-pipe failure."
            ),
            evidence_ids=("csb-chevron-surveillance-2012-09-11",),
        ),
    ),
    "2013-02-I-TX": CaseVerifierTargets(
        primary=HypothesisTarget(
            target_id="hypothesis:2013-02-I-TX:primary",
            role="primary",
            statement=(
                "A fire that escalated into the stored ammonium-nitrate inventory is the "
                "leading working hypothesis for the West Fertilizer explosion."
            ),
            evidence_ids=("csb-west-video-release-news-2013-05-03",),
        ),
        alternative=HypothesisTarget(
            target_id="hypothesis:2013-02-I-TX:alternative",
            role="alternative",
            statement=(
                "A different initiating mechanism within the fertilizer facility remains "
                "plausible because the early damage evidence does not establish the fire's "
                "origin."
            ),
            evidence_ids=("csb-west-video-release-news-2013-05-03",),
        ),
    ),
    "2018-02-I-WI": CaseVerifierTargets(
        primary=HypothesisTarget(
            target_id="hypothesis:2018-02-I-WI:primary",
            role="primary",
            statement=(
                "A transient-operation process upset that allowed incompatible process "
                "conditions is the leading working hypothesis for the Husky Superior "
                "refinery explosion."
            ),
            evidence_ids=("csb-husky-deployment-2018-04-26",),
        ),
        alternative=HypothesisTarget(
            target_id="hypothesis:2018-02-I-WI:alternative",
            role="alternative",
            statement=(
                "A discrete mechanical failure independent of the transient operation "
                "remains a plausible alternative pending later factual updates."
            ),
            evidence_ids=("csb-husky-deployment-2018-04-26",),
        ),
    ),
    "2019-04-I-PA": CaseVerifierTargets(
        primary=HypothesisTarget(
            target_id="hypothesis:2019-04-I-PA:primary",
            role="primary",
            statement=(
                "A loss of containment from refinery process equipment followed by ignition "
                "is the leading working hypothesis for the PES fire and explosions."
            ),
            evidence_ids=("csb-pes-deployment-2019-06-21",),
        ),
        alternative=HypothesisTarget(
            target_id="hypothesis:2019-04-I-PA:alternative",
            role="alternative",
            statement=(
                "An initiating fire or explosion preceding the major loss of containment "
                "remains a plausible alternative pending later evidence."
            ),
            evidence_ids=("csb-pes-deployment-2019-06-21",),
        ),
    ),
}


def _hypothesis_target_payload(target: HypothesisTarget) -> dict[str, Any]:
    return {
        "target_id": target.target_id,
        "role": target.role,
        "statement": target.statement,
        "evidence_ids": list(target.evidence_ids),
    }


def _uncertainty_target_payload(target: UncertaintyTarget) -> dict[str, Any]:
    return {
        "target_id": target.target_id,
        "statement": target.statement,
        "evidence_ids": list(target.evidence_ids),
    }


def verifier_target_contract_payload() -> dict[str, Any]:
    cases: dict[str, Any] = {}
    for case_id, targets in sorted(_TARGETS.items()):
        cases[case_id] = {
            "primary": _hypothesis_target_payload(targets.primary),
            "alternative": _hypothesis_target_payload(targets.alternative),
            "uncertainty": (
                None
                if targets.uncertainty is None
                else _uncertainty_target_payload(targets.uncertainty)
            ),
        }
    return {
        "schema_version": "veritas.gold10.verifier-targets.v1",
        "cases": cases,
    }


def verifier_target_contract_sha256() -> str:
    return canonical_hash(verifier_target_contract_payload())


def get_case_verifier_targets(case_id: str) -> CaseVerifierTargets:
    try:
        return _TARGETS[case_id]
    except KeyError as error:
        raise ValueError(f"missing Gold-10 verifier targets for {case_id}") from error


def validate_case_verifier_targets(
    case_id: str,
    available_evidence_ids: set[str],
    *,
    calibration_required: bool,
) -> CaseVerifierTargets:
    targets = get_case_verifier_targets(case_id)
    if targets.primary.role != "primary" or targets.alternative.role != "alternative":
        raise ValueError(f"Gold-10 verifier target role drift for {case_id}")
    if targets.primary.statement == targets.alternative.statement:
        raise ValueError(f"Gold-10 hypotheses must be distinct for {case_id}")
    for target in (targets.primary, targets.alternative):
        if not set(target.evidence_ids).issubset(available_evidence_ids):
            raise ValueError(
                f"Gold-10 hypothesis target cites unavailable evidence for {case_id}"
            )
    if calibration_required:
        if targets.uncertainty is None:
            raise ValueError(f"Gold-10 calibration target missing for {case_id}")
        if not set(targets.uncertainty.evidence_ids).issubset(available_evidence_ids):
            raise ValueError(
                f"Gold-10 uncertainty target cites unavailable evidence for {case_id}"
            )
    elif targets.uncertainty is not None:
        raise ValueError(f"unexpected Gold-10 uncertainty target for {case_id}")
    return targets
