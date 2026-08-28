from __future__ import annotations

from datetime import datetime, timezone

from investigation_world.conformance.certificate import (
    ConformanceAdapterReference,
    ConformanceCertificateStatus,
    ConformanceParity,
    PortableContractReference,
    TargetRuntimeReference,
    certify_adapter_conformance,
    conformance_evidence_record,
)
from investigation_world.conformance.models import AdapterConformanceReport
from investigation_world.evidence import (
    EvidencePolicyRef,
    EvidenceProducerRef,
    EvidenceVisibility,
)

NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)


def _report(**updates):
    values = {
        "mapped_fields": {"reward": "reward", "state": "state"},
        "preserved_fields": ("reward", "state", "termination", "evidence"),
        "generated_fields": ("target.metadata",),
        "excluded_private_fields": ("private.transitions",),
        "unsupported_fields": (),
        "semantic_losses": (),
        "test_vector_hash": "f" * 64,
    }
    values.update(updates)
    return AdapterConformanceReport(**values)


def _source() -> PortableContractReference:
    return PortableContractReference(
        schema_version="1.0.0",
        public_contract_id="POPC-PUBLIC-TEST",
        public_content_sha256="a" * 64,
    )


def _adapter() -> ConformanceAdapterReference:
    return ConformanceAdapterReference(
        adapter_name="nemo",
        adapter_version="1.0.0",
        content_sha256="b" * 64,
    )


def _runtime(version: str = "1.0.0") -> TargetRuntimeReference:
    return TargetRuntimeReference(
        runtime_name="nemo-gym",
        runtime_version=version,
        content_sha256="c" * 64,
    )


def _parity(**updates) -> ConformanceParity:
    values = {"state": True, "reward": True, "termination": True, "evidence": True}
    values.update(updates)
    return ConformanceParity(**values)


def _certificate(report=None, parity=None, runtime=None):
    return certify_adapter_conformance(
        report or _report(),
        source_contract=_source(),
        adapter=_adapter(),
        target_runtime=runtime or _runtime(),
        parity=parity or _parity(),
    )


def test_lossless_adapter_receives_pass_certificate() -> None:
    certificate = _certificate()

    assert certificate.status == ConformanceCertificateStatus.PASS
    assert certificate.passed
    assert certificate.certificate_id.startswith("CONFCERT-")
    assert certificate.report_id.startswith("CONFREPORT-")
    assert len(certificate.certificate_content_sha256) == 64


def test_semantic_loss_forces_certificate_failure() -> None:
    certificate = _certificate(
        report=_report(semantic_losses=("reward:semantic_mismatch:$.reward",))
    )

    assert certificate.status == ConformanceCertificateStatus.FAIL
    assert not certificate.passed


def test_negative_parity_forces_certificate_failure() -> None:
    certificate = _certificate(parity=_parity(reward=False))

    assert certificate.status == ConformanceCertificateStatus.FAIL


def test_missing_parity_evidence_remains_unknown() -> None:
    certificate = _certificate(parity=_parity(evidence=None))

    assert certificate.status == ConformanceCertificateStatus.UNKNOWN
    assert not certificate.passed


def test_declared_unsupported_surface_cannot_receive_lossless_pass() -> None:
    certificate = _certificate(report=_report(unsupported_fields=("optional_trace",)))

    assert certificate.status == ConformanceCertificateStatus.UNKNOWN


def test_certificate_identity_is_canonical_for_mapping_order() -> None:
    first = _certificate(
        report=_report(mapped_fields={"state": "state", "reward": "reward"})
    )
    second = _certificate(
        report=_report(mapped_fields={"reward": "reward", "state": "state"})
    )

    assert first.report_id == second.report_id
    assert first.certificate_id == second.certificate_id


def test_runtime_version_changes_certificate_identity_not_report_identity() -> None:
    first = _certificate(runtime=_runtime("1.0.0"))
    second = _certificate(runtime=_runtime("2.0.0"))

    assert first.report_id == second.report_id
    assert first.certificate_id != second.certificate_id


def test_certificate_emits_shared_composable_evidence() -> None:
    certificate = _certificate()
    record = conformance_evidence_record(
        certificate,
        producer=EvidenceProducerRef(
            producer_id="cross-runtime-conformance",
            producer_version="1.0.0",
            content_sha256="d" * 64,
        ),
        policy=EvidencePolicyRef(
            policy_id="CONFORMANCE-POLICY-v1",
            policy_version="veritas.adapter-conformance-certificate.v1",
            content_sha256="e" * 64,
        ),
        visibility=EvidenceVisibility.PUBLIC,
        observed_at=NOW,
        provenance={"runner": "conformance-test"},
    )

    assert record.outcome.value == "PASS"
    assert record.evidence_type == "conformance.adapter"
    assert {subject.kind for subject in record.subjects} == {
        "portable_contract",
        "adapter",
        "runtime",
    }
    assert {artifact.role for artifact in record.artifacts} == {
        "conformance_certificate",
        "adapter_conformance_report",
    }


def test_certificate_binds_public_contract_identity_only() -> None:
    certificate = _certificate()
    payload = certificate.model_dump(mode="json")

    assert payload["source_contract"]["public_contract_id"] == "POPC-PUBLIC-TEST"
    assert "contract_id" not in payload["source_contract"]
    assert "private" not in payload["source_contract"]
