from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest
from openpyxl import Workbook

import investigation_world.investigation_data.structured_corpus as structured_corpus_module
from investigation_world.investigation_data.models import (
    AcquisitionArtifact,
    AcquisitionPolicy,
    AIUsePolicy,
    ArtifactClass,
    ArtifactMethod,
    RedistributionPolicy,
    RightsPolicy,
    SourceCatalog,
    SourceSpec,
    TruthSemantics,
    TruthStrength,
)
from investigation_world.investigation_data.structured_corpus import (
    FieldExposure,
    ReviewScope,
    StructuredCorpusError,
    StructuredFieldRule,
    StructuredInputFormat,
    StructuredRightsReviewEvidence,
    StructuredSourceProfile,
    compile_structured_investigation_corpus,
    read_structured_records,
    write_structured_investigation_corpus,
)


def _catalog(
    *,
    acquisition: AcquisitionPolicy = AcquisitionPolicy.APPROVED,
    ai_use: AIUsePolicy = AIUsePolicy.ALLOWED,
    redistribution: RedistributionPolicy = RedistributionPolicy.ALLOWED,
    attribution_required: bool = False,
    expected_sha256: str | None = None,
    requires_redaction_review: bool = False,
) -> SourceCatalog:
    return SourceCatalog(
        schema_version="1.0",
        reviewed_at=date(2026, 8, 28),
        sources=(
            SourceSpec(
                source_id="test-source",
                name="Test Source",
                publisher="Test Publisher",
                domains=("investigation",),
                homepage="https://example.org/",
                allowed_hosts=("example.org",),
                rights=RightsPolicy(
                    acquisition=acquisition,
                    redistribution=redistribution,
                    ai_use=ai_use,
                    license_expression="test-only",
                    terms_url="https://example.org/terms",
                    attribution_required=attribution_required,
                ),
                truth=TruthSemantics(
                    strength=TruthStrength.CONTROLLED,
                    basis="Synthetic test fixture with controlled labels.",
                    verifier_use="private_truth",
                ),
                artifacts=(
                    AcquisitionArtifact(
                        artifact_id="fixture-csv",
                        label="Fixture CSV",
                        method=ArtifactMethod.HTTP_FILE,
                        url="https://example.org/data.csv",
                        artifact_class=ArtifactClass.DATA,
                        filename="data.csv",
                        expected_sha256=expected_sha256,
                    ),
                ),
                requires_redaction_review=requires_redaction_review,
            ),
        ),
    )


