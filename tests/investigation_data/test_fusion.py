from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from investigation_world.investigation_data.fusion import (
    DerivationKind,
    EpistemicRole,
    EvidenceFragment,
    EvidenceModality,
    FusionManifest,
    fuse_manifest,
)
from investigation_world.investigation_data.models import Sensitivity, TruthClaim


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def fragment(
    fragment_id: str,
    *,
    available_from: datetime | None = NOW,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    epistemic_role: EpistemicRole = EpistemicRole.PRIMARY_EVIDENCE,
    derivation: DerivationKind = DerivationKind.ORIGINAL,
    modality: EvidenceModality = EvidenceModality.DOCUMENT,
    parents: tuple[str, ...] = (),
) -> EvidenceFragment:
    return EvidenceFragment(
        fragment_id=fragment_id,
        source_id="ntsb-aviation-census",
        source_artifact_id="case-docket",
        case_ids=("CASE-1",),
        modality=modality,
        epistemic_role=epistemic_role,
        derivation=derivation,
        sensitivity=sensitivity,
        locator=f"docket://CASE-1/{fragment_id}",
        content_ref=f"evidence://CASE-1/{fragment_id}",
        available_from=available_from,
        reliability="high",
        parent_fragment_ids=parents,
    )


def manifest(*fragments: EvidenceFragment) -> FusionManifest:
    return FusionManifest(
        episode_id="episode-1",
        domain="aviation",
        source_case_ids=("CASE-1",),
        simulation_start=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
        simulation_as_of=NOW,
        initial_public_state={"report": "aircraft missing"},
        available_actions=("inspect", "interview", "request_forensics"),
        fragments=fragments,
        ground_truth_claims=(
            TruthClaim(
                claim_id="claim-1",
                proposition="Component X failed before impact",
                truth_status="true",
                confidence=1.0,
            ),
        ),
    )


def test_fusion_withholds_future_evidence_and_sealed_truth() -> None:
    visible = fragment("visible")
    future = fragment(
        "future",
        available_from=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
        modality=EvidenceModality.VIDEO,
    )
    sealed = fragment(
        "oracle",
        sensitivity=Sensitivity.SEALED,
        epistemic_role=EpistemicRole.PRIVATE_TRUTH,
    )

    result = fuse_manifest(manifest(visible, future, sealed))

    assert [item.evidence_id for item in result.bundle.public.evidence] == ["visible"]
    assert result.report.public_fragment_ids == ("visible",)
    assert result.report.withheld_future_fragment_ids == ("future",)
    assert result.report.sealed_fragment_ids == ("oracle",)
    assert result.bundle.oracle.ground_truth_claims[0].claim_id == "claim-1"


def test_video_segment_is_preserved_as_multimodal_kind() -> None:
    video = EvidenceFragment(
        fragment_id="hearing-segment",
        source_id="ntsb-public-media",
        source_artifact_id="hearing-video",
        case_ids=("CASE-1",),
        modality=EvidenceModality.VIDEO,
        epistemic_role=EpistemicRole.TESTIMONY,
        locator="https://example.invalid/watch?v=official",
        content_ref="external-media://hearing-video#t=90,130",
        available_from=NOW,
        segment_start_seconds=90.0,
        segment_end_seconds=130.0,
        reliability="medium",
    )
    result = fuse_manifest(manifest(video))
    assert result.bundle.public.evidence[0].kind == "video:testimony"


def test_timed_fragment_without_availability_is_rejected() -> None:
    with pytest.raises(
        ValidationError, match="timed public/restricted evidence requires available_from"
    ):
        fragment("missing-time", available_from=None)


def test_public_derived_fragment_cannot_depend_on_sealed_lineage() -> None:
    sealed = fragment(
        "sealed-parent",
        sensitivity=Sensitivity.SEALED,
        epistemic_role=EpistemicRole.PRIVATE_TRUTH,
    )
    public_derived = fragment(
        "derived",
        derivation=DerivationKind.EXTRACTED,
        epistemic_role=EpistemicRole.DERIVED,
        parents=("sealed-parent",),
    )
    with pytest.raises(ValidationError, match="depends on sealed lineage"):
        manifest(sealed, public_derived)


def test_missing_parent_is_rejected() -> None:
    derived = fragment(
        "derived",
        derivation=DerivationKind.EXTRACTED,
        epistemic_role=EpistemicRole.DERIVED,
        parents=("missing",),
    )
    with pytest.raises(ValidationError, match="missing parents"):
        manifest(derived)


def test_cross_case_fragment_is_rejected() -> None:
    other = EvidenceFragment(
        fragment_id="other-case",
        source_id="source",
        source_artifact_id="artifact",
        case_ids=("CASE-2",),
        modality=EvidenceModality.DOCUMENT,
        epistemic_role=EpistemicRole.PRIMARY_EVIDENCE,
        locator="doc://other",
        content_ref="evidence://other",
        available_from=NOW,
    )
    with pytest.raises(ValidationError, match="no case link"):
        manifest(other)


def test_manifest_digest_is_deterministic() -> None:
    item = fragment("stable")
    first = fuse_manifest(manifest(item)).report.manifest_sha256
    second = fuse_manifest(manifest(item)).report.manifest_sha256
    assert first == second


def test_derived_fragment_cannot_precede_parent_availability() -> None:
    parent = fragment(
        "video",
        available_from=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc),
        modality=EvidenceModality.VIDEO,
    )
    child = fragment(
        "transcript",
        available_from=datetime(2026, 8, 28, 11, 0, tzinfo=timezone.utc),
        modality=EvidenceModality.TRANSCRIPT,
        derivation=DerivationKind.EXTRACTED,
        epistemic_role=EpistemicRole.DERIVED,
        parents=("video",),
    )
    with pytest.raises(ValidationError, match="becomes available before parent"):
        manifest(parent, child)


def test_only_context_can_be_timeless() -> None:
    with pytest.raises(ValidationError, match="only context evidence"):
        EvidenceFragment(
            fragment_id="bad-timeless",
            source_id="source",
            source_artifact_id="artifact",
            case_ids=("CASE-1",),
            modality=EvidenceModality.DOCUMENT,
            epistemic_role=EpistemicRole.PRIMARY_EVIDENCE,
            locator="doc://bad",
            content_ref="evidence://bad",
            timeless=True,
        )

    context = EvidenceFragment(
        fragment_id="procedure-context",
        source_id="source",
        source_artifact_id="procedure",
        case_ids=("CASE-1",),
        modality=EvidenceModality.DOCUMENT,
        epistemic_role=EpistemicRole.CONTEXT,
        locator="doc://procedure",
        content_ref="evidence://procedure",
        timeless=True,
    )
    result = fuse_manifest(manifest(context))
    assert result.report.public_fragment_ids == ("procedure-context",)
