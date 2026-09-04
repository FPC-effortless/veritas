from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from investigation_world.attestations import (
    ArtifactIdentity,
    AttestationVisibility,
    ContentIdentity,
    EnvironmentAttestation,
    QualificationBinding,
)
from investigation_world.conformance.certificate import (
    ConformanceAdapterReference,
    ConformanceParity,
    PortableContractReference,
    TargetRuntimeReference,
    certify_adapter_conformance,
)
from investigation_world.conformance.models import AdapterConformanceReport
from investigation_world.evidence import (
    EvidenceArtifactRef,
    EvidenceOutcome,
    EvidencePolicyRef,
    EvidenceProducerRef,
    EvidenceRecord,
    EvidenceSubjectRef,
    EvidenceVisibility,
)
from investigation_world.portability.models import (
    PortableCapability,
    PortableEnvironmentManifest,
    PortableOperationalContractReference,
    PortableReleaseIdentity,
    PortableResetContract,
    PortableTasksetManifest,
    PortableVerifierContract,
    PortableVisibility,
)
from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    EnvironmentMaturity,
    GateOutcome,
    MaturityGateEvidence,
    VerifierIdentity,
    assess_environment_maturity,
)
from investigation_world.qualification.quality_scorecard import (
    QualityScorecardContext,
    build_environment_quality_scorecard,
)
from investigation_world.qualified_package import (
    PackageContentReference,
    PackageEvidenceBinding,
    PackageEvidenceKind,
    PackageLimitation,
    PrivateEvaluatorReference,
    PrivateEvaluatorStatus,
    QualifiedEnvironmentPackage,
    build_qualified_environment_package,
    serialize_buyer_safe_manifest,
    serialize_qualified_package,
)

DIGESTS = {letter: letter * 64 for letter in "abcdef"}
NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


def _environment() -> EnvironmentIdentity:
    return EnvironmentIdentity(
        environment_id="env.demo",
        environment_version="1",
        content_sha256=DIGESTS["a"],
    )


def _verifier() -> VerifierIdentity:
    return VerifierIdentity(
        verifier_id="verifier.demo",
        verifier_version="2",
        content_sha256=DIGESTS["b"],
    )


def _maturity_record():
    evidence = tuple(
        MaturityGateEvidence(
            gate=gate,
            outcome=GateOutcome.PASS,
            evidence_id=f"EVID-{index}",
            content_sha256=DIGESTS["c"],
            environment_content_sha256=DIGESTS["a"],
            verifier_content_sha256=DIGESTS["b"],
            qualification_policy_version="veritas-environment-maturity-v1",
            observed_at=NOW,
            provenance={"fixture": gate},
        )
        for index, gate in enumerate(
            (
                "environment_contract_valid",
                "runtime_smoke",
                "deterministic_reset",
            ),
            start=1,
        )
    )
    return assess_environment_maturity(
        environment_identity=_environment(),
        verifier_identity=_verifier(),
        evidence=evidence,
        provenance={"fixture": "package"},
        target_status=EnvironmentMaturity.COMMERCIAL_RELEASE,
        evaluated_at=NOW,
    )


def _portable_manifest(
    *, visibility: PortableVisibility = PortableVisibility.BUYER_SAFE
) -> PortableEnvironmentManifest:
    return PortableEnvironmentManifest(
        release=PortableReleaseIdentity(
            candidate_id="candidate-demo",
            candidate_version="1",
            panel_id="panel-demo",
            qualification_report_id="qualification-demo",
            evidence_manifest_id="evidence-demo",
            private_release_manifest_id="private-release-demo",
            source_bundle_sha256=DIGESTS["c"],
        ),
        environment_id="env.demo",
        environment_version="1",
        sku="demo-evaluation-pack",
        domain="demo",
        description="Buyer-safe demo package.",
        visibility=visibility,
        taskset=PortableTasksetManifest(
            taskset_version="1",
            visible_tasks=(),
            private_task_count=1,
        ),
        capabilities=(
            PortableCapability(
                capability_id="inspect",
                description="Inspect public state.",
            ),
        ),
        reset=PortableResetContract(
            reset_semantics="Restore the exact deterministic initial public state."
        ),
        verifier=PortableVerifierContract(
            verifier_id="verifier.demo",
            version="2",
            deterministic=True,
            reward_range=(0.0, 1.0),
            requires_private_ground_truth=True,
            description="Deterministic demo verifier.",
        ),
        operational_contract=PortableOperationalContractReference(
            schema_version="portable-contract-v1",
            public_contract_id="PCON-DEMO",
        ),
    )


def _maturity_and_scorecard():
    maturity = _maturity_record()
    scorecard = build_environment_quality_scorecard(
        context=QualityScorecardContext(
            environment=EvidenceSubjectRef(
                kind="environment",
                subject_id="env.demo",
                version="1",
                content_sha256=DIGESTS["a"],
            ),
            verifier=EvidenceSubjectRef(
                kind="verifier",
                subject_id="verifier.demo",
                version="2",
                content_sha256=DIGESTS["b"],
            ),
        ),
        evidence=(),
    )
    return maturity, scorecard


