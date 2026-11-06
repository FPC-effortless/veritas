# Prime Intellect Environments Hub Submission Packet

## Two-stage publication strategy

Prime's current Environments Hub supports both private and public environment visibility. Use two separate artifacts and do not collapse their trust boundaries.

### Stage 1 — fastest platform-native proof

Generate the existing **operator-private** SRE package from the exact sealed SRE v4 release, then push it with `--visibility=PRIVATE`. This can establish Prime-native installation/evaluation evidence without publishing the frozen private panel.

### Stage 2 — public distribution

Publish the repository's ready-to-push sanitized environment:

`integrations/prime/veritas-sre-open/`

Hub name:

`veritas-sre-open`

This public package contains 12 balanced **project-authored synthetic** demonstration tasks plus the Verifiers v1 taskset/scorer and compatibility entrypoint. It is intentionally not the qualified SRE v4 private benchmark. The commercially valuable private SRE panel remains evaluator-side and is licensed separately.

## Suggested Hub description

Verifier-grounded operational incident diagnosis under incomplete early evidence. Veritas SRE Open exposes 12 balanced project-authored synthetic tasks and a deterministic scorer compatible with Prime Intellect Verifiers v1. It demonstrates the public integration semantics used by Veritas while containing no frozen private SRE rows, private source snapshots, canonical private scenario IDs, private release identities or decryption material.

## Package metadata

- Name: `veritas-sre-open`
- Version: `0.11.0`
- License: Apache-2.0
- Tags/keywords: `evaluation`, `agents`, `sre`, `incident-response`, `reasoning`, `verifiers`
- Repository: `https://github.com/FPC-effortless/veritas`
- Release: `https://github.com/FPC-effortless/veritas/releases/tag/v0.11.0`
- Ready-to-push directory: `integrations/prime/veritas-sre-open/`

## Public/private boundary

May be pushed publicly:

- `integrations/prime/veritas-sre-open/`;
- Verifiers v1 loader/taskset/scorer code in that package;
- its 12 project-authored synthetic tasks and public reference labels;
- public documentation and qualification methodology;
- public package metadata and Apache-2.0 license.

Must not be pushed publicly:

- the 30 frozen SRE v4 private rows;
- expected private causal labels;
- canonical private scenario IDs;
- private snapshots or later-evidence source material;
- private release bundle or generated operator-private `private_tasks.json`;
- seal/decryption material;
- customer data or credentials.

## Existing Prime validation

Veritas 0.11 portability validation checks the generated sealed/private package for:

- clean installation of the external Verifiers dependency;
- Verifiers v1 `SRETaskset` loading;
- deterministic task identities and reward parity;
- legacy `load_environment()` compatibility bridge;
- standalone Prime wheel build outside the Veritas repository layout;
- sealed SRE package identity and private task count;
- buyer-safe/private leakage boundaries.

The `veritas-sre-open` integration adds a separate CI gate that installs the current external `verifiers` SDK, builds the public wheel, loads all 12 v1 tasks, and loads the compatibility entrypoint before merge.

Repository-controlled compatibility evidence is not a substitute for a Prime-account Hub push and Hosted Evaluation.

## Stage 1: private Prime proof

1. Create/log into Prime Intellect and set a Hub username.
2. Install the CLI: `uv tool install -U prime`.
3. Authenticate: `prime login`.
4. From the Veritas 0.11.0 checkout, generate the exact operator package against the sealed SRE v4 `qualification.json` using `tools/export_sre_portable_package.py --adapter both`, including the pinned expected release identities and source-bundle SHA used by the 0.11 proof.
5. Enter the generated Prime directory and install it locally.
6. Push it privately: `prime env push --visibility=PRIVATE`.
7. Verify clean Hub installation outside the developer checkout.
8. Run a Hosted Evaluation and store the private Hub/run identifiers in the operator evidence record.
9. Publish only buyer-safe aggregate evidence, never the private package contents or task rows.

## Stage 2: public Hub publication

From a clean `v0.11.0`-compatible checkout containing the merged public package:

```bash
cd integrations/prime/veritas-sre-open
uv pip install -e .
uv run vf-eval veritas-sre-open
prime env push
```

After upload:

1. Record the exact `<owner>/veritas-sre-open` identifier and version shown by Prime.
2. Inspect/package-check the Hub artifact before any evaluation.
3. Verify a clean install with `prime env install <owner>/veritas-sre-open`.
4. Run a one-example Hosted Evaluation first, then the full 12-example synthetic set if the smoke run is correct.
5. Prefer at least two materially different model strengths for the external evidence table.
6. Record the Hub URL/version and Hosted Evaluation result in the Veritas commercial evidence record.
7. Use the live public Hub environment plus immutable Veritas release as the completed-project link for Prime environment-program/partner applications.

Prime's current CLI evaluation pattern supports hosted runs such as:

```bash
prime eval run <owner>/veritas-sre-open --model openai/gpt-oss-20b --hosted
```

Use a model available in the account at execution time; do not hard-code commercial claims to one provider/model merely because it appears in an example.

## Hosted-evaluation acceptance criteria

A Prime-native proof should be counted only when:

- the environment installs from the Hub rather than a developer checkout;
- the expected public package version is visible;
- at least one evaluation completes end to end;
- task/reward behavior agrees with the public synthetic references;
- no private benchmark material is exposed through package contents, prompts, logs or metrics;
- the resulting Hub/evaluation page or buyer-safe record can be referenced externally.

A stronger proof uses at least two model strengths and reports parse reliability plus reward/capability differences. Do not infer scientific qualification or frontier qualification from the 12-task public synthetic environment or one Hosted Evaluation.

## Prime program/partner pitch

Veritas is a released verifier-grounded environment system with qualified private evaluation assets, an explicitly non-qualified public integration environment and a vendor-neutral portability layer. The 0.11.0 release includes a Prime Verifiers v1 private taskset adapter, deterministic reset/reward semantics and buyer-safe/private separation. SRE v4 is scientifically qualified and commercially sealed; CompanyWorld has replicated within-family training-value evidence. We are seeking externally hosted strong-model evaluation and collaboration on scaling operational environments toward frontier qualification, while keeping private evaluator truth separate from the public Hub artifact.

## Submission links

- Repository: `https://github.com/FPC-effortless/veritas`
- Release: `https://github.com/FPC-effortless/veritas/releases/tag/v0.11.0`
- Public Hub package source: `integrations/prime/veritas-sre-open/`
- Marketplace packet: `docs/commercial/marketplace-release.md`
- Portability contract: `docs/portability/README.md`
- Licensing: `LICENSING.md`
