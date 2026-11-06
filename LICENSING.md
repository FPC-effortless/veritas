# Veritas licensing policy

This file defines the licensing boundary between the public Veritas framework and commercially restricted evaluation/training assets. Transaction-specific written terms override the defaults below for the assets covered by that transaction.

## 1. Public Veritas framework

The Veritas source code and other project-authored material committed to this public repository are licensed under the **Apache License 2.0** in the root `LICENSE`, unless a file or directory carries a different license notice.

This public grant includes project-authored public schemas, documentation, synthetic examples, public test fixtures and buyer-safe sample artifacts that are committed to the repository, unless they are explicitly marked otherwise.

Third-party material is not relicensed merely because it is referenced by, processed by, or temporarily used with Veritas. Upstream copyright, database, API, dataset and service terms continue to apply.

The adapted agent skills under `.agents/skills/` retain their own included license notice where applicable.

## 2. Private benchmark and evaluation assets

The following are **not** licensed under Apache-2.0 unless a separate file explicitly says otherwise:

- frozen private SRE seeds, scenario identities and task rows;
- evaluator-only labels, causal truth, oracle state and hidden scoring data;
- private benchmark panels and private release manifests;
- unreleased adversarial suites;
- private source snapshots and evidence bundles;
- customer-specific private benchmark material.

These assets are **Veritas Commercial Restricted Assets — All Rights Reserved**. Possession or access does not grant a redistribution, publication, sublicensing, training, derivative-dataset, or benchmark-reconstruction right. Authorized use exists only to the extent stated in a written order, statement of work, marketplace transaction, evaluation agreement or other commercial agreement issued for the asset.

For evaluation-only SRE packages, the default permitted use is to run the package for the named customer or engagement and receive scores/aggregate evidence. Raw private tasks, labels and hidden truth may not be disclosed to the evaluated model or published as buyer-safe artifacts.

## 3. Customer evaluation outputs

Unless a transaction says otherwise, a customer receiving a paid Veritas evaluation receives a perpetual, non-exclusive right to use the delivered **customer-facing evaluation outputs** internally for model selection, engineering, safety, research, procurement and deployment decisions.

Customer-facing evaluation outputs can include scorecards, aggregate metrics, failure analyses, representative buyer-safe trajectories, recommendations and engagement reports.

This default does not grant the right to publish or redistribute hidden benchmark material, private task rows, evaluator-only labels, source snapshots, decryption material or other restricted assets that may have been used to produce the outputs.

A customer may cite aggregate results publicly if doing so does not disclose restricted benchmark content and does not imply Veritas endorsement. Transaction-specific confidentiality terms take precedence.

## 4. Generated training data

Generated training datasets, verified demonstrations, preference pairs, recovery traces and other training assets that are delivered commercially but are not committed to the public repository are governed by the applicable order. Unless that order says otherwise, the default license is:

- non-exclusive and worldwide for the named customer;
- usable for internal research, supervised fine-tuning, preference learning, reinforcement learning, distillation, evaluation and commercial model development;
- resulting model weights, checkpoints and model outputs may be used commercially;
- raw delivered training data may not be resold, sublicensed or redistributed as a standalone dataset;
- contractors acting solely for the customer may process the data subject to equivalent confidentiality/use restrictions;
- the data may not be used to reconstruct, disclose or contaminate a separately restricted private Veritas benchmark unless that benchmark is expressly licensed for training use.

A marketplace listing or signed order may grant broader redistribution, derivative-dataset or multi-affiliate rights.

## 5. Buyer-safe portability metadata

Buyer-safe portability manifests, aggregate qualification evidence, package identities, hashes and release/provenance records that are committed to this repository are public repository material under Apache-2.0. They intentionally exclude private task rows and hidden scoring truth.

Generated operator-private HUD/Prime packages remain restricted to the extent they contain `private_tasks`, evaluator labels, hidden truth or other commercial assets, even when their wrapper code was generated from Apache-2.0 source code.

The `licensing` field value `repository-license` in a portable manifest resolves to the root **Apache-2.0** license for public Veritas code. `commercial-restricted` identifies material governed by Section 2 and the applicable commercial order.

## 6. License precedence

When more than one notice appears to apply, use this order:

1. a signed/order-specific commercial agreement for the named asset;
2. an asset- or directory-specific license notice;
3. this licensing policy;
4. the root Apache-2.0 license for project-authored public repository material.

Nothing in the public Apache-2.0 grant conveys rights to private material that is not part of the licensed public Work.
