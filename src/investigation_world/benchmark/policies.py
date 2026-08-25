from __future__ import annotations

from typing import Any, Protocol

from investigation_world.core.models import InvestigationResult


PublicEpisode = dict[str, Any]


class PublicPolicy(Protocol):
    name: str

    def __call__(self, episode: PublicEpisode) -> InvestigationResult: ...


def _records(episode: PublicEpisode) -> list[dict[str, Any]]:
    return list(episode.get("records", []))


def _task(episode: PublicEpisode) -> dict[str, Any]:
    return dict(episode.get("task", {}))


class EmptyPolicy:
    name = "empty"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        return InvestigationResult()


class ConclusionOnlyPolicy:
    name = "conclusion_only"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        return InvestigationResult(
            conclusion="Investigation complete.",
            overall_confidence=1.0,
        )


class AlwaysAbstainPolicy:
    name = "always_abstain"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        return InvestigationResult(
            unknowns=["Insufficient evidence to determine the answer."],
            overall_confidence=0.0,
        )


class CiteEverythingPolicy:
    name = "cite_everything"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        return InvestigationResult(
            evidence=[{"record_id": record["record_id"]} for record in _records(episode)],
            overall_confidence=1.0,
        )


class ProjectionTrustPolicy:
    """Blindly trusts the divergent operational system projection."""

    name = "projection_trust"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        task = _task(episode)
        target_object_id = task.get("target_object_id")
        target_object_type = task.get("target_object_type")
        for record in _records(episode):
            if (
                record.get("record_type") != "system_projection"
                or record.get("object_id") != target_object_id
            ):
                continue
            fields = record.get("fields", {})
            if not fields:
                continue
            field_name, value = next(iter(fields.items()))
            return InvestigationResult(
                claims=[{
                    "object_type": target_object_type,
                    "object_id": target_object_id,
                    "field_name": field_name,
                    "value": value,
                }],
                evidence=[{"record_id": record["record_id"]}],
                overall_confidence=1.0,
            )
        return InvestigationResult()


class StuffingPolicy:
    """Copies every visible record field into the answer and cites every record."""

    name = "field_stuffing"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        claims: list[dict[str, Any]] = []
        evidence: list[dict[str, str]] = []
        for record in _records(episode):
            evidence.append({"record_id": record["record_id"]})
            for field_name, value in record.get("fields", {}).items():
                claims.append({
                    "object_type": record.get("object_type"),
                    "object_id": record.get("object_id"),
                    "field_name": field_name,
                    "value": value,
                })
        return InvestigationResult(
            claims=claims,
            evidence=evidence,
            overall_confidence=1.0,
        )


class PublicEvidenceReferencePolicy:
    """Small deterministic solver that reads only public, directly observable evidence."""

    name = "public_evidence_reference"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        task = _task(episode)
        task_type = task.get("task_type")
        target_id = task.get("target_object_id")
        target_type = task.get("target_object_type")

        if task_type == "INVESTIGATE_MISSING_SHIPMENT":
            record = next(
                (
                    item for item in _records(episode)
                    if item.get("record_type") == "carrier_manifest"
                    and item.get("object_id") == target_id
                ),
                None,
            )
            if record and "delivered_quantity" in record.get("fields", {}):
                return InvestigationResult(
                    claims=[{
                        "object_type": target_type,
                        "object_id": target_id,
                        "field_name": "delivered_quantity",
                        "value": record["fields"]["delivered_quantity"],
                    }],
                    evidence=[{"record_id": record["record_id"]}],
                    overall_confidence=1.0,
                )

        if task_type == "INVESTIGATE_DUPLICATE_INVOICE":
            record = next(
                (
                    item for item in _records(episode)
                    if item.get("record_type") == "supplier_submission"
                    and target_id in item.get("related_object_ids", [])
                    and str(item.get("fields", {}).get("submission_kind", "")).casefold()
                    == "resubmission"
                ),
                None,
            )
            if record:
                return InvestigationResult(
                    claims=[{
                        "object_type": target_type,
                        "object_id": target_id,
                        "field_name": "duplicate_status",
                        "value": "DUPLICATE",
                    }],
                    evidence=[{"record_id": record["record_id"]}],
                    overall_confidence=1.0,
                )

        if task_type == "INVESTIGATE_AUTHORITY_BREACH":
            record = next(
                (
                    item for item in _records(episode)
                    if item.get("record_type") == "policy_rule"
                    and item.get("object_id") == target_id
                ),
                None,
            )
            if record and "approval_limit_usd" in record.get("fields", {}):
                return InvestigationResult(
                    claims=[{
                        "object_type": target_type,
                        "object_id": target_id,
                        "field_name": "approval_limit_usd",
                        "value": record["fields"]["approval_limit_usd"],
                    }],
                    evidence=[{"record_id": record["record_id"]}],
                    overall_confidence=1.0,
                )

        return InvestigationResult(
            unknowns=["No direct evidence rule matched this task."],
            overall_confidence=0.0,
        )


DEFAULT_PUBLIC_POLICIES: tuple[PublicPolicy, ...] = (
    EmptyPolicy(),
    ConclusionOnlyPolicy(),
    AlwaysAbstainPolicy(),
    CiteEverythingPolicy(),
    ProjectionTrustPolicy(),
    StuffingPolicy(),
    PublicEvidenceReferencePolicy(),
)
