"""Content-bound evidence contracts, not capability or causal qualification gates."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from investigation_world.experience import ExperienceReference
from investigation_world.foundry.models import (
    CapabilityContract,
    capability_contract_digest_payload,
)
from investigation_world.observatory.capability_graph import (
    CapabilityEdge,
    CapabilityGraph,
    CapabilityNode,
)
from investigation_world.trajectory import VisibilityClass, canonical_hash

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def _payload(value: Any) -> Any:
    """Legacy frozen models still contain mutable containers; reparse the whole tree."""
    if isinstance(value, BaseModel):
        return _payload(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _payload(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_payload(child) for child in value]
    if isinstance(value, tuple):
        return tuple(_payload(child) for child in value)
    return value


def validate_references(references: tuple[ExperienceReference, ...]) -> None:
    if not references:
        raise ValueError("evidence references required")
    for ref in references:
        digest = ref.digest or ""
        if (
            not ref.reference_id.strip()
            or not ref.reference_type.strip()
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise ValueError("evidence requires nonblank identity and full SHA256 digest")


def _visible(value: Any, allowed: set[VisibilityClass]) -> bool:
    if isinstance(value, BaseModel):
        if getattr(value, "visibility", VisibilityClass.PUBLIC) not in allowed:
            return False
        return _visible(value.model_dump(mode="python"), allowed)
    if isinstance(value, dict):
        if "visibility" in value and value["visibility"] not in allowed:
            return False
        return all(
            not child
            if key in {"private_metadata", "private_payload"}
            else _visible(child, allowed)
            for key, child in value.items()
        )
    if isinstance(value, (tuple, list)):
        return all(_visible(child, allowed) for child in value)
    return True


class ScienceRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", allow_inf_nan=False
    )
    record_id: str = ""
    visibility: VisibilityClass = VisibilityClass.INTERNAL

    @model_validator(mode="before")
    @classmethod
    def reparse(cls, value: Any) -> Any:
        return _payload(value)

    @model_validator(mode="after")
    def bind_record(self) -> Self:
        expected = (
            type(self).__name__
            + "-"
            + canonical_hash(self.model_dump(mode="json", exclude={"record_id"}))
        )
        if self.record_id and self.record_id != expected:
            raise ValueError("record identity does not match full evidence payload")
        object.__setattr__(self, "record_id", expected)
        return self

    def checked(self) -> Self:
        return type(self).model_validate(self.model_dump(mode="python"))

    def _projection(self, allowed: set[VisibilityClass]) -> dict[str, Any]:
        checked = self.checked()
        if not _visible(checked, allowed):
            return {"status": "UNKNOWN", "reason": "evidence_not_visible"}
        return checked.model_dump(mode="json")

    def public_payload(self) -> dict[str, Any]:
        return self._projection({VisibilityClass.PUBLIC})

    def buyer_safe_payload(self) -> dict[str, Any]:
        # ponytail: whole-record withholding; partial declassification needs its own proof.
        return self._projection({VisibilityClass.PUBLIC, VisibilityClass.BUYER_SAFE})


class CapabilitySpec(ScienceRecord):
    schema_version: Literal["veritas.capability-spec.v1"] = "veritas.capability-spec.v1"
    contract: CapabilityContract

    @model_validator(mode="after")
    def validate_declaration(self) -> Self:
        if not all(
            (
                self.contract.capability_id.strip(),
                self.contract.version.strip(),
                self.contract.objective.strip(),
            )
        ):
            raise ValueError("capability declaration requires identity, version and objective")
        return self

    @property
    def contract_digest(self) -> str:
        """Full canonical content, in addition to the provider's truncated digest."""
        return canonical_hash(capability_contract_digest_payload(self.checked().contract))