def _policy_sha256(catalog: SourceCatalog) -> str:
    source = catalog.sources[0]
    payload = {
        "rights": source.rights.model_dump(mode="json"),
        "requires_redaction_review": source.requires_redaction_review,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _artifact_sha256(catalog: SourceCatalog) -> str:
    artifact = catalog.sources[0].artifacts[0]
    encoded = json.dumps(
        artifact.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _required_scopes(catalog: SourceCatalog) -> tuple[ReviewScope, ...]:
    source = catalog.sources[0]
    scopes: list[ReviewScope] = []
    if source.rights.acquisition is AcquisitionPolicy.REVIEW_REQUIRED:
        scopes.append("acquisition")
    if source.rights.redistribution is RedistributionPolicy.REVIEW_REQUIRED:
        scopes.append("redistribution")
    if source.rights.ai_use in {
        AIUsePolicy.REVIEW_REQUIRED,
        AIUsePolicy.ALLOWED_WITH_CONDITIONS,
    }:
        scopes.append("ai_use")
    if source.requires_redaction_review:
        scopes.append("redaction")
    return tuple(scopes)


def _review_evidence(
    catalog: SourceCatalog,
    *,
    review_id: str = "review-test-001",
    source_id: str = "test-source",
    artifact_id: str = "fixture-csv",
    scopes: tuple[ReviewScope, ...] | None = None,
    policy_sha256: str | None = None,
    artifact_sha256: str | None = None,
) -> StructuredRightsReviewEvidence:
    return StructuredRightsReviewEvidence(
        review_id=review_id,
        source_id=source_id,
        source_artifact_id=artifact_id,
        scopes=scopes if scopes is not None else _required_scopes(catalog),
        policy_sha256=policy_sha256 or _policy_sha256(catalog),
        artifact_sha256=artifact_sha256 or _artifact_sha256(catalog),
    )


def _profile(
    *,
    input_format: StructuredInputFormat = StructuredInputFormat.CSV,
    rights_review_id: str | None = None,
) -> StructuredSourceProfile:
    return StructuredSourceProfile(
        profile_id="test-profile",
        version="1",
        source_id="test-source",
        source_artifact_id="fixture-csv",
        rights_review_id=rights_review_id,
        input_format=input_format,
        domain="investigation",
        objective="Determine the supported outcome from public evidence.",
        source_case_id_fields=("source_case_id",),
        title_fields=("title",),
        event_date_field="event_date",
        field_rules=(
            StructuredFieldRule(
                source_field="source_case_id",
                exposure=FieldExposure.IGNORE,
                required=True,
            ),
            StructuredFieldRule(
                source_field="title",
                exposure=FieldExposure.PUBLIC,
                required=True,
            ),
            StructuredFieldRule(
                source_field="event_date",
                exposure=FieldExposure.PUBLIC,
                required=True,
            ),
            StructuredFieldRule(
                source_field="evidence",
                exposure=FieldExposure.PUBLIC,
                required=True,
            ),
            StructuredFieldRule(
                source_field="outcome",
                exposure=FieldExposure.VERIFIER,
                required=True,
            ),
        ),
    )


def _write_csv(path, rows: list[tuple[str, str, str, str, str]]) -> None:
    path.write_text(
        "source_case_id,title,event_date,evidence,outcome\n"
        + "".join(",".join(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_case_identity_is_independent_of_row_order_and_verifier_label(tmp_path) -> None:
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    _write_csv(
        first_path,
        [
            ("CASE-A", "Alpha", "2025-01-01", "public-a", "secret-a"),
            ("CASE-B", "Beta", "2025-01-02", "public-b", "secret-b"),
        ],
    )
    _write_csv(
        second_path,
        [
            ("CASE-B", "Beta", "2025-01-02", "public-b", "changed-secret"),
            ("CASE-A", "Alpha", "2025-01-01", "public-a", "secret-a"),
        ],
    )

    first = compile_structured_investigation_corpus(
        _profile(),
        first_path,
        _catalog(),
        dataset_id="dataset",
        version="1",
        as_of=date(2026, 8, 28),
    )
    second = compile_structured_investigation_corpus(
        _profile(),
        second_path,
        _catalog(),
        dataset_id="dataset",
        version="1",
        as_of=date(2026, 8, 28),
    )

    first_ids = {case.source_identity: case.case_id for case in first.cases}
    second_ids = {case.source_identity: case.case_id for case in second.cases}
    assert first_ids == second_ids
    assert first_ids[("CASE-B",)] == second_ids[("CASE-B",)]


def test_unclassified_source_field_fails_closed(tmp_path) -> None:
    path = tmp_path / "data.csv"
    path.write_text(
        "source_case_id,title,event_date,evidence,outcome,unexpected_truth\n"
        "CASE-A,Alpha,2025-01-01,public,secret,leak\n",
        encoding="utf-8",
    )

    with pytest.raises(StructuredCorpusError, match="unclassified fields"):
        compile_structured_investigation_corpus(
            _profile(),
            path,
            _catalog(),
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
        )


def test_source_identity_cannot_depend_on_verifier_only_field() -> None:
    with pytest.raises(ValueError, match="cannot depend on verifier-only data"):
        StructuredSourceProfile(
            profile_id="bad",
            version="1",
            source_id="test-source",
            source_artifact_id="fixture-csv",
            input_format=StructuredInputFormat.CSV,
            domain="investigation",
            objective="Bad profile.",
            source_case_id_fields=("hidden_id",),
            title_fields=("title",),
            event_date_field="event_date",
            field_rules=(
                StructuredFieldRule(
                    source_field="hidden_id",
                    exposure=FieldExposure.VERIFIER,
                ),
                StructuredFieldRule(source_field="title", exposure=FieldExposure.PUBLIC),
                StructuredFieldRule(
                    source_field="event_date",
                    exposure=FieldExposure.PUBLIC,
                ),
            ),
        )


def test_duplicate_target_field_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate target field"):
        StructuredSourceProfile(
            profile_id="bad",
            version="1",
            source_id="test-source",
            source_artifact_id="fixture-csv",
            input_format=StructuredInputFormat.CSV,
            domain="investigation",
            objective="Bad profile.",
            source_case_id_fields=("source_case_id",),
            title_fields=("title",),
            event_date_field="event_date",
            field_rules=(
                StructuredFieldRule(
                    source_field="source_case_id",
                    exposure=FieldExposure.IGNORE,
                ),
                StructuredFieldRule(
                    source_field="title",
                    target_field="same",
                    exposure=FieldExposure.PUBLIC,
                ),
                StructuredFieldRule(
                    source_field="event_date",
                    exposure=FieldExposure.PUBLIC,
                ),
                StructuredFieldRule(
                    source_field="outcome",
                    target_field="same",
                    exposure=FieldExposure.VERIFIER,
                ),
            ),
        )


def test_conditional_ai_use_requires_scoped_review_evidence(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(
        path,
        [("CASE-A", "Alpha", "2025-01-01", "public", "secret")],
    )
    catalog = _catalog(ai_use=AIUsePolicy.ALLOWED_WITH_CONDITIONS)

    with pytest.raises(StructuredCorpusError, match="requires scoped rights/redaction review"):
        compile_structured_investigation_corpus(
            _profile(),
            path,
            catalog,
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
        )

    evidence = _review_evidence(catalog)
    compiled = compile_structured_investigation_corpus(
        _profile(rights_review_id=evidence.review_id),
        path,
        catalog,
        dataset_id="dataset",
        version="1",
        as_of=date(2026, 8, 28),
        rights_reviews=(evidence,),
    )
    assert len(compiled.cases) == 1
    assert compiled.rights_review == evidence


def test_public_materialization_fails_closed_for_blocked_redistribution(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])

    with pytest.raises(StructuredCorpusError, match="blocked for public redistribution"):
        compile_structured_investigation_corpus(
            _profile(),
            path,
            _catalog(redistribution=RedistributionPolicy.BLOCKED),
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
        )


def test_review_required_redistribution_retains_validated_review_evidence(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])
    catalog = _catalog(redistribution=RedistributionPolicy.REVIEW_REQUIRED)

    with pytest.raises(StructuredCorpusError, match="before public corpus use"):
        compile_structured_investigation_corpus(
            _profile(),
            path,
            catalog,
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
        )

    evidence = _review_evidence(catalog, review_id="redistribution-review-001")
    profile = _profile(rights_review_id=evidence.review_id)
    corpus = compile_structured_investigation_corpus(
        profile,
        path,
        catalog,
        dataset_id="dataset",
        version="1",
        as_of=date(2026, 8, 28),
        rights_reviews=(evidence,),
    )
    assert corpus.redistribution_policy is RedistributionPolicy.REVIEW_REQUIRED
    assert corpus.rights_review == evidence

    manifest_path = tmp_path / "manifest.json"
    write_structured_investigation_corpus(
        corpus,
        profile,
        public_output=tmp_path / "public.jsonl",
        manifest_output=manifest_path,
    )
    rights = json.loads(manifest_path.read_text(encoding="utf-8"))["rights"]
    assert rights["review_id"] == "redistribution-review-001"
    assert rights["review"] == evidence.model_dump(mode="json")


def test_review_id_must_resolve_to_supplied_evidence(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])
    catalog = _catalog(redistribution=RedistributionPolicy.REVIEW_REQUIRED)

    with pytest.raises(StructuredCorpusError, match="must resolve to exactly one"):
        compile_structured_investigation_corpus(
            _profile(rights_review_id="missing-review"),
            path,
            catalog,
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
        )


def test_duplicate_review_id_fails_closed(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])
    catalog = _catalog(redistribution=RedistributionPolicy.REVIEW_REQUIRED)
    evidence = _review_evidence(catalog, review_id="duplicate-review")

    with pytest.raises(StructuredCorpusError, match="must resolve to exactly one"):
        compile_structured_investigation_corpus(
            _profile(rights_review_id=evidence.review_id),
            path,
            catalog,
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
            rights_reviews=(evidence, evidence),
        )


def test_wrong_source_review_evidence_fails_closed(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])
    catalog = _catalog(redistribution=RedistributionPolicy.REVIEW_REQUIRED)
    evidence = _review_evidence(catalog, source_id="other-source")

    with pytest.raises(StructuredCorpusError, match="scoped to source"):
        compile_structured_investigation_corpus(
            _profile(rights_review_id=evidence.review_id),
            path,
            catalog,
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
            rights_reviews=(evidence,),
        )


def test_wrong_artifact_review_evidence_fails_closed(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])
    catalog = _catalog(redistribution=RedistributionPolicy.REVIEW_REQUIRED)
    evidence = _review_evidence(catalog, artifact_id="other-artifact")

    with pytest.raises(StructuredCorpusError, match="scoped to artifact"):
        compile_structured_investigation_corpus(
            _profile(rights_review_id=evidence.review_id),
            path,
            catalog,
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
            rights_reviews=(evidence,),
        )


