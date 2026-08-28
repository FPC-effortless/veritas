from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from re import fullmatch
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.evidence import EvidenceVisibility
from investigation_world.qualification.maturity import (
    MATURITY_ORDER,
    EnvironmentMaturity,
    MaturityRecord,
)
from investigation_world.qualification.quality_scorecard import EnvironmentQualityScorecard

CATALOG_SCHEMA_VERSION = "veritas.environment-catalog-entry.v1"
CATALOG_PUBLIC_SCHEMA_VERSION = "veritas.environment-catalog-public.v1"


class CatalogPresentationClass(StrEnum):
    EXPERIMENTAL = "EXPERIMENTAL"
    EXECUTABLE = "EXECUTABLE"
    QUALIFIED = "QUALIFIED"
    TRAINING_VALIDATED = "TRAINING_VALIDATED"
    COMMERCIAL = "COMMERCIAL"


class QualificationFacet(StrEnum):
    SCIENTIFIC = "scientific"
    FRONTIER = "frontier"
    TRAINING = "training"
    COMMERCIAL = "commercial"


class QualificationFacetState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class BuyerSafeReferenceKind(StrEnum):
    PACKAGE = "package"
    CONFORMANCE = "conformance"
    EXPERIENCE = "experience"
    FIDELITY = "fidelity"


class CatalogSort(StrEnum):
    MATURITY = "maturity"
    DOMAIN = "domain"
    ENVIRONMENT = "environment"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _validate_sha256(value: str, *, field_name: str) -> None:
    if fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _maturity_rank(value: EnvironmentMaturity) -> int:
    return MATURITY_ORDER.index(value)


class BuyerSafeReference(BaseModel):
    """Opaque public reference suitable for catalog presentation.

    Locators and payloads are deliberately absent. The reference can identify a package,
    conformance certificate, experience classification, or fidelity classification without
    carrying evaluator-private paths or contents.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: BuyerSafeReferenceKind
    identity: str = Field(min_length=1)
    version: str | None = None
    content_sha256: str
    visibility: EvidenceVisibility = EvidenceVisibility.PUBLIC

    @model_validator(mode="after")
    def validate_reference(self) -> "BuyerSafeReference":
        if self.visibility != EvidenceVisibility.PUBLIC:
            raise ValueError("catalog buyer-safe references must be PUBLIC")
        if fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@+-]*", self.identity) is None:
            raise ValueError("buyer-safe reference identity must be opaque and locator-free")
        _validate_sha256(self.content_sha256, field_name="buyer-safe reference content_sha256")
        return self


class CatalogClassification(BaseModel):
    """Future-provider classification bound to a public content identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str = Field(min_length=1)
    reference: BuyerSafeReference

    @model_validator(mode="after")
    def validate_value(self) -> "CatalogClassification":
        if fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", self.value) is None:
            raise ValueError("catalog classification value must be a compact token")
        return self


class QualificationFacetAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    facet: QualificationFacet
    state: QualificationFacetState


_FACET_TARGETS: dict[QualificationFacet, EnvironmentMaturity] = {
    QualificationFacet.SCIENTIFIC: EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED,
    QualificationFacet.FRONTIER: EnvironmentMaturity.FRONTIER_QUALIFIED,
    QualificationFacet.TRAINING: EnvironmentMaturity.TRAINING_VALIDATED,
    QualificationFacet.COMMERCIAL: EnvironmentMaturity.COMMERCIAL_RELEASE,
}


def _presentation_class(status: EnvironmentMaturity) -> CatalogPresentationClass:
    if status == EnvironmentMaturity.DRAFT:
        return CatalogPresentationClass.EXPERIMENTAL
    if status in {
        EnvironmentMaturity.EXECUTABLE,
        EnvironmentMaturity.VERIFIER_VALIDATED,
    }:
        return CatalogPresentationClass.EXECUTABLE
    if status in {
        EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED,
        EnvironmentMaturity.FRONTIER_QUALIFIED,
    }:
        return CatalogPresentationClass.QUALIFIED
    if status == EnvironmentMaturity.TRAINING_VALIDATED:
        return CatalogPresentationClass.TRAINING_VALIDATED
    return CatalogPresentationClass.COMMERCIAL


def _required_gates_through(
    record: MaturityRecord, target: EnvironmentMaturity
) -> tuple[str, ...]:
    target_index = _maturity_rank(target)
    return tuple(
        gate
        for status in MATURITY_ORDER[: target_index + 1]
        for gate in record.qualification_policy_requirements[status]
    )


def _facet_state(
    record: MaturityRecord, facet: QualificationFacet
) -> QualificationFacetState:
    target = _FACET_TARGETS[facet]
    if _maturity_rank(record.status) >= _maturity_rank(target):
        return QualificationFacetState.PASS
    if _maturity_rank(record.target_status) < _maturity_rank(target):
        return QualificationFacetState.UNKNOWN
    if set(record.failed_gates).intersection(_required_gates_through(record, target)):
        return QualificationFacetState.FAIL
    return QualificationFacetState.UNKNOWN


