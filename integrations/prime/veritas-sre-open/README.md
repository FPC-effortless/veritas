# Veritas SRE Open

`veritas-sre-open` is the public Prime Intellect / Verifiers integration surface for Veritas SRE causal-class evaluation semantics.

It contains **12 project-authored synthetic demonstration tasks**, balanced across four causal classes:

- `regression`
- `infrastructure`
- `capacity`
- `transient`

This package is intentionally **not the qualified SRE v4 private benchmark**. It does not contain frozen private task rows, source snapshots, canonical private scenario identifiers, hidden private evaluator truth, private release identities, or decryption material. It is an integration/evaluation sample for public Hub distribution.

## What it demonstrates

Each task gives an incident description and asks the model to return exactly one causal class:

```json
{"causal_class":"capacity"}
```

The reward is binary: `1.0` only when the parsed class exactly matches the public synthetic reference label, otherwise `0.0`.

The package exports both:

- `SREOpenTaskset` using `verifiers.v1`;
- `load_environment()` as the compatibility entrypoint used by current Environments Hub workflows.

## Local installation

```bash
uv pip install -e .
```

## Local evaluation

Using the compatibility workflow described by Prime:

```bash
uv run vf-eval veritas-sre-open
```

For current Verifiers v1 tooling, the package also exposes `SREOpenTaskset` directly.

## Prime Environments Hub

Authenticate the Prime CLI:

```bash
uv tool install -U prime
prime login
```

Push from this directory:

```bash
prime env push
```

A private publication can be used first for platform-native verification:

```bash
prime env push --visibility=PRIVATE
```

After upload, verify installation from a clean workspace using the environment identifier shown by Prime, then run a Hosted Evaluation.

## Commercial/private SRE evaluation

The qualified commercial SRE Evaluation Pack v1 remains a separate evaluator-side asset governed by the Veritas commercial licensing boundary. See:

- `https://github.com/FPC-effortless/veritas/blob/main/docs/commercial/sre-evaluation-pack-v1.md`
- `https://github.com/FPC-effortless/veritas/blob/main/LICENSING.md`

Do not infer scientific qualification, frontier qualification, or production readiness from scores on this 12-task public synthetic integration sample.

## License

The code and project-authored synthetic tasks in this package are released under Apache-2.0.