def test_wrong_artifact_definition_review_evidence_fails_closed(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])
    catalog = _catalog(redistribution=RedistributionPolicy.REVIEW_REQUIRED)
    evidence = _review_evidence(catalog, artifact_sha256="0" * 64)

    with pytest.raises(StructuredCorpusError, match="current canonical artifact definition"):
        compile_structured_investigation_corpus(
            _profile(rights_review_id=evidence.review_id),
            path,
            catalog,
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
            rights_reviews=(evidence,),
        )


def test_wrong_policy_review_evidence_fails_closed(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])
    reviewed_catalog = _catalog(ai_use=AIUsePolicy.ALLOWED_WITH_CONDITIONS)
    current_catalog = _catalog(ai_use=AIUsePolicy.REVIEW_REQUIRED)
    evidence = _review_evidence(reviewed_catalog)

    with pytest.raises(StructuredCorpusError, match="current canonical rights/redaction policy"):
        compile_structured_investigation_corpus(
            _profile(rights_review_id=evidence.review_id),
            path,
            current_catalog,
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
            rights_reviews=(evidence,),
        )


def test_wrong_review_scope_fails_closed(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])
    catalog = _catalog(redistribution=RedistributionPolicy.REVIEW_REQUIRED)
    evidence = _review_evidence(catalog, scopes=("ai_use",))

    with pytest.raises(StructuredCorpusError, match="required scopes"):
        compile_structured_investigation_corpus(
            _profile(rights_review_id=evidence.review_id),
            path,
            catalog,
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
            rights_reviews=(evidence,),
        )