def _conformance():
    report = AdapterConformanceReport(
        mapped_fields={"observation": "observation"},
        preserved_fields=("reward",),
        generated_fields=(),
        excluded_private_fields=("hidden_truth",),
        unsupported_fields=(),
        semantic_losses=(),
        test_vector_hash=DIGESTS["d"],
    )
    return certify_adapter_conformance(
        report,
        source_contract=PortableContractReference(
            schema_version="portable-contract-v1",
            public_contract_id="PCON-DEMO",
            public_content_sha256=DIGESTS["d"],
        ),
        adapter=ConformanceAdapterReference(
            adapter_name="prime",
            adapter_version="1",
            content_sha256=DIGESTS["e"],
        ),
        target_runtime=TargetRuntimeReference(
            runtime_name="prime-verifiers",
            runtime_version="1",
            content_sha256=DIGESTS["f"],
        ),
        parity=ConformanceParity(
            state=True,
            reward=True,
            termination=True,
            evidence=True,
        ),
    )


def _attestation(
    *,
    visibility: AttestationVisibility = AttestationVisibility.PUBLIC,
    artifact_digest: str = DIGESTS["c"],
) -> EnvironmentAttestation:
    maturity = _maturity_record()
    return EnvironmentAttestation(
        visibility=visibility,
        environment=_environment(),
        artifacts=(
            ArtifactIdentity(
                artifact_id="runtime",
                role="runtime",
                content_sha256=artifact_digest,
            ),
        ),
        source=ContentIdentity(
            kind="source",
            identity="git:demo",
            content_sha256=DIGESTS["d"],
        ),
        builder=ContentIdentity(
            kind="builder",
            identity="veritas-ci",
            version="1",
            content_sha256=DIGESTS["e"],
        ),
        verifier=_verifier(),
        qualification=QualificationBinding.from_maturity_record(maturity),
        sbom=ContentIdentity(
            kind="sbom",
            identity="spdx:demo",
            content_sha256=DIGESTS["f"],
        ),
    )


def _evidence(
    *,
    visibility: EvidenceVisibility,
    artifact_digest: str,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_type="package.installation",
        outcome=EvidenceOutcome.OBSERVED,
        visibility=visibility,
        claim="Clean installation fixture observed.",
        subjects=(
            EvidenceSubjectRef(
                kind="environment",
                subject_id="env.demo",
                version="1",
                content_sha256=DIGESTS["a"],
            ),
        ),
        producer=EvidenceProducerRef(
            producer_id="package-test",
            producer_version="1",
            content_sha256=DIGESTS["d"],
        ),
        policy=EvidencePolicyRef(
            policy_id="package-policy",
            policy_version="1",
            content_sha256=DIGESTS["e"],
        ),
        artifacts=(
            EvidenceArtifactRef(
                artifact_id="install-report",
                content_sha256=artifact_digest,
            ),
        ),
        observed_at=NOW,
        provenance={"fixture": "install"},
    )


def _supply_chain():
    return (
        PackageContentReference(
            kind="source",
            identity="git:demo",
            content_sha256=DIGESTS["d"],
            visibility=EvidenceVisibility.PUBLIC,
        ),
        PackageContentReference(
            kind="license",
            identity="license:commercial-demo",
            version="1",
            content_sha256=DIGESTS["e"],
            visibility=EvidenceVisibility.PUBLIC,
        ),
        PackageContentReference(
            kind="sbom",
            identity="spdx:private-detail",
            content_sha256=DIGESTS["f"],
            visibility=EvidenceVisibility.OPERATOR_PRIVATE,
        ),
    )


def _package(
    *,
    private_evaluator_digest: str = DIGESTS["f"],
    private_attestation_digest: str = DIGESTS["e"],
) -> QualifiedEnvironmentPackage:
    maturity, scorecard = _maturity_and_scorecard()
    return build_qualified_environment_package(
        environment=_environment(),
        verifier=_verifier(),
        portable_manifest=_portable_manifest(),
        maturity_record=maturity,
        scorecard=scorecard,
        conformance_certificates=(_conformance(),),
        attestations=(
            _attestation(),
            _attestation(
                visibility=AttestationVisibility.OPERATOR_PRIVATE,
                artifact_digest=private_attestation_digest,
            ),
        ),
        evidence=(
            PackageEvidenceBinding.from_evidence_record(
                _evidence(
                    visibility=EvidenceVisibility.PUBLIC,
                    artifact_digest=DIGESTS["c"],
                ),
                kind=PackageEvidenceKind.INSTALLATION,
            ),
            PackageEvidenceBinding.from_evidence_record(
                _evidence(
                    visibility=EvidenceVisibility.OPERATOR_PRIVATE,
                    artifact_digest=DIGESTS["f"],
                ),
                kind=PackageEvidenceKind.DIAGNOSTIC,
            ),
        ),
        supply_chain=_supply_chain(),
        private_evaluator=PrivateEvaluatorReference(
            status=PrivateEvaluatorStatus.PRESENT,
            reference_id="private-evaluator-demo",
            version="1",
            content_sha256=private_evaluator_digest,
        ),
        known_limitations=(
            PackageLimitation(
                code="frontier-evidence-unknown",
                detail="Frontier utility has not been established.",
                unknown=True,
            ),
        ),
    )


