# Changing-information campaigns and the frontier evidence path

Status: additive implementation candidate for ECOSYSTEM-MEM-001 (#510).
This is a bridge for existing model runners, not a replacement trainer or a
scientifically qualified benchmark. Its acceptance tests use scripted controls
and perform zero model fits.

## What changes

Previously, the composed example was fixed to two CompanyWorld scripted policies.
The memory campaign accepts operator-selected TrainLab recipes for an explicit
arm-by-seed grid. Existing CSM/LRC model code stays in its source repository.
A trusted local adapter exports complete-map predictions in the format below.

1. Forge verifies a pinned release and selects public TRAIN or validation prefixes.
2. Preparation copies every declared recipe input, recipe, design and dataset file
   into a new campaign directory. Checkpoint files belong in recipe inputs too.
   Preparation emits a protocol SHA256 that the operator retains separately.
3. TrainLab runs each declared recipe once and retains terminal failures as well as
   successful results. Repeating the campaign command skips existing attempt
   directories; it does not silently rerun failed seeds.
4. Veritas reconstructs correct states from each supplied prefix and scores saved
   predictions. Recipe-reported accuracy never enters these scores.
5. Research Lab indexes the dataset, valid execution receipts, immutable report
   revisions and the existing shared EvidenceRecord with outcome OBSERVED.
6. Verification recomputes the report and shared envelope without executing recipes.

Missing, invalid, unfinished and failed slots remain in the report. COMPLETE means
all declared commands succeeded and their submitted predictions were rescorable.
It never means that the models performed well, had matched supervision, passed
scientific review or achieved frontier performance.

## Data and prediction adapter

Use Forge's existing operations-jsonl release workflow. Each observation contains
one memory prefix, with the exact shape:

```json
{
  "memory": {
    "keys": ["customer", "location", "never_seen"],
    "events": [
      {"op": "set", "key": "customer", "value": "old"},
      {"op": "set", "key": "location", "value": "Lagos"},
      {"op": "set", "key": "customer", "value": "new"},
      {"op": "delete", "key": "customer"}
    ]
  }
}
```

Set the Forge outcome to unknown/unverified. This v1 adapter does not accept target
labels or protected TEST selection. Values and identities are bounded nonempty
strings; JSON null means absence, not a value that can be stored. Each prediction
must include every declared key, including absent ones:

```json
{
  "predictions": {
    "the-forge-record-id": {
      "customer": null,
      "location": "Lagos",
      "never_seen": null
    }
  }
}
```

The adapter writes this object to
`$TRAINLAB_OUTPUT_DIR/memory_predictions.json`, plus TrainLab's normal
`metrics.json`. All expected Forge record IDs must occur exactly once.

For learning experiments, use a separate pinned TRAIN release or split in the
recipe and record its files as inputs. The campaign-selected split is the scoring
split. Keep all prefixes from one underlying stream under the same Forge subject,
so they cannot split between TRAIN and validation. Freeze seeds, vocabulary,
entity-family split rules, tuning budgets, supervised controller labels, training
stages and checkpoint selection in the design before any model fitting.

## Metrics and denominators

| Metric | Numerator | Denominator |
| --- | --- | --- |
| Current-answer accuracy | Correct key answers | All keys across all supplied prefixes |
| Stale-answer rate | Predictions equal to an earlier noncurrent value | Keys with at least one earlier noncurrent value |
| Deletion accuracy | Correct absent answers after deletion | Keys whose latest operation is delete |
| Untouched-fact accuracy | Correct existing facts not targeted by the final event | Existing keys other than the final event's key |
| Complete-state accuracy | Exactly correct complete maps | Supplied prefixes |
| Absent-answer accuracy | Correct absent answers | All currently absent keys |

Every metric retains numerator and denominator. An empty stratum produces null,
not a fabricated zero or perfect score. Untouched-fact accuracy is not a causal
collateral-damage estimate: that needs paired pre/post predictions conditional on
prior correctness. Reinserted keys are no longer in the deletion stratum.

The scorer uses only the supplied prefix. It does not prove that a trusted adapter
avoided looking at later rows, labels, prior evaluation outputs or other files.
Complete-state accuracy covers the explicitly declared key universe, not unknown
facts outside that universe. These distinctions must survive interpretation.

## Prepare, execute and verify

Install all four existing ecosystem packages from the same reviewed checkout:

```bash
python -m pip install . ./integrations/forge ./integrations/trainlab ./integrations/research_lab
```

Place recipes together with a design document and the Forge release in a source
directory. This minimal specification uses two arms and one seed for illustration;
a scientific comparison needs the admitted replicated protocol.

```json
{
  "schema": "veritas.memory-campaign.v1",
  "dataset": "dataset",
  "cutoff": "2026-01-01T00:00:00Z",
  "split": "validation",
  "design": "design.md",
  "slots": [
    {"id": "candidate-7", "arm": "candidate", "seed": 7, "recipe": "candidate-7.json"},
    {"id": "baseline-7", "arm": "baseline", "seed": 7, "recipe": "baseline-7.json"}
  ]
}
```

Use standard TrainLab v1 or v2 recipes. Each must declare:

- the slot seed, source_kind CONSTRUCTED and the Forge manifest SHA256 as split_identity;
- the design document, adapter source, model checkpoints and all other used local
  files in inputs, including dataset/manifest.json and all three dataset split files;
- memory_predictions.json in artifacts, plus checkpoints/logs required by the
  scientific design;
- the real training/inference command, timeout, workload and declared budget.

```bash
python -m research_lab.memory_campaign prepare source/campaign.json output/campaign
# Retain the returned protocol_sha256 outside the output directory.
python -m research_lab.memory_campaign assess output/campaign --protocol-sha256 HASH
python -m research_lab.memory_campaign run output/campaign --protocol-sha256 HASH
python -m research_lab.memory_campaign verify output/campaign --protocol-sha256 HASH
```

Replace HASH with the exact preparation output. assess is read-only and useful
before execution or after interruption. run uses the archived inputs as its
working directory. Installed ecosystem Python source trees and selected package
versions must still match preparation. No package download, external API call,
GPU purchase or remote job dispatch is introduced by this orchestration code.

There is intentionally no automatic retry selection. A new admitted campaign
can resume a model from a retained checkpoint, but must name that checkpoint in
its declared inputs and explain the changed attempt in its design. The existing
TrainLab/full-cycle checkpoint protocols still own optimizer and sampler recovery.

## Cost and trust boundaries

process_wall_seconds is the full TrainLab command duration, including startup,
training and evaluation if the command includes them. inference_cost is explicitly
NOT_MEASURED. Neither a faster scripted control nor declared equal budgets proves
a model cost-quality advantage. Parameter counts, FLOPs, memory, label access,
tuning effort and stage-specific costs remain unverified by this adapter.

Commands are trusted local code, not sandboxed workers. They share the account
and can access neighboring files. Declaring inputs does not prove that a command
used them or declared every dependency. Dataset rights are operator declarations;
public CONSTRUCTED is an intended-use boundary, not a privacy detector. No sealed
or customer data belongs in these acceptance fixtures or public CI artifacts.

Hashes detect changes relative to the retained protocol and receipts, not a
malicious rewrite of the entire local evidence chain. Remote attestation and an
independent replication remain separate. Runtime identity is not a full OS,
CUDA, hardware or binary dependency attestation. Host death may leave UNFINISHED
attempts; this adapter preserves them and does not claim optimizer recovery.

Bounds: 2-64 slots, 1-10000 scored prefixes, at most 1024 keys and 10000 events per
prefix, plus existing Forge/TrainLab file-size limits. Source/checkpoint archival
can require substantial disk space. This is a local single-operator command;
concurrent controllers must not operate on the same campaign directory.

## What would justify frontier-class research infrastructure

The target is reliable, independently reproducible scientific decisions at
competitive total cost. A larger component inventory is not the success metric.

| Milestone, in order | Concrete deliverable | Acceptance evidence |
| --- | --- | --- |
| 1. Common experiment path | This frozen campaign adapter used by actual CSM/LRC runners | Full arm/seed coverage, saved predictions, source/checkpoint restoration and independently reproduced scores |
| 2. Credible learned comparison | Admitted changing-information panel and capable baselines | Equal-information and task-only-supervision tracks; capable Transformer and memory-network controls; at least three prespecified seeds; untouched-fact, stale, deletion, abstention and composition slices |
| 3. Cost-quality measurement | Synchronized complete-call timing and resource meter | Loading, prefill, updates, queries, retrieval, correction, serialization and reset measured separately and end-to-end; CPU/GPU identities; warmups; p50/p95; memory; measured amortization across workload mixes |
| 4. Reliable operation | Existing supervisor deployed to an authorized persistent host | Process identity, heartbeat age, durable queue/checkpoints, forced restart, exact continuation where promised, no duplicate task ownership, budget stop and independent clean-host restore |
| 5. Measured research value | Prospective coordination A/B/C campaign and external reproduction | Independently accepted experiments per total elapsed hour and per cost, including review/failures; reproduction by another environment/team |

For milestone 2, choose the strongest *qualified* controls for the actual task,
not only convenient weak models. A symbolic store is a task-validity reference;
it is not a learned baseline. An oracle-routed candidate is a separate privileged
control. Freeze checkpoint selection and stopping rules before examining the
confirmatory panel. Include state reset/shuffle, ignore-last-update, wrong-entity,
absent-key and no-history controls. Passing source tests never admits a model fit
by itself.

For milestone 3, preserve the user's stated 12:1 inference-to-training preference
as a declared sensitivity analysis, alongside raw measurements. Do not disguise
it as universal economics. The actual workload mix and serving lifetime determine
amortized cost. Claim an improvement only at comparable reliability with uncertainty
across seeds and evaluation streams; retain failures and floor/ceiling saturation.

For milestone 4, review and integrate the existing full-cycle recovery branches
rather than reimplementing their checkpoint logic. A scheduled ChatGPT task or
registered department does not establish a live worker. Start with one measured
campaign; expand worker count only when accepted throughput benefits.

The promotion decision remains NOT_QUALIFIED until the existing scientific
contracts are satisfied. Frontier qualification additionally needs results against
current strong alternatives on externally meaningful work. No result in this
implementation or its scripted tests establishes that outcome.