def test_unsolicited_review_evidence_is_rejected(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])
    no_review_catalog = _catalog()
    evidence_catalog = _catalog(ai_use=AIUsePolicy.ALLOWED_WITH_CONDITIONS)
    evidence = _review_evidence(evidence_catalog)

    with pytest.raises(StructuredCorpusError, match="unsolicited rights_review_id"):
        compile_structured_investigation_corpus(
            _profile(rights_review_id=evidence.review_id),
            path,
            no_review_catalog,
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
            rights_reviews=(evidence,),
        )


def test_canonical_expected_sha256_must_match_local_artifact(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])

    with pytest.raises(StructuredCorpusError, match="does not match canonical expected_sha256"):
        compile_structured_investigation_corpus(
            _profile(),
            path,
            _catalog(expected_sha256="0" * 64),
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
        )


def test_matching_canonical_expected_sha256_is_retained(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    corpus = compile_structured_investigation_corpus(
        _profile(),
        path,
        _catalog(expected_sha256=digest),
        dataset_id="dataset",
        version="1",
        as_of=date(2026, 8, 28),
    )
    assert corpus.source_artifact_sha256 == digest


def test_canonical_hash_and_parse_share_one_immutable_snapshot(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "approved", "secret")])
    approved_snapshot = path.read_bytes()
    approved_digest = hashlib.sha256(approved_snapshot).hexdigest()

    original_snapshot_reader = structured_corpus_module._read_input_snapshot
    snapshot_reads = 0

    def snapshot_then_swap(candidate):
        nonlocal snapshot_reads
        snapshot_reads += 1
        snapshot = original_snapshot_reader(candidate)
        if snapshot_reads == 1:
            _write_csv(
                path,
                [("CASE-B", "Tampered", "2025-02-02", "substituted", "other-secret")],
            )
        return snapshot

    monkeypatch.setattr(
        structured_corpus_module,
        "_read_input_snapshot",
        snapshot_then_swap,
    )

    corpus = compile_structured_investigation_corpus(
        _profile(),
        path,
        _catalog(expected_sha256=approved_digest),
        dataset_id="dataset",
        version="1",
        as_of=date(2026, 8, 28),
    )

    assert snapshot_reads == 1
    assert corpus.source_artifact_sha256 == approved_digest
    assert [case.title for case in corpus.cases] == ["Alpha"]
    assert corpus.cases[0].public_payload["evidence"] == "approved"
    assert "Tampered" in path.read_text(encoding="utf-8")