def test_package_composes_authorities_without_promoting_maturity() -> None:
    package = _package()

    assert package.maturity.status == EnvironmentMaturity.EXECUTABLE
    assert package.maturity.unknown_gates
    assert package.scorecard.unknown_dimensions
    assert package.conformance[0].status.value == "PASS"
    assert package.package_id.startswith("QPKG-")


def test_package_identity_is_deterministic_and_material_changes_rekey() -> None:
    left = _package()
    right = _package()
    changed = _package(private_evaluator_digest=DIGESTS["c"])

    assert left.package_id == right.package_id
    assert serialize_qualified_package(left) == serialize_qualified_package(right)
    assert changed.package_id != left.package_id


def test_public_manifest_filters_private_identifiers_and_private_hashes() -> None:
    package = _package()
    manifest = package.buyer_safe_manifest()
    payload = serialize_buyer_safe_manifest(package).decode("utf-8")

    assert manifest.private_evaluator_status == PrivateEvaluatorStatus.PRESENT
    assert "private-evaluator-demo" not in payload
    assert package.private_evaluator.content_sha256 not in payload
    assert all(
        item.visibility == AttestationVisibility.PUBLIC
        for item in manifest.attestations
    )
    assert all(item.visibility == EvidenceVisibility.PUBLIC for item in manifest.evidence)
    assert all(
        item.visibility == EvidenceVisibility.PUBLIC for item in manifest.supply_chain
    )


def test_private_only_changes_do_not_create_buyer_safe_fingerprint() -> None:
    original = _package()
    changed_evaluator = _package(private_evaluator_digest=DIGESTS["c"])
    changed_private_attestation = _package(private_attestation_digest=DIGESTS["d"])

    assert changed_evaluator.package_id != original.package_id
    assert changed_private_attestation.package_id != original.package_id
    assert (
        changed_evaluator.buyer_safe_manifest().manifest_id
        == original.buyer_safe_manifest().manifest_id
    )
    assert (
        changed_private_attestation.buyer_safe_manifest().manifest_id
        == original.buyer_safe_manifest().manifest_id
    )


def test_stale_model_copy_semantic_mutation_fails_closed_at_serialization() -> None:
    package = _package()
    copied = package.model_copy(
        update={
            "environment": EnvironmentIdentity(
                environment_id="env.demo",
                environment_version="1",
                content_sha256=DIGESTS["f"],
            )
        }
    )

    assert copied.package_id == package.package_id
    with pytest.raises(ValidationError, match="portable|maturity|scorecard|digest"):
        serialize_qualified_package(copied)
    with pytest.raises(ValidationError, match="portable|maturity|scorecard|digest"):
        serialize_buyer_safe_manifest(copied)


def test_package_rejects_mismatched_attestation_authority() -> None:
    package = _package()
    bad = package.model_dump(exclude={"package_id", "package_content_sha256"})
    attestation = package.attestations[0].model_dump()
    attestation["environment_content_sha256"] = DIGESTS["f"]
    bad["attestations"] = (attestation,)

    with pytest.raises(ValidationError, match="different environment"):
        QualifiedEnvironmentPackage(**bad)


def test_private_portable_manifest_is_not_accepted_as_buyer_package_binding() -> None:
    maturity, scorecard = _maturity_and_scorecard()

    with pytest.raises(ValidationError, match="public or buyer-safe"):
        build_qualified_environment_package(
            environment=_environment(),
            verifier=_verifier(),
            portable_manifest=_portable_manifest(
                visibility=PortableVisibility.PRIVATE_OPERATOR
            ),
            maturity_record=maturity,
            scorecard=scorecard,
            attestations=(_attestation(),),
            supply_chain=_supply_chain(),
            private_evaluator=PrivateEvaluatorReference(
                status=PrivateEvaluatorStatus.UNKNOWN
            ),
        )


def test_source_and_license_disclosure_are_required() -> None:
    package = _package()
    bad = package.model_dump(exclude={"package_id", "package_content_sha256"})
    bad["supply_chain"] = tuple(
        item for item in bad["supply_chain"] if item["kind"] != "license"
    )

    with pytest.raises(ValidationError, match="licensing"):
        QualifiedEnvironmentPackage(**bad)


def test_non_present_private_evaluator_cannot_carry_identifiers() -> None:
    with pytest.raises(ValidationError, match="cannot carry private identifiers"):
        PrivateEvaluatorReference(
            status=PrivateEvaluatorStatus.UNKNOWN,
            reference_id="secret-reference",
            content_sha256=DIGESTS["a"],
        )
