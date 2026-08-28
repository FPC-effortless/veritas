import json

import pytest
from pydantic import ValidationError

from investigation_world.attestations import (
    ArtifactIdentity,
    AttestationSignature,
    AttestationVisibility,
    ContentIdentity,
    EnvironmentAttestation,
    QualificationBinding,
    serialize_attestation,
    serialize_public_attestation,
)
from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    EnvironmentMaturity,
    VerifierIdentity,
)

DIGESTS = {letter: letter * 64 for letter in "abcdef"}


def _attestation(*, reverse: bool = False) -> EnvironmentAttestation:
    environment = EnvironmentIdentity(
        environment_id="env.demo",
        environment_version="1",
        content_sha256=DIGESTS["a"],
    )
    verifier = VerifierIdentity(
        verifier_id="verifier.demo",
        verifier_version="2",
        content_sha256=DIGESTS["b"],
    )
    qualification = QualificationBinding(
        maturity_record_id="MREC-ABC",
        qualification_identity="MQUAL-ABC",
        achieved_status=EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED,
        qualification_policy_id="MPOL-ABC",
        qualification_policy_version="policy-v1",
        environment_content_sha256=DIGESTS["a"],
        verifier_content_sha256=DIGESTS["b"],
    )
    artifacts = [
        ArtifactIdentity(
            artifact_id="runtime",
            role="runtime",
            content_sha256=DIGESTS["c"],
        ),
        ArtifactIdentity(
            artifact_id="manifest",
            role="manifest",
            content_sha256=DIGESTS["d"],
        ),
    ]
    adapters = [
        ContentIdentity(
            kind="adapter",
            identity="nemo",
            version="1",
            content_sha256=DIGESTS["c"],
        ),
        ContentIdentity(
            kind="adapter",
            identity="openenv",
            version="1",
            content_sha256=DIGESTS["d"],
        ),
    ]
    dependencies = [
        ContentIdentity(
            kind="dependency",
            identity="pydantic",
            version="2.13",
            content_sha256=DIGESTS["e"],
        ),
        ContentIdentity(
            kind="dependency",
            identity="python",
            version="3.12",
            content_sha256=DIGESTS["f"],
        ),
    ]
    if reverse:
        artifacts.reverse()
        adapters.reverse()
        dependencies.reverse()

    return EnvironmentAttestation(
        environment=environment,
        artifacts=tuple(artifacts),
        source=ContentIdentity(
            kind="source",
            identity="git:deadbeef",
            content_sha256=DIGESTS["d"],
        ),
        builder=ContentIdentity(
            kind="builder",
            identity="veritas-ci",
            version="1",
            content_sha256=DIGESTS["e"],
        ),
        verifier=verifier,
        qualification=qualification,
        adapters=tuple(adapters),
        dependencies=tuple(dependencies),
        sbom=ContentIdentity(
            kind="sbom",
            identity="spdx:demo",
            content_sha256=DIGESTS["f"],
        ),
    )


def test_identity_is_order_independent_and_content_addressed() -> None:
    left = _attestation()
    right = _attestation(reverse=True)

    assert left.attestation_id == right.attestation_id
    assert left.content_sha256 == right.content_sha256
    assert serialize_attestation(left) == serialize_attestation(right)


def test_content_change_changes_identity() -> None:
    original = _attestation()
    data = original.model_dump(exclude={"attestation_id", "content_sha256"})
    data["source"] = ContentIdentity(
        kind="source",
        identity="git:cafebabe",
        content_sha256=DIGESTS["a"],
    )

    changed = EnvironmentAttestation(**data)

    assert changed.attestation_id != original.attestation_id
    assert changed.content_sha256 != original.content_sha256


def test_claimed_digest_must_match_contents() -> None:
    data = _attestation().model_dump()
    data["content_sha256"] = DIGESTS["f"]

    with pytest.raises(ValidationError, match="attestation digest"):
        EnvironmentAttestation(**data)


def test_qualification_must_bind_exact_environment_and_verifier() -> None:
    data = _attestation().model_dump()
    data["qualification"]["environment_content_sha256"] = DIGESTS["f"]
    data["attestation_id"] = ""
    data["content_sha256"] = ""

    with pytest.raises(ValidationError, match="different environment"):
        EnvironmentAttestation(**data)


def test_draft_is_not_qualified_for_attestation() -> None:
    with pytest.raises(ValidationError, match="beyond DRAFT"):
        QualificationBinding(
            maturity_record_id="MREC-X",
            qualification_identity="MQUAL-X",
            achieved_status=EnvironmentMaturity.DRAFT,
            qualification_policy_id="MPOL-X",
            qualification_policy_version="v1",
            environment_content_sha256=DIGESTS["a"],
            verifier_content_sha256=DIGESTS["b"],
        )


def test_models_carry_references_not_private_payloads() -> None:
    with pytest.raises(ValidationError):
        ContentIdentity.model_validate(
            {
                "kind": "source",
                "identity": "git:x",
                "content_sha256": DIGESTS["a"],
                "payload": {"secret": "truth"},
            }
        )

    payload = json.loads(serialize_attestation(_attestation()))

    assert "signature" not in payload
    assert "provenance" not in payload
    assert "evidence" not in payload["qualification"]


def test_signature_is_detached_from_semantic_identity() -> None:
    attestation = _attestation()
    semantic_bytes = serialize_attestation(attestation)
    signature = AttestationSignature(
        attestation_id=attestation.attestation_id,
        attestation_content_sha256=attestation.content_sha256,
        algorithm="ed25519",
        key_id="release-key",
        signature="opaque-signature",
    )

    assert signature.binds(attestation)
    assert serialize_attestation(attestation) == semantic_bytes

    wrong_signature = signature.model_copy(
        update={"attestation_content_sha256": DIGESTS["a"]}
    )
    assert not wrong_signature.binds(attestation)


def test_public_serialization_is_fail_closed_and_changes_identity() -> None:
    private = _attestation()

    assert private.visibility == AttestationVisibility.OPERATOR_PRIVATE
    with pytest.raises(ValueError, match="only PUBLIC"):
        serialize_public_attestation(private)

    data = private.model_dump(exclude={"attestation_id", "content_sha256"})
    data["visibility"] = AttestationVisibility.PUBLIC
    public = EnvironmentAttestation(**data)

    assert serialize_public_attestation(public) == serialize_attestation(public)
    assert public.attestation_id != private.attestation_id


def test_model_copy_semantic_mutation_is_rejected_at_consumers() -> None:
    attestation = _attestation()
    signature = AttestationSignature(
        attestation_id=attestation.attestation_id,
        attestation_content_sha256=attestation.content_sha256,
        algorithm="ed25519",
        key_id="release-key",
        signature="opaque-signature",
    )
    copied = attestation.model_copy(
        update={
            "source": ContentIdentity(
                kind="source",
                identity="git:cafebabe",
                content_sha256=DIGESTS["a"],
            )
        }
    )

    assert copied.attestation_id == attestation.attestation_id
    assert copied.content_sha256 == attestation.content_sha256
    with pytest.raises(ValidationError, match="attestation digest"):
        serialize_attestation(copied)
    assert not signature.binds(copied)


def test_model_copy_visibility_escalation_cannot_be_publicly_serialized() -> None:
    private = _attestation()
    copied = private.model_copy(update={"visibility": AttestationVisibility.PUBLIC})

    assert copied.visibility == AttestationVisibility.PUBLIC
    assert copied.attestation_id == private.attestation_id
    assert copied.content_sha256 == private.content_sha256
    with pytest.raises(ValidationError, match="attestation digest"):
        serialize_public_attestation(copied)
