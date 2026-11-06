# WIL-TRAIN-001 / Counterfactual State Acquisition — NO-FIT v0.1

**Status:** synthetic TRAIN/diagnostic DEV fixture; not a trained model, sealed test, scientific validation, or authority to spend GPU/paid compute. Source program: [Veritas issue #496](https://github.com/FPC-effortless/veritas/issues/496).

## Scientific question

At matched architecture, labels, data tokens and measured optimizer FLOPs, does paired relevant/irrelevant revision training improve models' ability to reconstruct current multi-key state from *their learned compressed representation*, compared with equally capable answer-supervised controls? Test two architecture families before promotion.

## Task construction

A public toy world maps `(owner, item)` to one location or absence. Two arms share a prefix, identical question and identical final sentence; precisely one penultimate event differs. A paired relevant edit has opposite answers; an irrelevant edit has the same answer; retraction has one unknown and one known answer. Noise updates and competing keys are included. Deterministic seed, event oracle, SHA256 export manifest, strong syntax family holdout.

`model_view(row)` returns **only history and query**. `answer`, `pair_id`, `kind`, `split` and `arm` are evaluator/training metadata and **must never enter the model input**. Cross-arm metadata must not influence inference. Data has public labels for TRAIN and both diagnostic DEV splits. This is not a private or sealed TEST set: a separate independently generated and access-controlled test panel must be preregistered.

## Current checks and falsifiers

1. Repeated generators produce identical bytes and hashes; different split seeds.
2. Same-prefix, one semantic-event change, identical post-edit suffix/query; every answer replays from the independent typed event oracle.
3. Exactly one opposing answer per `relevant_edit` or `retraction` pair; identical answers for irrelevant changes.
4. For conflicting pair answers, a predictor given only the common query/suffix cannot score more than one of two, regardless of its fixed answer. This is a pair-wise upper bound, not a global 50% majority-class bound.
5. Tampering one label must fail validation; no oracle or answer may be passed by `model_view`.
6. `dev_ood_syntax` has a disjoint surface grammar, but **not** disjoint underlying concepts. OOD syntax performance will not demonstrate general causal semantics.

## Proposed training controls; no fits yet

A. CE on exactly the same labeled examples (including paired edits) with ordinary sampling.
B. A plus pair loss. Since pair losses often just reweight the same CE labels, include a **CE-hard-example / pair-balanced reweighting control**.
C. B plus invariant predictions for irrelevant edits, anchored to CE.
D. C plus explicit history-erasure and recomputation/update consistency. For every architecture, make the history truly inaccessible after state extraction, including KV/scratch leak tests.
E. Future stage: randomized action-conditioned simulator dynamics with independent outcome verification. Do not call passive narrated edit pairs real-world `do(a)` interventions.

Predeclare both matched-tokens and matched-training-FLOPs comparisons; auxiliary losses consume compute. Require 5 seeds and architecture-qualified baselines (Transformer, recurrent/modern SSM) with observed parameters ±5% and enough state capacity. Report per-seed results, uncertainty, training seconds and memory bytes; do not promote based on a weak comparator.

## Capacity feasibility lower bound

If a model must reconstruct **all K independently chosen values**, each with `V` equiprobable alternatives, from a finite discrete state representation with `B` bits, perfect reconstruction for every possible world requires `B >= K*log2(V)`. This follows by the pigeonhole principle. It does not directly impose a hard limit on idealized real-valued neural states or approximate query-weighted recovery; quantify effective numerical precision and resource limits before using it for architecture comparisons.

## Novelty boundaries

NextLat already trains predictive latents; State Commitment Learning already trains retention through counterfactual erasure; Causal-JEPA already uses structured masking, and Memento trains context compression. CSA's specific combination remains a **hypothesis**. Stronger comparisons must include these objective families, not just ordinary next-token prediction or an undertrained Transformer.

## Run locally (no third-party dependencies)

```bash
python -m unittest discover -s . -p 'test_csa_fixture.py' -v
python csa_fixture.py --output ./local-fixtures --seed 71407 --pairs 120
```

The exported JSONLs contain synthetic training and diagnostic labels and are not sealed scientific tests. Do not publish private future test rows or use this generator's public DEV as the confirmatory panel.
