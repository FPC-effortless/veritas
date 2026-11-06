# Veritas 0.11.0 Marketplace Release Packet

This document is the buyer-safe handoff for submitting the first Veritas commercial release to external environment/evaluation platforms.

## Canonical release

- Software: **Veritas 0.11.0**
- Git tag / GitHub release: **`v0.11.0`**
- Primary SKU: **Veritas SRE Evaluation Pack v1**
- Public software license: **Apache-2.0**
- Private benchmark assets: **Veritas Commercial Restricted Assets — All Rights Reserved** under `LICENSING.md`

The GitHub release contains the Python wheel/source distribution, `SHA256SUMS`, CycloneDX SBOM, release provenance, portability identities, root license and licensing policy. The release container is pinned by digest in the provenance record.

## Primary SKU

Veritas SRE Evaluation Pack v1 evaluates whether an AI model or agent can infer the likely causal class of an active service incident from incomplete early evidence without access to later resolution notes.

The frozen SRE v4 release contains:

- 87 total scenarios;
- 30 private-test cases;
- four causal classes with material private support;
- 18/18 scientific qualification gates passed;
- immutable candidate, evidence, qualification, panel and private-release identities;
- sealed private benchmark transport and buyer-safe aggregate reporting.

## Commercial proof already completed

The exact sealed 30-case panel has been exercised through two real open-model families:

- Qwen2.5-0.5B-Instruct: balanced accuracy 25.0%, macro F1 13.2%, parse failures 0/30;
- SmolLM2-360M-Instruct: balanced accuracy 12.5%, macro F1 9.5%, parse failures 17/30.

A customer-equivalent authenticated OpenAI-compatible endpoint rehearsal also completed all 30 cases with one attempt, zero retries, zero operator interventions and exact buyer-safe metric reproduction.

These results prove execution/reproducibility of the commercial pack. They are not a claim that SRE v4 is already frontier-qualified; Frontier Qualification remains a separate evidence gate.

## What is public

The public repository and release may expose:

- framework/runtime code;
- portable schemas and adapter code;
- buyer-safe manifests and release identities;
- aggregate qualification evidence;
- public/sample tasks explicitly committed under the repository license;
- benchmark methodology and limitations.

## What remains private

The following must not be uploaded to a public marketplace listing, public Hub package, public issue, or public artifact:

- raw SRE v4 private task rows;
- canonical private scenario identities;
- evaluator-only causal labels and hidden truth;
- private source snapshots;
- decryption material or secret-bearing paths;
- customer credentials or customer-confidential model outputs.

Operator-private HUD/Prime exports may contain the restricted task material only inside authorized evaluator infrastructure and remain governed by the commercial licensing policy.

## Offer structure

The first commercial release supports three buyer motions:

1. **Private model/agent evaluation** — buyer supplies a model endpoint, harness or checkpoint; Veritas returns a buyer-safe scorecard and failure analysis.
2. **Environment/taskset license** — non-exclusive access to an authorized environment/taskset package under transaction-specific terms.
3. **Custom capability environment** — commissioned construction of a task distribution, executable world, verifier, adversarial cases and evaluation/training assets for a buyer-defined capability.

No exclusivity should be implied unless separately negotiated and priced.

## Platform strategy

### HUD

Use the qualified private SRE SKU as the commercial asset. The generated HUD package has already passed clean SDK installation, Docker build, live task-start/task-grade smoke tests, deterministic reset and canonical reward-parity validation in Veritas portability CI.

Remaining external action: authenticate to HUD, deploy/run the generated package in the seller account, inspect HUD-native traces/QA, and submit the DataVendor intake.

### Prime Intellect

Use a public/sanitized Verifiers v1 environment as the Hub-facing artifact. Do not publish the private SRE v4 panel. The public environment should expose the verifier-compatible task/harness shape and buyer-safe sample/public tasks, while the private panel remains a separate commercial evaluator asset.

The generated Prime package has already passed Verifiers v1 taskset loading, compatibility loading, standalone wheel build, deterministic identity and canonical reward-parity checks.

Remaining external action: authenticate with the Prime CLI, push the sanitized environment to the Environments Hub, run a Hosted Evaluation, then use the resulting Hub page and evaluation as the external technical proof for partnership/bounty discussions.

## Buyer-safe links

- Repository: `https://github.com/FPC-effortless/veritas`
- Release: `https://github.com/FPC-effortless/veritas/releases/tag/v0.11.0`
- Commercial package docs: `docs/commercial/`
- SRE SKU: `docs/commercial/sre-evaluation-pack-v1.md`
- Portability contract: `docs/portability/README.md`
- Licensing policy: `LICENSING.md`

## Commercial inquiry route

Use the repository's **Commercial evaluation inquiry** issue template for buyer-safe initial contact. Sensitive endpoint details, credentials, customer data and private benchmark content must move to an agreed private channel before integration.
