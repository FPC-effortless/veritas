# HUD / DataVendor Submission Packet

## Asset

**Veritas SRE Evaluation Pack v1** — a verifier-grounded private evaluation environment for operational incident-cause diagnosis from incomplete early evidence.

## One-paragraph submission description

Veritas builds qualified, verifier-grounded environments for training and evaluating AI agents in persistent or partially observable operational worlds. The first commercial SKU is SRE Evaluation Pack v1: a frozen, source-disjoint 30-case private panel drawn from 87 qualified incident scenarios across 16 source families, with four causal classes, immutable release identities, hidden evaluator truth and buyer-safe reporting. The exact sealed panel has been run against two real model families and through an authenticated customer-equivalent OpenAI-compatible endpoint rehearsal. Veritas 0.11.0 adds a standalone HUD v6 package with deterministic reset, canonical reward parity, opaque private task identities and leak-resistant metering.

## Buyer problem

The pack is intended for model-selection, regression, harness and post-training decisions where a buyer needs to know whether an agent can infer incident cause from the evidence available while an incident is still unfolding, rather than from later resolution notes.

## What HUD can receive safely

Buyer-safe/public material:

- repository and immutable `v0.11.0` release;
- portable environment manifest;
- qualification evidence summary;
- package/release identities and hashes;
- HUD adapter/runtime code;
- public/sample tasks explicitly cleared for publication;
- benchmark card and limitations.

Restricted material, only after appropriate marketplace/NDA/evaluator boundary:

- frozen private SRE v4 task rows;
- evaluator-only labels/hidden truth;
- private source snapshots;
- operator-private package material.

## Existing HUD validation

Veritas portability validation already checks:

- clean external HUD SDK installation;
- standalone HUD Docker image build;
- live HUD task start and task grade;
- deterministic reset;
- canonical reward parity;
- unique opaque portable task identities even where public digests collide;
- no canonical private scenario IDs in generated records;
- buyer-safe aggregate qualification evidence;
- metering events without prompt/private-label leakage;
- exact sealed SRE release identity and private task count.

This is repository-controlled portability evidence. A seller-account HUD deployment is still required to create the external platform-native proof.

## Commercial motions

1. Private evaluation access.
2. Non-exclusive environment/taskset licensing.
3. Custom operational capability environments for buyer-defined tasks.

## Suggested DataVendor intake answers

**What are you providing?**

Verifier-grounded RL/evaluation environments, private tasksets and custom operational capability environments for agent training and evaluation.

**What makes it differentiated?**

Veritas separates agent-visible evidence from independently maintained hidden truth; freezes qualified private panels; validates contamination/leakage, deterministic replay, exploit policies and verifier behavior; and ships buyer-safe scorecards without exposing the private oracle.

**Current readiness?**

Released as Veritas 0.11.0. Primary SRE SKU is scientifically qualified, sealed, real-model tested, endpoint-rehearsed and exported through a standalone HUD package. Frontier qualification is a separate gate and is not implied.

**Rights/provenance?**

Public project-authored code is Apache-2.0. Private benchmark/evaluator assets are commercial restricted assets under `LICENSING.md` and are licensed only under a marketplace transaction or written commercial agreement. Third-party rights are not relicensed by Veritas.

**Buyer use cases?**

Model/harness selection, pre/post-training evaluation, regression testing, agent reliability analysis, and commissioned environment construction.

## Seller-account acceptance run

Before representing the package as HUD-native externally validated, complete all of the following inside the seller HUD account:

1. Authenticate to HUD and create/select the seller project.
2. Deploy the generated SRE HUD package from the exact `v0.11.0` release/export.
3. Run a small buyer-safe/public task sample first.
4. Confirm task-start and task-grade complete on HUD infrastructure.
5. Inspect trace/reward output for grader errors, reward hacking and unexpected private-field exposure.
6. Run wrong/empty/malformed and correct reference behaviors where the HUD QA surface permits them.
7. Record HUD environment/package identity and run links in a private operator record; publish only buyer-safe identifiers.
8. Submit the DataVendor vendor intake at `datavendor.ai` and reference the release plus HUD-native proof.

## Submission links

- Release: `https://github.com/FPC-effortless/veritas/releases/tag/v0.11.0`
- Repository: `https://github.com/FPC-effortless/veritas`
- Commercial packet: `docs/commercial/marketplace-release.md`
- SRE pack: `docs/commercial/sre-evaluation-pack-v1.md`
- Portability: `docs/portability/README.md`
- Licensing: `LICENSING.md`