def test_attribution_obligation_is_retained_in_public_manifest(tmp_path) -> None:
    input_path = tmp_path / "data.csv"
    _write_csv(
        input_path,
        [("CASE-A", "Alpha", "2025-01-01", "public", "secret")],
    )
    corpus = compile_structured_investigation_corpus(
        _profile(),
        input_path,
        _catalog(
            redistribution=RedistributionPolicy.ATTRIBUTION_REQUIRED,
            attribution_required=True,
        ),
        dataset_id="dataset",
        version="1",
        as_of=date(2026, 8, 28),
    )
    manifest_path = tmp_path / "manifest.json"
    write_structured_investigation_corpus(
        corpus,
        _profile(),
        public_output=tmp_path / "public.jsonl",
        manifest_output=manifest_path,
    )

    rights = json.loads(manifest_path.read_text(encoding="utf-8"))["rights"]
    assert rights == {
        "attribution_required": True,
        "license_expression": "test-only",
        "redistribution": "attribution_required",
        "review": None,
        "review_id": None,
        "terms_url": "https://example.org/terms",
    }


def test_attribution_policy_without_obligation_flag_fails_closed(tmp_path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, [("CASE-A", "Alpha", "2025-01-01", "public", "secret")])

    with pytest.raises(StructuredCorpusError, match="inconsistent attribution policy"):
        compile_structured_investigation_corpus(
            _profile(),
            path,
            _catalog(redistribution=RedistributionPolicy.ATTRIBUTION_REQUIRED),
            dataset_id="dataset",
            version="1",
            as_of=date(2026, 8, 28),
        )


def test_public_outputs_omit_source_identity_row_and_verifier_hash(tmp_path) -> None:
    input_path = tmp_path / "data.csv"
    _write_csv(
        input_path,
        [("CASE-A", "Alpha", "2025-01-01", "public", "SECRET_SENTINEL")],
    )
    corpus = compile_structured_investigation_corpus(
        _profile(),
        input_path,
        _catalog(),
        dataset_id="dataset",
        version="1",
        as_of=date(2026, 8, 28),
    )
    public_path = tmp_path / "public.jsonl"
    verifier_path = tmp_path / "verifier.jsonl"
    manifest_path = tmp_path / "manifest.json"

    result = write_structured_investigation_corpus(
        corpus,
        _profile(),
        public_output=public_path,
        verifier_output=verifier_path,
        manifest_output=manifest_path,
    )

    public_text = public_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "SECRET_SENTINEL" not in public_text
    assert "CASE-A" not in public_text
    assert "source_identity" not in public_text
    assert "row_number" not in public_text
    assert "verifier_hash" not in manifest
    assert result.verifier_hash is not None
    assert "SECRET_SENTINEL" in verifier_path.read_text(encoding="utf-8")


