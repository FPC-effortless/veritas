# Prime Intellect Environments Hub Submission Packet

## Publication strategy

Prime's Environments Hub is a public/open distribution surface. Publish a **sanitized Verifiers v1 environment**, not the frozen SRE v4 private panel.

Recommended Hub name:

`veritas-sre-open`

The Hub artifact exists to demonstrate Veritas's verifier-compatible environment architecture and create an externally hosted evaluation surface. The commercially valuable private SRE panel remains evaluator-side and is licensed separately.

## Suggested Hub description

Verifier-grounded operational incident diagnosis under incomplete and conflicting early evidence. Veritas SRE Open exposes a public/sample taskset and deterministic scorer compatible with Prime Intellect Verifiers v1. It is derived from the same portable environment contract used by Veritas's qualified private SRE evaluation SKU, but does not contain the frozen private panel, private source snapshots, canonical private scenario IDs, hidden causal truth or decryption material.

## Recommended metadata

- Name: `veritas-sre-open`
- Version: `0.11.0`
- License: Apache-2.0 for the public package material
- Tags: `evaluation`, `agents`, `sre`, `incident-response`, `reasoning`, `verifiers`, `tool-use`
- Repository: `https://github.com/FPC-effortless/veritas`
- Release: `https://github.com/FPC-effortless/veritas/releases/tag/v0.11.0`

## Public/private boundary

May be pushed publicly:

- Verifiers v1 loader/taskset/scorer code;
- buyer-safe/public sample tasks;
- public documentation and qualification methodology;
- portable manifest fields cleared for public distribution;
- public package metadata and licensing notice.

Must not be pushed publicly:

- 30 frozen SRE v4 private rows;
- expected private causal labels;
- canonical private scenario IDs;
- private snapshots or later-evidence source material;
- private release bundle;
- seal/decryption material;
- customer data or credentials.

## Existing Prime validation

Veritas 0.11 portability validation already checks:

- clean installation of the external Verifiers dependency;
- Verifiers v1 `SRETaskset` loading;
- deterministic task identities and reward parity;
- legacy `load_environment()` compatibility bridge;
- standalone Prime wheel build outside the Veritas repository layout;
- sealed SRE package identity and private task count;
- buyer-safe/private leakage boundaries.

This is repository-controlled compatibility evidence. A Prime-account Hub push and Hosted Evaluation are still required for external platform-native proof.

## Seller-account publication run

1. Create/log into a Prime Intellect account and set a Hub username.
2. Install/configure Prime CLI and run `prime login`.
3. Generate or stage the **public/sanitized** Prime package only.
4. From the environment directory, test the package locally with the current Verifiers evaluation command.
5. Verify the staged directory does not contain private SRE task rows, hidden labels, private snapshots, decryption material or developer-local paths.
6. Push with `prime env push` (or `prime env push --team <team>` if publishing under a team).
7. Confirm `prime env info <owner>/veritas-sre-open` and installability from a clean environment.
8. Run a Hosted Evaluation against at least two materially different model strengths if budget/credits permit.
9. Record the Hub environment URL/version and hosted evaluation result in the Veritas commercial evidence record.
10. Use the public Hub environment plus immutable Veritas release as the completed-project link for Prime environment-program/partner applications.

## Hosted-evaluation acceptance criteria

A Prime-native proof should be counted only when:

- the environment installs from the Hub rather than a developer checkout;
- the expected Veritas/portable version is visible;
- at least one evaluation completes end-to-end;
- task/reward behavior agrees with the canonical public/sample reference;
- no private benchmark material is exposed through package contents, prompts, logs or metrics;
- the resulting Hub/evaluation page can be referenced externally.

A stronger proof uses at least two model strengths and reports parse reliability plus reward/capability differences. Do not infer frontier qualification from one Hosted Evaluation.

## Prime program/partner pitch

Veritas is a released verifier-grounded environment system with qualified private evaluation assets and a vendor-neutral portability layer. The 0.11.0 release includes a Prime Verifiers v1 taskset adapter, deterministic reset/reward semantics and buyer-safe/private separation. SRE v4 is scientifically qualified and commercially sealed; CompanyWorld has replicated within-family training-value evidence. We are seeking externally hosted strong-model evaluation and collaboration on scaling operational environments toward frontier qualification, while keeping private evaluator truth separate from the public Hub artifact.

## Submission links

- Repository: `https://github.com/FPC-effortless/veritas`
- Release: `https://github.com/FPC-effortless/veritas/releases/tag/v0.11.0`
- Marketplace packet: `docs/commercial/marketplace-release.md`
- Portability contract: `docs/portability/README.md`
- Licensing: `LICENSING.md`