class PrerequisiteIntervention(ScienceRecord):
    """An externally reported paired study, not independently attested execution.

    The fixed-context commitment covers model, environment, verifier, population
    and metric. Its references must be inspected by the empirical qualification
    program; digest presence alone cannot verify that the study happened.
    """

    schema_version: Literal["veritas.prerequisite-intervention.v1"] = (
        "veritas.prerequisite-intervention.v1"
    )
    prerequisite: Text
    dependent: Text
    fixed_context_digest: Digest
    protocol_reference: ExperienceReference
    with_prerequisite_reference: ExperienceReference
    without_prerequisite_reference: ExperienceReference
    with_prerequisite_score: float = Field(ge=0, le=1)
    without_prerequisite_score: float = Field(ge=0, le=1)
    replicates: int = Field(ge=2, strict=True)
    provenance: Literal["EXTERNALLY_REPORTED"] = "EXTERNALLY_REPORTED"
    causal_qualification: Literal["UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def check_controls(self) -> Self:
        refs = (
            self.protocol_reference,
            self.with_prerequisite_reference,
            self.without_prerequisite_reference,
        )
        validate_references(refs)
        if len({r.reference_id for r in refs}) != 3 or len({r.digest for r in refs}) != 3:
            raise ValueError("intervention protocol and both controls must be distinct")
        if self.prerequisite == self.dependent:
            raise ValueError("intervention cannot use the dependent as its prerequisite")
        return self

    @property
    def reported_difference(self) -> float:
        checked = self.checked()
        return checked.with_prerequisite_score - checked.without_prerequisite_score


class PrerequisiteClaim(ScienceRecord):
    schema_version: Literal["veritas.prerequisite-claim.v1"] = "veritas.prerequisite-claim.v1"
    prerequisite: Text
    dependent: Text
    status: Literal[
        "HYPOTHESIZED",
        "OBSERVED_ASSOCIATION",
        "INTERVENTION_SUPPORT_REPORTED",
        "REFUTED",
        "INCONCLUSIVE",
    ] = "HYPOTHESIZED"
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)
    intervention: PrerequisiteIntervention | None = None
    causal_qualification: Literal["UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def require_evidence(self) -> Self:
        validate_references(self.evidence_references)
        if self.intervention is not None and (
            self.intervention.prerequisite != self.prerequisite
            or self.intervention.dependent != self.dependent
        ):
            raise ValueError("intervention capability binding mismatch")
        if self.status == "INTERVENTION_SUPPORT_REPORTED" and (
            self.intervention is None or self.intervention.reported_difference <= 0
        ):
            raise ValueError("positive paired intervention evidence required")
        return self


class PrerequisiteGraph(ScienceRecord):
    schema_version: Literal["veritas.prerequisite-graph.v1"] = "veritas.prerequisite-graph.v1"
    specs: tuple[CapabilitySpec, ...] = Field(min_length=1)
    claims: tuple[PrerequisiteClaim, ...] = ()

    def _graph(self) -> CapabilityGraph:
        return CapabilityGraph(
            nodes=[
                CapabilityNode(capability_id=s.record_id, label=s.contract.capability_id)
                for s in self.specs
            ],
            edges=[
                CapabilityEdge(prerequisite=c.prerequisite, dependent=c.dependent)
                for c in self.claims
            ],
        )

    @model_validator(mode="after")
    def validate_structure(self) -> Self:
        pairs = [(c.prerequisite, c.dependent) for c in self.claims]
        if len(pairs) != len(set(pairs)):
            raise ValueError("duplicate prerequisite claims")
        self._graph()  # Reuse Observatory unknown-node, self-edge and cycle checks.
        return self

    def observatory_graph(self) -> CapabilityGraph:
        """Structural view only; evidence/status remains on this wrapper, not the graph."""
        return self.checked()._graph()


class HypothesisRevision(ScienceRecord):
    schema_version: Literal["veritas.capability-hypothesis-revision.v1"] = (
        "veritas.capability-hypothesis-revision.v1"
    )
    hypothesis_key: Text
    revision: int = Field(ge=0, strict=True)
    previous_record_id: Text | None = None
    statement: Text
    capability_spec_ids: tuple[Text, ...] = Field(min_length=1)
    falsifier: Text
    status: Literal["PROPOSED", "SUPPORT_REPORTED", "REFUTED", "FAILED", "INCONCLUSIVE"]
    evidence_references: tuple[ExperienceReference, ...] = ()
    intervention_id: Text | None = None
    causal_qualification: Literal["UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def validate_revision(self) -> Self:
        if (self.revision == 0) != (self.previous_record_id is None):
            raise ValueError("hypothesis revision chain must start at zero")
        if len(self.capability_spec_ids) != len(set(self.capability_spec_ids)):
            raise ValueError("duplicate hypothesis capabilities")
        if self.status != "PROPOSED" or self.evidence_references:
            validate_references(self.evidence_references)
        return self


class HypothesisHistory(ScienceRecord):
    schema_version: Literal["veritas.capability-hypothesis-history.v1"] = (
        "veritas.capability-hypothesis-history.v1"
    )
    specs: tuple[CapabilitySpec, ...] = Field(min_length=1)
    revisions: tuple[HypothesisRevision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_history(self) -> Self:
        known = {spec.record_id for spec in self.specs}
        if len(known) != len(self.specs):
            raise ValueError("duplicate hypothesis capability specs")
        latest: dict[str, HypothesisRevision] = {}
        for current in self.revisions:
            if not set(current.capability_spec_ids) <= known:
                raise ValueError("hypothesis refers to an unknown capability spec")
            previous = latest.get(current.hypothesis_key)
            if previous is None:
                if current.revision != 0 or current.previous_record_id is not None:
                    raise ValueError("hypothesis history requires its initial revision")
            elif current.revision != previous.revision + 1 or (
                current.previous_record_id != previous.record_id
            ):
                raise ValueError("hypothesis history has a broken revision chain")
            latest[current.hypothesis_key] = current
        return self

    def append(self, revision: HypothesisRevision) -> HypothesisHistory:
        checked = self.checked()
        return HypothesisHistory(
            specs=checked.specs,
            revisions=(*checked.revisions, revision),
            visibility=checked.visibility,
        )
