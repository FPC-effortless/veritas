# Veritas Benchmark Release and Score-Compatibility Policy

## Commercial benchmark identity

The first sellable benchmark line is **Veritas CompanyWorld Pilot v1**. Software package version `0.5.0` is the initial release vehicle for this commercial line.

Every customer run must record:

- benchmark name and version;
- immutable benchmark/private-suite hash;
- Veritas software release/tag or commit;
- evaluated model identifier;
- harness/adapter version;
- attempts per task;
- applicable token, tool, time, and retry budgets;
- run identifier and timestamp.

## Private assets

Private seeds, hidden world truth, evaluator oracles, answer keys, unreleased adversarial suites, and customer-specific benchmark mutations are never committed to the public repository. The operator stores them in access-controlled private storage and records only a non-reversible content hash in customer-facing run metadata.

## What changes require a new benchmark version

Create a new benchmark version whenever a change can materially alter score meaning, including:

- verifier weights or hard gates;
- task-family distribution;
- difficulty distribution or materializer semantics;
- private world generator semantics;
- tool availability/cost model;
- authority or policy rules;
- observation/evidence projection rules;
- answer schemas or scoring normalization.

Bug fixes that provably do not alter any frozen task observation, oracle, or score may keep the same benchmark version, but the software patch version and release notes must change.

## Historical-score compatibility

Scores from different benchmark versions must not be compared as if they are the same measurement. If a buyer needs a longitudinal comparison after a benchmark revision, rerun both systems on the same frozen benchmark version or explicitly label the comparison as cross-version and non-equivalent.

## Release gate

A commercial release is eligible only when:

1. CI and security workflows pass on the exact release commit;
2. public/private leakage tests pass;
3. reference/oracle solvability checks pass;
4. exploit-resistance checks pass;
5. deterministic recompilation/replay checks pass where applicable;
6. the operator records the private suite hash and asset location;
7. release notes identify methodology-affecting changes;
8. no draft research branch is silently included in the release.

## Customer communication

Each report must state the benchmark version and hash. Re-evaluation after a customer model/harness change should use the same frozen version unless both parties explicitly agree to a new benchmark version.
