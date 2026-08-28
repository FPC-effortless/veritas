# Qualified environment supply-chain attestations

`EnvironmentAttestation` is a deterministic, content-addressed statement that binds a Veritas
environment artifact set to the identities used to build and qualify it.

The attestation is **supply-chain evidence, not qualification**. It references a validated maturity
record and its qualification identity, policy identity, exact environment digest, and verifier
digest. It does not repeat qualification evidence and must not be interpreted as independently
proving scientific, Frontier, training, or commercial maturity.

## Bound identities

The semantic attestation binds:

- the canonical environment identity and content digest;
- one or more distributable artifact identities and digests;
- the source identity used for the build;
- the builder identity;
- the exact verifier identity used by the referenced maturity record;
- the maturity-record, qualification, and qualification-policy identities;
- zero or more runtime adapter identities;
- zero or more dependency identities; and
- an SBOM identity and digest.

`ContentIdentity` and `ArtifactIdentity` intentionally contain no URI, filesystem path, raw package
contents, evaluator payload, or private evidence. They are opaque identities plus content digests.
This lets an operator bind sealed or private material without copying that material into a public
attestation.

## Deterministic identity

Attestations are serialized as canonical JSON with sorted keys and compact separators. Artifact,
adapter, and dependency collections are normalized before hashing, so caller ordering does not
change identity. The semantic digest is SHA-256 and the human-readable ID is derived from it:

```text
EATT-<first 24 uppercase hex characters of semantic SHA-256>
```

Supplying a pre-existing `attestation_id` or `content_sha256` causes validation to fail if either no
longer matches the immutable semantic fields. Changing source, builder, artifact, verifier,
qualification, adapter, dependency, or SBOM identity therefore changes the attestation identity.

## Qualification binding

`QualificationBinding.from_maturity_record(record)` projects only the stable identities needed to
bind an attestation to an already validated `MaturityRecord`:

- maturity record ID;
- qualification identity;
- achieved maturity status;
- qualification policy ID and version;
- environment content digest; and
- verifier content digest.

The attestation rejects a `DRAFT` binding and rejects qualification bindings whose environment or
verifier digest does not match the attested environment and verifier. It does not recalculate the
maturity gates; that remains the responsibility of the qualification subsystem.

## Detached signing

`AttestationSignature` is deliberately separate from `EnvironmentAttestation`. A signature binds the
attestation ID and semantic content digest, but signature bytes, key identity, and signing algorithm
are not inputs to the semantic attestation hash.

This separation preserves two independent questions:

1. **Semantic integrity:** do the attestation contents produce the claimed content digest and ID?
2. **Cryptographic/authorship trust:** does an authorized key produce a valid signature over that
   digest?

An unsigned attestation can therefore be semantically valid, while a signature can independently be
missing, invalid, expired, unauthorized, or otherwise unacceptable to a release policy. Signing must
never be treated as a substitute for environment qualification.

## Consumer boundary

PKG-001 or another packaging layer may consume these objects by embedding or referencing the
attestation ID/content digest and, separately, any accepted detached signatures. This module does
not define a package format, publish a release, modify exporters, or alter release workflows.
