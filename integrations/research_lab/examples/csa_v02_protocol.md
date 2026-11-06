# WIL-TRAIN-002 — Two-hop counterfactual state training protocol (exploratory)

**Date:** 2026-11-06. **Status:** SOURCE/DIAGNOSTIC VERIFIED LOCALLY; NEURAL OBJECTIVE UNQUALIFIED. This is a follow-on to [WIL-TRAIN-001](https://github.com/FPC-effortless/veritas/issues/496), stacked on draft [PR #497](https://github.com/FPC-effortless/veritas/pull/497). There is **no protected confirmatory TEST**, no paid/GPU job, no performance promotion, and no claim of learning-theory novelty. No independent author/session review occurred in this execution environment.

## Hypothesis and mathematical scope

A useful query-independent state representation must satisfy both (i) preservation of an answer under edits that are irrelevant **to that query**, and (ii) sensitivity to the same edit for another query when the edited fact matters. In the 2-hop task, an event assigns project P to person W, and another event locates W at room L. The answer is L if both links exist, else UNKNOWN. Updates override prior assignments/locations, and unassign removes the project link. A query can require resolving P → W → L; the model receives only raw history text and question, not typed edges or oracle codes.

For paired histories H⁺/H⁻ differing by exactly one event, and queries q₁/q₂, construct cases where y(H⁺,q₁)=y(H⁻,q₁) but y(H⁺,q₂)≠y(H⁻,q₂). This disproves **whole-state invariance** as a general regularizer; the desired invariance is prediction-conditional on q.

A proposed auxiliary paired-ranking objective uses the same external labels as CE and is anchored by CE. On relevant flips, increase the log-probability of each arm's correct answer relative to the other arm; on query-irrelevant edits, minimize Jensen-Shannon prediction divergence, while a cross-relevance question flips. This objective is *not automatically new information* relative to answer supervision, and loss reweighting is an obligatory competitor.

**Further correction:** For an exact deterministic recurrent E whose state update U is its unrolled recurrence, `E(H ⊕ e) = U(E(H),e)` holds by construction (up to floating-point effects). Consequently, an auxiliary objective comparing these identical forward paths is a tautology and has zero useful error signal. A meaningful update-consistency loss must compare genuinely distinct computational paths, e.g. full recomputation vs separately parameterized approximate update, or different intervened histories under grounded questions. Neither warrants claims before measured benefits.

## Public synthetic benchmark

Four families: reassign, relocate, unrelated relocation, unassign. Histories of 8/32/128 events; 40 pairs for each of 4 splits × 3 lengths = 480 pairs, 960 primary labeled examples plus 240 changed-key cross-query examples. TRAIN/DEV-IID use the base grammar; DEV-OOD-SYNTAX uses a disjoint grammatical template, not unseen world semantics; DEV-OOD-COMP withholds target project+person combinations satisfying a deterministic modulo-4 partition while retaining previously seen individual tokens. The surface event number is normalized to `<num>` by the optional neural pilot tokenizer.

Generator source is deterministic and exports SHA256-manifested public diagnostic JSONL. **These examples and labels are public diagnostics, not protected evaluation.** No date/license ambiguity (synthetically generated). `model_view` returns only `history` and `query`; the typed teacher replay is inaccessible through this adapter. Evaluators must independently parse public text rather than call teacher replay to validate neural/model input integrity.

## Source-only controls

- 7 standard-library no-fit checks, including pair construction, answer replay, no privileged metadata, disjoint composition, hash-repeatability, independent textual parser, mutation refusal. Reran all 7 under optimized Python as well.
- Independent regex-based text parser achieves 100% of all 960 primary and 240 cross-query labels. This is **not neural generalization** and is the symbolic grammar-aware control ceiling on this constructed domain.
- Ignore-final-update gets 37.5% primary and 0% cross-query at all tested cells. The last-location-only shortcut varies across cells (~27.5–41.25%).
- Majority-class prediction `UNKNOWN` is correct on 12.5% of primary rows by construction (unassign pairs: half known/unknown, 1/4 of all pairs).

## Bounded CPU neural learning feasibility (NOT a qualified CSA comparison)

Hardware: local CPU; PyTorch 2.10.0+cpu. Synthetic raw history text tokenization with integer event numerals normalized. 27,705-parameter single-layer GRU; query follows full history, output is final recurrent hidden state + head. 9 answer classes. Three objective arms CE, CE_REWEIGHT and PAIR use exact same generated 1600 training pairs, seed10, mini-batch sampling, 350 AdamW steps, 24 pairs/step, LR 0.003. Public DEV panels of 200 pairs each. No GPU, no pretrained LM, no meaningful equal-FLOP claim; repeated rows on noncross cases are masked out of loss but computed to keep forward shapes constant. Training seconds and labels logged per run. No checkpoints were persisted for these exploratory fits; **not independently replay verified**.

- CE: train 0.1253, IID 0.1150, heldout-composition 0.1075, OOD-syntax 0.0925; 24.547 training seconds.
- CE_REWEIGHT: train 0.1291, IID 0.1200, heldout-composition 0.1325, OOD-syntax 0.1000; 26.159 training seconds.
- PAIR: train 0.1253, IID 0.1150, heldout-composition 0.1075, OOD-syntax 0.0925; 25.636 training seconds. PAIR ranking penalty ~1.948 both initial and last measured point.
- Separate 8-pair overfit smoke, CE/seed10/500 updates: TRAIN 0.6875, IID 0.1375, OOD composition 0.1000; no generalization.
- At random initialization, 16 supervised TRAIN examples show mean embedding-gradient norm over history positions / mean over query positions ≈ 0.0008323; final 15 history positions / query positions ≈ 0.004792. This is a **random-initialization gradient diagnostic**, not an attribution to the trained model. Likely weak temporal credit propagation is a candidate bottleneck, not a proven cause.
- Separate 52,665-parameter two-layer Transformer/full-context smoke completed 10 CPU updates, but a 350-step batch24 attempt exceeded the command's 120-second execution limit before a completed artifact. It is **INCOMPLETE/UNMEASURED**, not a Transformer model failure. Its full-context access is NOT equivalent to bounded memory/erasure.

**STOP DECISION:** do not interpret the CSA loss as successful or falsified in this pilot. The GRU control is not capability-qualified and is at or below 12.5% majority accuracy, with zero complete opposing-history pair success. More arm/seed repetitions cannot identify a training-objective effect until a capable, independently source-reviewed baseline is established.

## Qualifying next experiment (not run)

1. Separate implementation correctness, capability feasibility, and causal training-objective utility. Require training-set and DEV probe overfitting in the capable control, and history-vs-no-history/shuffle discriminability, before using it as scientific comparator.
2. Use a qualified architecture with real access to distant observations; compare an equal-parameter Transformer with explicit bounded state extraction, a GRU/modern recurrent model proven to learn the task, and an attention full-context ceiling. Never infer state compression from attention over the whole history.
3. Keep CE, hard-example/reweighted CE, paired ranking, query-relative invariance, and erasure/temporal credit local replay as distinct registered treatment arms; each uses the same task labels and token exposures, report extra training FLOPs (not presumed equal) and state bandwidth.
4. For the proposed *temporal credit-localization* arm, provide intermediate prefix-query labels **equally to CE and CSA controls**, then vary only the auxiliary stability/revision objective. Without label-budget parity, any gain could simply come from added supervision. This stage has not been implemented or fitted.
5. Freeze disjoint test generation before examining final metrics, audit lexical/grammar vs compositional OOD separately, retain per-seed checkpoints, and independent scientific replay. Five seeds and matched resources required for promotion.
6. Prior art essential: [Next-Latent Prediction](https://www.microsoft.com/en-us/research/publication/next-latent-prediction-transformers-learn-compact-world-models/) (predictive belief-state training), [State Commitment Learning / CERL](https://arxiv.org/abs/2606.05201) (counterfactual erasure), and [StateComp](https://arxiv.org/abs/2609.27298) (conditional compression). This work establishes **no priority/novelty claim**.

## Replication

```
python -m unittest discover -s integrations/research_lab/tests -p test_csa_v02.py -v
python integrations/research_lab/examples/csa_v02.py --output /tmp/wil-csa-v02 --pairs 40 --seed 49621
python integrations/research_lab/examples/csa_v02_diagnostics.py --output /tmp/wil-csa-v02-diagnostics.json
# Optional with PyTorch installed, outside ordinary Research Lab OS CI:
python integrations/research_lab/examples/test_csa_train_pilot.py
python integrations/research_lab/examples/csa_training_pilot.py --output /tmp/csa-ce.json --architecture gru --variant CE --updates 350 --train-pairs 1600 --dev-pairs 200 --batch 24 --seed 10
```

`--architecture transformer` supports an exploratory *full-context* Transformer, not a valid memory-budget-matched comparator. Its reported attempt is **timed out**, not complete.
