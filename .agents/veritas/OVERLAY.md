# Veritas Scientific and Product Overlay

This overlay specializes the Universal Coding Agent Contract for Veritas.

## Qualification separation

Always distinguish:

1. **Implementation verification** — code behaves as specified.
2. **Scientific qualification** — benchmark/environment evidence satisfies the scientific qualification contract.
3. **Frontier qualification** — a scientifically valid environment has evidence that it differentiates and is useful for improving current strong/frontier agents.
4. **Commercial/release readiness** — buyer-safe packaging, privacy, operational reproducibility, CI/security, release identity, and deployment/admin requirements are satisfied.

No layer implies the next. Missing evidence yields `UNKNOWN`, `NOT_QUALIFIED`, or `NOT_YET_FRONTIER_QUALIFIED` as defined by the active subsystem; never infer PASS.

## Benchmark/environment integrity

Treat these as first-class failure modes:
- train/test or source leakage;
- near-duplicate contamination;
- hidden-label exposure;
- reward/verifier gaming;
- majority-class or stratum imbalance;
- policy-ordering failure;
- exploit policy success;
- nondeterministic replay where determinism is promised;
- insufficient task diversity;
- calibration failure;
- ceiling/floor saturation;
- weak discrimination among strong agents;
- private artifact exposure;
- using public evidence to claim private-panel performance.

## Evidence semantics

Strong empirical claims require the evidence level specified by the active contract. Where replication/uncertainty is material, report seeds/replicates, effect sizes, intervals or variability, failures, and limitations. A successful single run is not automatically a validated scientific claim.

## Private/sealed data

Never print or persist private scenario IDs, expected labels, hidden oracle rows, decrypted bundles, or secret-bearing paths into public files/logs/artifacts unless the release contract explicitly permits the specific field. Buyer-safe/public artifacts must remain sanitized.

## Expensive/manual workflows

Model calibration, training-value runs, sealed-panel evaluation, pilot dress rehearsal, or similar expensive workflows stay manual/controlled when repository policy marks them so. Ordinary code changes should use cheap deterministic tests first.

## Parallel work

When a task gives strict file ownership, treat it as a hard boundary. Do not opportunistically edit adjacent files owned by another active branch/agent. Prefer additive docs/tests/adapters or a follow-up issue over cross-branch conflict.

## Release discipline

Use `BUILD_STATUS.md` and exact release workflows as current release authority. Do not assume a target version or release state from stale conversation context.
