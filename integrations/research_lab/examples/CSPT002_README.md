# CSPT002 — Structural-Prediction Training Diagnostic

Woyengi Intelligence Labs · LEARNING_OBJECTIVES research lane · 2026-11-06.

## Claim boundary

This is a reproducible *synthetic implementation diagnostic*, not a trained language model, not learned long-term memory, not a causal identification result, not a matched-compute architecture comparison, and not scientific qualification. Nothing here authorizes promotion, paid GPU allocation, external deployment or opening protected TEST datasets.

It trains the same 65,100-online-trainable-parameter Transformer backbone and answer-token head under four variants: `answer_only` (supervised query-answer control), `good_views` (+ alignment of two paraphrases of one world), `completion` (+ before-state question supervision), and `causal_latent` (+ EMA-target action-conditioned post-state latent prediction). All methods use the same underlying synthetic states with the same generated order per seed, 120 optimizer steps, 32 samples/update, 3 seeds. Auxiliary losses differ in additional information and compute. Their parameter counts are matched; their compute and training signals are **not**, so the contrasts do not isolate JEPA or establish superiority to an LLM.

## Why CSPT001 was superseded

CSPT001 used a hash of the complete question record. Alternate questions about the same underlying world could therefore cross train/DEV/test boundaries (347/384 sampled dev states had a query variant assigned to another split in a diagnostic check). Its primary intervention-pair metric could be passed by always returning the last transfer recipient, despite never predicting the unchanged object's owner. Preserve CSPT001 files/results as invalid historical evidence, rather than rewriting them after seeing outcomes.

CSPT002 preregistered an improved split by `state_key()` (query/view omitted), checked same-state query isolation, required changed-receiver counterfactuals to remain in the same split, and added `state_triplet_exact`. This metric requires correct transfer and unchanged-item owners, plus a correct changed-receiver prediction on the same held-out group. A recipient-only shortcut receives 0% on this joint gate. The trial's resulting floor performance is a **negative diagnostic**, not a proof that JEPA cannot work.

## Reproduction

Requires Python 3.11+ and PyTorch (CPU is sufficient); does not change Veritas dependencies.

```bash
python -m unittest -v test_cspt002.py
python cspt002.py --arms answer_only good_views completion causal_latent \
  --seeds 11 23 37 --steps 120 --batch-size 32 --eval-size 384 \
  --out runs002 --save-checkpoints
python audit_cspt002.py --paths runs002/*.pt --output replay_all.json
```

The saved checkpoint contains inference weights, training receipt and an RNG snapshot, but **not optimizer state**. It supports exact prediction replay, not optimizer resumption. The auditor verifies held-out DEV and exploratory TEST metrics from checkpoint bytes in a separate Python process; a genuine external independent review has NOT occurred.

## Scientific assessment

- Synthetic owner-transfer grammar only; one action per world, 2 objects, 12 entities, 8 object types.
- Main test contrasts `state_triplet_exact`, not just transferred-item accuracy.
- A heldout split consists of unseen underlying state tuples, not wholly unseen words, sentences, real documents, or action distributions.
- This tiny model has not been shown to reason, understand real-world interventions, maintain persistent memory or generate natural language.
- One-step source-derived oracle scores 100% by construction, proving a valid answer exists, not learnability.
- Next critical research gate: learn exact untouched-value binding on real language and independent longer-horizon event chains, then compare objectives against properly pretrained Transformer, GRU and SSM baselines with matched compute and independent verification.

Read `PREREGISTRATION_002.json`, `FROZEN_002.sha256`, and `RESULTS_002.md` for study identities and measured limitations.