def test_public_and_verifier_outputs_cannot_alias(tmp_path) -> None:
    input_path = tmp_path / "data.csv"
    _write_csv(
        input_path,
        [("CASE-A", "Alpha", "2025-01-01", "public", "SECRET_SENTINEL")],
    )
    corpus = compile_structured_investigation_corpus(
        _profile(),
        input_path,
        _catalog(),
        dataset_id="dataset",
        version="1",
        as_of=date(2026, 8, 28),
    )
    shared_path = tmp_path / "shared.jsonl"

    with pytest.raises(StructuredCorpusError, match="output paths must be distinct"):
        write_structured_investigation_corpus(
            corpus,
            _profile(),
            public_output=shared_path,
            verifier_output=shared_path,
            manifest_output=tmp_path / "manifest.json",
        )

    assert not shared_path.exists()


def test_equivalent_output_paths_cannot_bypass_alias_check(tmp_path) -> None:
    input_path = tmp_path / "data.csv"
    _write_csv(
        input_path,
        [("CASE-A", "Alpha", "2025-01-01", "public", "SECRET_SENTINEL")],
    )
    corpus = compile_structured_investigation_corpus(
        _profile(),
        input_path,
        _catalog(),
        dataset_id="dataset",
        version="1",
        as_of=date(2026, 8, 28),
    )
    public_path = tmp_path / "public.jsonl"
    equivalent_manifest = tmp_path / "nested" / ".." / "public.jsonl"

    with pytest.raises(StructuredCorpusError, match="output paths must be distinct"):
        write_structured_investigation_corpus(
            corpus,
            _profile(),
            public_output=public_path,
            manifest_output=equivalent_manifest,
        )

    assert not public_path.exists()


def test_json_nested_values_preserve_structure_without_cross_partition_leak(tmp_path) -> None:
    path = tmp_path / "data.json"
    path.write_text(
        json.dumps(
            [
                {
                    "source_case_id": "CASE-A",
                    "title": "Alpha",
                    "event_date": "2025-01-01",
                    "evidence": {"sensor": [1, 2], "note": "public"},
                    "outcome": {"label": "private", "confidence": 0.9},
                }
            ]
        ),
        encoding="utf-8",
    )
    profile = _profile(input_format=StructuredInputFormat.JSON)
    corpus = compile_structured_investigation_corpus(
        profile,
        path,
        _catalog(),
        dataset_id="dataset",
        version="1",
        as_of=date(2026, 8, 28),
    )

    case = corpus.cases[0]
    assert case.public_payload["evidence"] == {"sensor": [1, 2], "note": "public"}
    assert case.verifier_payload["outcome"] == {"label": "private", "confidence": 0.9}
    assert "outcome" not in case.public_projection()["evidence"]


def test_xlsx_reader_uses_declared_header_schema(tmp_path) -> None:
    path = tmp_path / "data.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["source_case_id", "title", "event_date", "evidence", "outcome"])
    sheet.append(["CASE-A", "Alpha", "2025-01-01", "public", "private"])
    workbook.save(path)
    workbook.close()

    rows = read_structured_records(
        path,
        _profile(input_format=StructuredInputFormat.XLSX),
    )
    assert rows == [
        {
            "source_case_id": "CASE-A",
            "title": "Alpha",
            "event_date": "2025-01-01",
            "evidence": "public",
            "outcome": "private",
        }
    ]