def _expected_facets(record: MaturityRecord) -> tuple[QualificationFacetAssessment, ...]:
    return tuple(
        QualificationFacetAssessment(facet=facet, state=_facet_state(record, facet))
        for facet in QualificationFacet
    )


def _validated_maturity(record: MaturityRecord) -> MaturityRecord:
    return MaturityRecord.model_validate(record.model_dump(mode="python"))


def _validated_scorecard(scorecard: EnvironmentQualityScorecard) -> EnvironmentQualityScorecard:
    return EnvironmentQualityScorecard.model_validate(scorecard.model_dump(mode="python"))


class CatalogEntry(BaseModel):
    """Truthful catalog projection over canonical qualification authorities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CATALOG_SCHEMA_VERSION
    catalog_entry_id: str = ""
    catalog_content_sha256: str = ""
    domain: str
    maturity_record: MaturityRecord
    quality_scorecard: EnvironmentQualityScorecard
    presentation_class: CatalogPresentationClass | None = None
    qualification_facets: tuple[QualificationFacetAssessment, ...] = ()
    experience_maturity: CatalogClassification | None = None
    fidelity: CatalogClassification | None = None
    limitations: tuple[str, ...] = ()
    buyer_safe_references: tuple[BuyerSafeReference, ...] = ()

    @model_validator(mode="after")
    def validate_entry(self) -> "CatalogEntry":
        if self.schema_version != CATALOG_SCHEMA_VERSION:
            raise ValueError("unsupported catalog entry schema version")
        if fullmatch(r"[a-z][a-z0-9_.-]*", self.domain) is None:
            raise ValueError("catalog domain must be a lowercase namespaced token")

        maturity = _validated_maturity(self.maturity_record)
        scorecard = _validated_scorecard(self.quality_scorecard)
        environment = maturity.environment_identity
        verifier = maturity.verifier_identity
        score_environment = scorecard.context.environment
        score_verifier = scorecard.context.verifier
        if (
            score_environment.subject_id != environment.environment_id
            or score_environment.version != environment.environment_version
            or score_environment.content_sha256 != environment.content_sha256
        ):
            raise ValueError("quality scorecard belongs to a different environment version")
        if (
            score_verifier.subject_id != verifier.verifier_id
            or score_verifier.version != verifier.verifier_version
            or score_verifier.content_sha256 != verifier.content_sha256
        ):
            raise ValueError("quality scorecard belongs to a different verifier version")

        expected_presentation = _presentation_class(maturity.status)
        if self.presentation_class is not None and self.presentation_class != expected_presentation:
            raise ValueError("catalog presentation class does not match canonical maturity")
        expected_facets = _expected_facets(maturity)
        if self.qualification_facets and self.qualification_facets != expected_facets:
            raise ValueError(
                "catalog qualification facets do not match canonical maturity evidence"
            )

        if self.experience_maturity is not None and (
            self.experience_maturity.reference.kind != BuyerSafeReferenceKind.EXPERIENCE
        ):
            raise ValueError("experience maturity must use an experience reference")
        if self.fidelity is not None and (
            self.fidelity.reference.kind != BuyerSafeReferenceKind.FIDELITY
        ):
            raise ValueError("fidelity must use a fidelity reference")

        limitations = tuple(sorted(item.strip() for item in self.limitations if item.strip()))
        if len(limitations) != len(set(limitations)):
            raise ValueError("catalog limitations must be unique")
        if len(limitations) != len(self.limitations):
            raise ValueError("catalog limitations must be non-empty strings")

        references = tuple(
            sorted(
                self.buyer_safe_references,
                key=lambda item: (
                    item.kind.value,
                    item.identity,
                    item.version or "",
                    item.content_sha256,
                ),
            )
        )
        reference_keys = {
            (item.kind, item.identity, item.version, item.content_sha256) for item in references
        }
        if len(reference_keys) != len(references):
            raise ValueError("catalog buyer-safe references must be unique")

        object.__setattr__(self, "maturity_record", maturity)
        object.__setattr__(self, "quality_scorecard", scorecard)
        object.__setattr__(self, "presentation_class", expected_presentation)
        object.__setattr__(self, "qualification_facets", expected_facets)
        object.__setattr__(self, "limitations", limitations)
        object.__setattr__(self, "buyer_safe_references", references)

        payload = {
            "schema_version": self.schema_version,
            "domain": self.domain,
            "maturity_record_id": maturity.record_id,
            "qualification_identity": maturity.qualification_identity,
            "quality_scorecard_id": scorecard.scorecard_id,
            "quality_scorecard_content_sha256": scorecard.scorecard_content_sha256,
            "presentation_class": expected_presentation.value,
            "qualification_facets": [item.model_dump(mode="json") for item in expected_facets],
            "experience_maturity": (
                self.experience_maturity.model_dump(mode="json")
                if self.experience_maturity
                else None
            ),
            "fidelity": self.fidelity.model_dump(mode="json") if self.fidelity else None,
            "limitations": list(limitations),
            "buyer_safe_references": [item.model_dump(mode="json") for item in references],
        }
        digest = _canonical_sha256(payload)
        identifier = f"CAT-{digest[:24].upper()}"
        if self.catalog_content_sha256 and self.catalog_content_sha256 != digest:
            raise ValueError("catalog entry digest does not match immutable contents")
        if self.catalog_entry_id and self.catalog_entry_id != identifier:
            raise ValueError("catalog entry ID does not match immutable contents")
        object.__setattr__(self, "catalog_content_sha256", digest)
        object.__setattr__(self, "catalog_entry_id", identifier)
        return self


class CatalogQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    domains: tuple[str, ...] = ()
    minimum_maturity: EnvironmentMaturity | None = None
    fidelity_levels: tuple[str, ...] = ()
    sort_by: CatalogSort = CatalogSort.ENVIRONMENT
    descending: bool = False

    @model_validator(mode="after")
    def normalize_query(self) -> "CatalogQuery":
        domains = tuple(sorted(set(self.domains)))
        if any(fullmatch(r"[a-z][a-z0-9_.-]*", item) is None for item in domains):
            raise ValueError("catalog query domains must be lowercase namespaced tokens")
        fidelity_levels = tuple(sorted(set(self.fidelity_levels)))
        object.__setattr__(self, "domains", domains)
        object.__setattr__(self, "fidelity_levels", fidelity_levels)
        return self


def _validated_entry(entry: CatalogEntry) -> CatalogEntry:
    """Re-establish nested and derived invariants at every external catalog boundary."""
    return CatalogEntry.model_validate(entry.model_dump(mode="python"))


def apply_catalog_query(
    entries: Iterable[CatalogEntry], query: CatalogQuery | None = None
) -> tuple[CatalogEntry, ...]:
    active_query = query or CatalogQuery()
    validated = tuple(_validated_entry(entry) for entry in entries)
    filtered = tuple(
        entry
        for entry in validated
        if (not active_query.domains or entry.domain in active_query.domains)
        and (
            active_query.minimum_maturity is None
            or _maturity_rank(entry.maturity_record.status)
            >= _maturity_rank(active_query.minimum_maturity)
        )
        and (
            not active_query.fidelity_levels
            or (
                entry.fidelity is not None
                and entry.fidelity.value in active_query.fidelity_levels
            )
        )
    )

    def sort_key(entry: CatalogEntry) -> tuple[Any, ...]:
        environment = entry.maturity_record.environment_identity
        tie_breaker = (environment.environment_id, environment.environment_version)
        if active_query.sort_by == CatalogSort.MATURITY:
            return (_maturity_rank(entry.maturity_record.status), *tie_breaker)
        if active_query.sort_by == CatalogSort.DOMAIN:
            return (entry.domain, *tie_breaker)
        return tie_breaker

    return tuple(sorted(filtered, key=sort_key, reverse=active_query.descending))


def _public_entry(entry: CatalogEntry) -> dict[str, Any]:
    maturity = entry.maturity_record
    scorecard = entry.quality_scorecard
    environment = maturity.environment_identity
    presentation = entry.presentation_class
    if presentation is None:
        raise ValueError("validated catalog entry is missing a presentation class")
    return {
        "catalog_entry_id": entry.catalog_entry_id,
        "catalog_content_sha256": entry.catalog_content_sha256,
        "environment": environment.model_dump(mode="json"),
        "domain": entry.domain,
        "maturity": maturity.status.value,
        "maturity_record_id": maturity.record_id,
        "qualification_identity": maturity.qualification_identity,
        "presentation_class": presentation.value,
        "qualification_facets": {
            item.facet.value: item.state.value for item in entry.qualification_facets
        },
        "quality_scorecard": {
            "scorecard_id": scorecard.scorecard_id,
            "content_sha256": scorecard.scorecard_content_sha256,
            "policy_id": scorecard.policy_id,
            "policy_version": scorecard.policy_version,
            "dimensions": {
                item.dimension.value: item.outcome.value for item in scorecard.dimensions
            },
            "failed_dimensions": [item.value for item in scorecard.failed_dimensions],
            "unknown_dimensions": [item.value for item in scorecard.unknown_dimensions],
        },
        "experience_maturity": (
            entry.experience_maturity.model_dump(mode="json")
            if entry.experience_maturity
            else None
        ),
        "fidelity": entry.fidelity.model_dump(mode="json") if entry.fidelity else None,
        "limitations": list(entry.limitations),
        "references": [item.model_dump(mode="json") for item in entry.buyer_safe_references],
    }


def serialize_buyer_safe_catalog(
    entries: Iterable[CatalogEntry], query: CatalogQuery | None = None
) -> bytes:
    selected = apply_catalog_query(entries, query)
    payload = {
        "schema_version": CATALOG_PUBLIC_SCHEMA_VERSION,
        "entries": [_public_entry(entry) for entry in selected],
    }
    return _canonical_bytes(payload)
