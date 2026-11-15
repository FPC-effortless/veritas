"""Private bridge to canonical TRAIN-001; never qualification or model execution.

Supplied diagnostic observations may be joined to supplied canonical records only
by exact point identity and complete per-member scores. This establishes internal
consistency, not authenticated model execution, scoring or chronology.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .runner import LabError
from .training_value_diagnostics import interpretation, score_by_id

PHASES = ("train_before", "train_after", "heldout_before", "heldout_after")


def _bytes(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > 16 * 1024 * 1024:
        raise LabError("private assessment exceeds 16 MiB limit")
    return raw


def point_identity(point):
    """Exact private EvaluationPoint identity, including lineage/checkpoint/scorer context."""
    return hashlib.sha256(_bytes(point.model_dump(mode="json"))).hexdigest()


@dataclass(frozen=True, repr=False)
class PrivateTrainingAssessment:
    """Explicit private export only; ordinary representations/projections withhold evidence."""

    _serialized: bytes

    def __repr__(self):
        return "PrivateTrainingAssessment(evaluator_private; evidence withheld)"

    def private_payload(self):
        return json.loads(self._serialized)

    def public_payload(self):
        return {"visibility": "evaluator_private", "withheld": True}

    def buyer_safe_payload(self):
        return self.public_payload()


def assess_private_training(report_payload, diagnostics=()):
    """Recompute a canonical report and join bounded four-way diagnostics privately.

    Each diagnostic uses v3's five phase records plus training_seed and an optional
    `canonical_binding`: run_id and a point_sha256 map for all four phases. Missing
    binding/phase/seed stays UNASSESSED; contradictions refuse. Legacy v3 reports
    cannot be upgraded by inventing missing identities. The routine never executes
    a model/scorer, opens a panel or signs/promotes a claim.
    """
    from investigation_world.training_qualification import TrainingReport, assess_training

    try:
        # A fresh parse invokes canonical nested validators even for model instances.
        supplied = (
            report_payload.model_dump(mode="json")
            if isinstance(report_payload, TrainingReport)
            else report_payload
        )
        parsed = TrainingReport.model_validate_json(_bytes(supplied))
        canonical = assess_training(parsed.evidence, policy=parsed.policy)
    except (ValueError, TypeError, KeyError) as exc:
        raise LabError("invalid private canonical training report") from exc
    if canonical.model_dump(mode="json") != parsed.model_dump(mode="json"):
        raise LabError("canonical training report did not recompute")
    if not isinstance(diagnostics, (list, tuple)) or len(diagnostics) > 32:
        raise LabError("at most 32 diagnostic seed records are supported")
    supplied_rows = {}
    for row in diagnostics:
        if not isinstance(row, dict) or type(row.get("training_seed")) is not int:
            raise LabError("diagnostic requires an explicit integer training seed")
        seed = row["training_seed"]
        if seed not in canonical.evidence.expected_seeds or seed in supplied_rows:
            raise LabError("unexpected or duplicated diagnostic seed")
        supplied_rows[seed] = row
    replicates = {rep.seed: rep for rep in canonical.evidence.replicates}
    rows = []
    for seed in canonical.evidence.expected_seeds:
        row, rep = supplied_rows.get(seed), replicates.get(seed)
        result = {
            "seed": seed,
            "status": "UNASSESSED",
            "diagnosis": None,
            "reason": "missing diagnostic or canonical replicate",
        }
        rows.append(result)
        if row is None or rep is None:
            continue
        if rep.train is None or rep.heldout is None:
            result["reason"] = "canonical four-way observations missing"
            continue
        points = dict(zip(PHASES, (*rep.train.points, *rep.heldout.points), strict=True))
        binding = row.get("canonical_binding")
        if binding is None:
            result["reason"] = "legacy or unbound diagnostics; exact point lineage unavailable"
            continue
        if (
            not isinstance(binding, dict)
            or set(binding) != {"run_id", "point_sha256"}
            or binding["run_id"] != rep.manifest.run_id
            or binding["point_sha256"] != {k: point_identity(v) for k, v in points.items()}
        ):
            raise LabError("diagnostic canonical point binding mismatch")
        if any(phase not in row for phase in PHASES):
            result["reason"] = "diagnostic four-way phases missing"
            continue
        if any(outcome.value is None for point in points.values() for outcome in point.outcomes):
            result["reason"] = "canonical unscored outcomes retained; no complete diagnosis"
            continue
        try:
            for phase, point in points.items():
                expected = {outcome.member_id: float(outcome.value) for outcome in point.outcomes}
                if score_by_id(row[phase]) != expected:
                    raise LabError("diagnostic member population or score mismatch")
            reference = row.get("reference_target_sanity")
            if reference is None:
                result["reason"] = "target sanity missing"
                continue
            diagnosis = interpretation(
                reference,
                *(row[phase] for phase in PHASES),
                minimum_reference_score=row.get("minimum_reference_score"),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise LabError("invalid or contradictory private diagnostic observations") from exc
        status = {
            "pipeline_sanity_unassessed": "UNASSESSED",
            "target_scorer_sanity_failed": "PIPELINE_INVALID",
        }.get(diagnosis["diagnosis"], "DIAGNOSTIC_SCORES_LINKED")
        result.update(
            status=status,
            diagnosis=diagnosis,
            reason="supplied records agree; scorer/model execution not independently verified",
        )
    payload = {
        "schema": "trainlab.private-training-assessment.v1",
        "visibility": "evaluator_private",
        "qualification": "NOT_QUALIFIED",
        "training_validated": False,
        "scientific_qualification": "NOT_QUALIFIED",
        "claim_promotion": "NOT_GRANTED",
        "canonical_report": canonical.model_dump(mode="json"),
        "canonical_status": canonical.status.value,
        "diagnostics": rows,
        "diagnostic_sources": list(diagnostics),
        "diagnostic_source_sha256": hashlib.sha256(_bytes(list(diagnostics))).hexdigest(),
        "providers": {
            "model_execution_and_chronology": "UNAVAILABLE",
            "memorization_and_contamination": "UNAVAILABLE",
            "independent_scorer_replay": "NOT_PERFORMED",
            "tiny_overfit_control": "NOT_PERFORMED_BY_THIS_ADAPTER",
        },
        "scope": "Consistency of supplied private records, not empirical or generalization proof",
    }
    return PrivateTrainingAssessment(_bytes(payload))


def verify_private_training_assessment(assessment):
    """Recompute a retained private assessment; never trust its declared status."""
    if not isinstance(assessment, PrivateTrainingAssessment):
        raise LabError("expected private training assessment")
    try:
        payload = assessment.private_payload()
        fresh = assess_private_training(payload["canonical_report"], payload["diagnostic_sources"])
    except (ValueError, TypeError, KeyError) as exc:
        raise LabError("invalid retained private assessment") from exc
    if fresh.private_payload() != payload:
        raise LabError("private assessment failed recomputation")
    return True
