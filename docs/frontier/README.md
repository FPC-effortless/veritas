# Frontier Qualification

Frontier Qualification is an additive Veritas evidence layer. It answers a different question from scientific benchmark qualification:

> Is a scientifically qualified environment useful for differentiating and improving current strong/frontier agents under an explicit policy?

It does **not** replace, weaken, reinterpret, or mutate scientific qualification. A benchmark may be scientifically qualified while its Frontier Qualification remains `NOT_YET_FRONTIER_QUALIFIED` because utility evidence is absent or inconclusive.

## Three-state evidence rule

Every utility gate emits `PASS`, `FAIL`, or `UNKNOWN`. `UNKNOWN` is mandatory when the measurement required by the active policy has not been supplied. The final report only sets `frontier_qualified=true` when scientific qualification is explicitly true and every Frontier utility gate passes.

The active `FrontierQualificationPolicy` is embedded in every report and has a content-derived ID. The policy declares which tiers count as strong/frontier; the implementation does not silently assign that status to a model from its name or parameter count.

## Utility gates

1. **Non-saturation** — strong/frontier observations must occupy useful intermediate difficulty rather than all being at the configured floor or saturation ceiling.
2. **Capability separation** — weaker and stronger tiers must separate by the configured effect threshold. A PASS requires uncertainty information; point estimates alone remain `UNKNOWN`.
3. **Harness sensitivity** — paired or otherwise comparable runs of the same model snapshot under different harnesses/configurations must expose a material capability difference. Without comparable runs the result is `UNKNOWN`.
4. **Failure-mode breadth** — categorized failures must span multiple meaningful classes without parser, infrastructure, or another single class dominating beyond policy.
5. **Task diversity** — structural/categorical diversity must satisfy policy independently of raw task/seed count.
6. **Held-out/compositional generalization** — random held-out, source-disjoint, grammar-disjoint, component-disjoint, and compositional/OOD evidence are represented separately. Policy chooses which are required.
7. **Training value** — evidence is scoped to within-family, cross-family, and external-benchmark transfer. Existing Training Value v3 aggregates are interpreted only as replicated within-family held-out transfer.
8. **Control/regression guardrail** — unrelated/control capability preservation must be measured when policy requires it. No control run means `UNKNOWN`.

## Diversity claims and metrics

`frontier_task_diversity.py` works offline from normalized JSON metadata. No network or heavyweight semantic model is required.

For each available categorical dimension it reports Shannon entropy, normalized entropy, effective number of categories (`exp(entropy)`), and largest-category share. Dimensions include source family, workflow topology, tool/action sequence, causal/failure mode, verifier condition, artifact/schema, component signature, and grammar family.

The report also includes:

- `raw_task_count`: number of supplied rows; this is **not** a diversity claim;
- `effective_diversity`: conservative harmonic mean of available categorical effective numbers, so one concentrated dimension cannot be hidden by another high-cardinality dimension;
- `cluster_count` and `largest_cluster_share`: output of the deterministic lexical/structural semantic-cluster proxy;
- `duplicate_share`: exact normalized-content duplicates;
- `near_duplicate_share` and component sizes: seed/identifier-normalized near-duplicate concentration;
- `source_concentration`: largest source-family share;
- split overlap and component/grammar/compositional disjointness diagnostics.

The built-in `LexicalStructuralSimHashBackend` is deterministic and dependency-free. It implements the same small interface a future embedding-backed clusterer can implement without changing the report contract.

## Buyer-safe contract

Frontier reports contain aggregate evidence, immutable identities, policy thresholds, model/harness identities, artifact hashes, and gate diagnostics. They do not require private task rows, private labels, hidden oracle contents, or per-case predictions. Detailed private artifacts remain evaluator-side.

## Standalone tools

```bash
python tools/frontier_task_diversity.py \
  --input tasks.json \
  --output diversity.json

python tools/frontier_calibration.py \
  --observations observations.json \
  --output calibration.json

python tools/frontier_qualify.py \
  --qualification scientific-qualification.json \
  --diversity diversity.json \
  --calibration calibration.json \
  --training-value training-value.json \
  --generalization generalization.json \
  --policy policy.json \
  --output frontier-qualification.json
```

All IDs and calculations are content-derived. Timestamps are intentionally absent from identity-bearing outputs, so the same inputs and policy reproduce the same report bytes.
