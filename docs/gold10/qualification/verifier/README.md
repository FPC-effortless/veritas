# Gold-10 verifier qualification

`GOLD-VQ-001` is the provider lane between the merged executable Gold-10 pilot and
Gold-10 scientific/red-team qualification.

It does **not** modify `src/investigation_world/gold10/**`. The verifier being judged
is frozen input. This package composes the canonical Veritas verifier-qualification
models with Gold-10 task identity and candidate aggregation.

## Authority

A successful candidate may establish only `VERIFIER_VALIDATED` evidence. It does not
establish scientific, Frontier, training-value, learning-efficiency, release, or
commercial qualification.

Per-task evidence is mandatory. The candidate cannot pass by averaging a failed or
required-UNKNOWN task away. A material change to a Gold-10 task manifest, verifier
identity, or verifier-target contract invalidates the bound qualification record.

## Applicability

The generic verifier suite intentionally contains broad operational categories. A
Gold-10 task may not expose every category, for example a mutable side-effect surface.
Such a dimension must remain explicit as `NOT_APPLICABLE` with a rationale. It cannot
be used to erase an observed failure. Any unclassified UNKNOWN remains required and
therefore keeps that task and the whole candidate UNKNOWN.

## Next implementation step

The fixture compiler must produce deterministic canonical `VerifierFixtureManifest`
and `VerifierReplay` evidence for every one of the ten frozen tasks. It must retain
permanent exploit fixtures covering the shortcut classes discovered while PR #354 was
reviewed, including unrelated-target hypothesis laundering, arbitrary structured
calibration, confidence-role inversion, target/evidence drift, hindsight evidence,
and malformed/unsupported claims.
