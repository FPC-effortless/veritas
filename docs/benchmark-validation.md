# Benchmark validation harness

The validation harness tests whether a CompanyWorld benchmark is internally valid, publicly solvable, deterministic, and resistant to simple reward exploits before any model evaluation is trusted.

## Run

```bash
iworld benchmark-companyworld \
  /path/to/companyworld_v0_1 \
  --output runs/companyworld/benchmark-validation.json
```

Use `--limit N` for a smoke run. Use `--skip-determinism` only when compilation cost matters and determinism has already been checked for the exact benchmark build.

## Oracle-blind policies

All ordinary policies receive only `episode.public_payload()`:

- `empty`
- `conclusion_only`
- `always_abstain`
- `cite_everything`
- `projection_trust`
- `field_stuffing`
- `public_evidence_reference`

The first six are exploit or degenerate baselines. `public_evidence_reference` is a deterministic public-evidence solver for the currently supported CompanyWorld task families.

The harness also runs two privileged controls:

- `privileged_oracle` proves the verifier can award the maximum score to the exact hidden answer with direct evidence.
- `oracle_without_evidence` proves that a correct unsupported answer scores below a correct evidence-backed answer.

## Required invariants

A passing report requires:

- CompanyWorld source integrity checks pass;
- zero public/private oracle-field leakage;
- every answerable task has observable records and direct supporting evidence;
- privileged oracle minimum reward is 1.0;
- public-evidence reference solver minimum reward is 1.0;
- empty, conclusion-only, abstention, citation-only, and blind divergent-projection policies have maximum reward 0;
- field stuffing remains bounded at or below 0.25 reward;
- unsupported correct answers score below evidence-backed correct answers;
- repeated compilation produces an identical public-payload SHA-256 when determinism validation is enabled.

## Report

The JSON report includes:

- task-family counts and train/public/private split sizes;
- every invariant with observed and expected values;
- per-policy mean/min/max/median/p95 reward;
- non-zero and perfect-score rates;
- per-family policy statistics;
- the deterministic public-payload hash;
- source validation metadata.

A benchmark should not be promoted to a public or private evaluation set unless this report passes. Model evaluation comes after benchmark validation, not before it.
