# Native changing-state replay through the ecosystem

ECOSYSTEM-MEM-002 (#512) adapts the recovered CHANGING-STATE-001 public development
panel to the [memory campaign](memory-campaign.md). It runs the original learned
CSM and simpler SlotStore checkpoints with their native model sources. No model
is fitted by this adapter. This is an integration reproduction, not a fresh
architecture comparison or new held-out generalization evidence.

## Frozen protocol

- Two process-supervised models, seeds 101/202/303, six commands executed once.
- Original checkpoints and source bytes must match the recovered manifest and
  historical training receipts. The original CSM archive and recovered manifest
  have fixed SHA256 pins in the adapter. These establish byte identity, not
  independent chronology.
- The 640 previously exposed development worlds form eight correlated base-pattern
  groups. Forge keeps all value shifts, update depths and regimes from each group
  together. Its validation split is selected; TEST is not scored. This reassignment
  does not make the old development examples unseen.
- Four identities, eight values, SET only, 1/4/16/64/256 extra updates. DELETE,
  COPY, LINK, additional identities/values and supplied target fields are rejected.
- All 2,560 encoded historical queries must match the old input encoder before
  execution. The inference adapter supplies token IDs only, without answer labels,
  supervised physical addresses or edit targets.
- Each complete map uses four separate fresh-state queries. This is not persistent
  multi-query state reuse. One CPU thread, FP32, no concurrent campaign workloads,
  180-second timeout per seed/arm; failed attempts are retained without retries.
- One untimed warmup per event length, then one measured full-map request per world.
  Timing includes encoding, tensor creation, state initialization, token steps,
  argmax, map assembly and JSON serialization. Imports, checkpoint loading and
  disk writes are excluded; loading time is recorded separately.
- Timing is descriptive on the local CPU, with no confidence interval, power
  measurement or inference-cost qualification. The generic campaign correctly
  retains `inference_cost=NOT_MEASURED`.

Both historical arms had 256 optimizer updates and 8,192 answer exposures per
seed with matching schedule hashes. The adapter checks those retained records;
it does not independently re-establish the historical training chronology or
claim that equal parameter counts imply equal compute. Historical development
scores cannot select new checkpoints, hyperparameters or evaluation examples.

## Reproduce with the authorized source package

The operator supplies an extracted `Woyengi_Changing_State_001_20261113.zip`.
Do not replace missing checkpoint bytes with newly trained weights. Install all
four ecosystem packages, Python 3.12.14, CPU Torch 2.5.1+cpu and NumPy 2.3.5 in
an isolated environment. Torch is a manual replay dependency, not an ordinary CI
requirement. Source paths below must be new directories.

```bash
python integrations/research_lab/examples/changing_state_replay.py prepare RECOVERED SOURCE
python -m research_lab.memory_campaign prepare SOURCE/campaign.json CAMPAIGN
# Keep the returned protocol_sha256 outside CAMPAIGN and review the frozen inputs.
python -m research_lab.memory_campaign run CAMPAIGN --protocol-sha256 HASH
python -m research_lab.memory_campaign verify CAMPAIGN --protocol-sha256 HASH
```

The full evidence bundle contains the frozen sources/checkpoints, Forge manifest,
protocol pin, all six TrainLab receipts and predictions, independent Veritas
rescores, shared EvidenceRecord and Research Lab index. Keep source packages and
raw evidence within their authorized storage boundary. Public code and aggregate
results do not grant permission to publish a recovered private archive.

## Executed reproduction: 13 November 2026

All six native runs succeeded, once each, with no fitting or discarded attempts.
The separate `verify` command recomputed the saved report and shared envelope.
Protocol SHA256:
`11cf753109f6cb4d7ff15a3cc4224c0acb576a1a28324152ef2235b0a8db0e15`.
Forge manifest SHA256:
`a16f44bba3cfd6e77beb7c4e5ea47c451dd25e5ee8f98a701da2b32e0adf652e`.
All six prediction files have SHA256:
`9e6ec61b151b423aa816bac253f2736cbdb5a0aad2dedf79af6a8c4973eb9f34`.

Each seed/arm scored the same 80 correlated validation worlds from **one base
pattern**, giving 320 fresh-query answers. Counts below apply separately to each
of the six runs; the three seeds are model replications, not new data groups.

| Recomputed metric | CSM, each seed | SlotStore, each seed |
| --- | ---: | ---: |
| Current-answer accuracy | 320/320 | 320/320 |
| Complete-state accuracy | 80/80 | 80/80 |
| Stale-answer rate | 0/176 | 0/176 |
| Untouched-fact accuracy | 240/240 | 240/240 |
| Deletion / absent-answer accuracy | No examples; null | No examples; null |

Descriptive median complete-map latency, in milliseconds (four independent fresh
queries per map; the timing exclusions above apply):

| Seed | CSM, 18,294 parameters | SlotStore, 18,254 parameters |
| --- | ---: | ---: |
| 101 | 159.26 | 57.24 |
| 202 | 147.84 | 62.33 |
| 303 | 140.04 | 60.14 |

All six commands together consumed 201.83 measured process-wall seconds,
including startup, loading, warmup and output work. This is not measured research
productivity or an energy/cost comparison. The simpler control was faster in this
local replay; CSM has no demonstrated advantage on this saturated panel.
Model state tensors and checkpoint file hashes remained unchanged. The adapter's
10 cheap falsifiers and 45 existing ecosystem/evidence tests passed locally;
the quality ratchet introduced zero diagnostics. Neural replay stays manual.

## Interpretation

`COMPLETE` establishes successful execution and rescorable saved predictions.
Zero deletion or absent-key examples produce null metrics, never perfect scores.
The shared scorer defines stale as any earlier noncurrent value, and untouched
as an existing key not targeted by the final event. The old report instead used
the immediate predecessor value and keys never overwritten after initialization.
Saved predictions can match exactly while these metric denominators differ; do
not compare the old and new stale/untouched summaries as identical measurements.
Passing this replay does not establish learned deletion, natural-language memory,
unseen entity generalization, continuous autonomous research, or frontier status.
The next scientific protocol must introduce genuinely new admitted challenges
and strong equally informed controls, rather than relabeling this panel as TEST.
