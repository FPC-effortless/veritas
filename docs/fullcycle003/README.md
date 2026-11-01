# FULLCYCLE-003: public data and deep 10M TAC

This adds automatic public dataset acquisition to the Forge/TrainLab lifecycle.
The model uses the actual LANGDEPTH106 four-layer allocation's width and bank
geometry, with 40 distinct layers and a fitted 3,072-token byte BPE. Its total
and trainable parameter counts are both **10,040,600**. Weights start randomly;
the trained four-layer checkpoint is not expanded or reused.

The native model retains the blueprint's bounded local attention, associative
banks, rotary fields, gated FFN and tied embedding. It is not the fixed-size
TAC098 adapter and is not attention-free. The original four-layer byte model
has 998,024 parameters. `BLUEPRINT.json` records the source configuration and
original implementation hashes. The adapter only changes vocabulary sizing,
stack depth and optional activation checkpointing.

## Install and acquire

Install PyTorch for the actual host first, then install the repository and optional
training dependencies:

```bash
python -m pip install -e . -e integrations/forge -e 'integrations/trainlab[training]'
python -m trainlab data fetch \
  integrations/trainlab/examples/fullcycle003/data-plan.json \
  --cache .trainlab/fullcycle003-data
python -m trainlab data prepare \
  integrations/trainlab/examples/fullcycle003/data-plan.json \
  --cache .trainlab/fullcycle003-data
python -m trainlab data status .trainlab/fullcycle003-data
```

`data-plan.json` pins repository commits, individual parquet paths, byte sizes,
SHA256s, upstream splits and license metadata. Public anonymous downloads work;
`HF_TOKEN` is optional when a source requires authentication. Tokens are never
written into a manifest. The SDK retains interrupted-download state. Acquisition
refuses an altered cached shard or a changed plan in an existing cache.

Ten shards total **3,359,380,492 bytes**. Raw corpora and prepared artifacts live
in ignored `.trainlab/`, outside Git. Shards are read in batches of 64 rows.
Deduplication and source-group isolation use disk-backed SQLite; the public prompt
fingerprint automaton and the tokenizer fitting sample are bounded by the pinned
input plan. This is not a constant-memory guarantee for arbitrary-sized prompt
catalogs or tokenizer vocabularies.

The downloadable prepared-data archive also contains `resolved-full-cuda.json`,
the fitted tokenizer and the complete selected Forge release. It can run without
the raw Hugging Face cache or an Internet connection after dependencies and the
source installation are available:

```bash
unzip FULLCYCLE-003-prepared-data.zip -d /data/fullcycle003
python integrations/trainlab/examples/fullcycle/gpu_run.py \
  /data/fullcycle003/resolved-full-cuda.json \
  --output /runs/fullcycle003-full --gpus 1
```

| Stage | Public source | Preparation |
| --- | --- | --- |
| Pretraining | FineWeb-Edu, first pinned 10BT sample shard | At least 200.1M TRAIN BPE tokens; independent text splits by normalized URL |
| Mid/SFT | Smol-SmolTalk `smol-magpie-ultra-short`; GSM8K solutions | 20,000 short TRAIN chats plus eligible TRAIN math solutions; complete role turns |
| DPO | UltraFeedback binarized | 4,000 TRAIN pairs with strictly greater chosen scores and common user prefixes |
| Completion GRPO | GSM8K TRAIN problems | Policy samples full-vocabulary multi-token answers; exact numeric final-line verifier |

Source licenses are ODC-by (FineWeb), Apache-2.0 (the selected Smol component),
and MIT (GSM8K/UltraFeedback), as declared by their pinned public source cards.
These are provenance/rights-review records, not independent source-authenticity
or scientific qualification. Smol and UltraFeedback contain generated/model-judged
data and are labeled accordingly.

All official TEST prompt groups are reserved before quotas or context filtering.
TRAIN-derived validation and official TEST prompt fingerprints are screened out
of training text and post-training candidates **before BPE fitting**. The screen
normalizes words and uses full short prompts or three 12-word windows. It cannot
certify absence of paraphrases or semantic contamination. Pretraining uses exact
payload deduplication on an upstream deduplicated source, not a new global fuzzy
deduplication of the web.

BPE fitting consumes only screened TRAIN text, at most 16 MiB. The tokenizer
receipt binds the exact screen, preparation implementation and tokenizer hash.
Post-training records exceeding the 1,024-token context are rejected rather than
truncated. Official TEST cannot be relabeled as TRAIN or validation. Evaluation
text quotas, chat quotas and preference quotas must all be met before freezing.

## Run the model

The full recipe requests CUDA and fails when CUDA is unavailable:

```bash
python integrations/trainlab/examples/fullcycle/gpu_run.py \
  integrations/trainlab/examples/fullcycle003/tac-10m-full.json \
  --output .trainlab/fullcycle003-full --gpus 1
```

It prepares data before distributed process initialization, then performs base
pretraining, conversational mid-training, assistant-only SFT, frozen-reference
DPO, bounded on-policy completion GRPO, public evaluation and registry export.
The native TAC adapter uses FP32. GPU mixed precision and GPU/distributed
correspondence are not established by the CPU checks.

On **one GPU**, pretraining is 12,208 updates × batch 8 × accumulation 4 × length
512 = **200,015,872 sampled training token positions**. Random crops are sampled
with replacement; this is not a guaranteed single pass through all documents.
Post-training uses up to 1,024 tokens per sequence, general-text replay and cosine
learning-rate schedules. Additional GPUs increase the global processed-token
budget proportionally with this fixed-step recipe; the report records actual
world size and work. Do not compare runs as matched budgets without adjusting
steps or accumulation.

The separate CPU pilot exercises the **same 10,040,600-parameter architecture**:

```bash
python -m trainlab pipeline run \
  integrations/trainlab/examples/fullcycle003/tac-10m-cpu-pilot.json \
  --output .trainlab/fullcycle003-pilot \
  --stop-stage pretrain --stop-after 32
python integrations/trainlab/examples/fullcycle003/check_recovery.py \
  .trainlab/fullcycle003-pilot --output .trainlab/fullcycle003-recovery
python -m trainlab pipeline resume .trainlab/fullcycle003-pilot
python -m trainlab pipeline verify .trainlab/fullcycle003-pilot
python -m trainlab model chat .trainlab/fullcycle003-pilot/model
python -m trainlab model serve .trainlab/fullcycle003-pilot/model --port 8787
```

The pilot is 256 pretraining updates (32,768 token positions), 4 mid-training,
8 SFT, 4 DPO and 2 completion-GRPO updates. It proves execution, not useful
assistant behavior. Its small public panels are explicitly bounded and frozen
by group hash. Public evaluator execution occurs in a separate process loading
the checkpoint bytes; training metrics do not confer Veritas qualification.

The recovery driver runs a separate uninterrupted control through update 33,
resumes the primary checkpoint from 32 to 33 and compares all weights, optimizer
state, losses and RNG byte-for-byte. Those 33 control updates are reported
separately from primary training work.

Immutable checkpoint blobs include optimizer, sampler, RNG, reference policy and
learning-rate progress. An atomic selecting index governs recovery; stage receipts
pin all dependencies. Completed stages are skipped only after verification. To
resume a CUDA run, use the same process count, device type, source installation
and environment; for multiple GPUs invoke `torch.distributed.run` with that count
and `-m trainlab pipeline resume RUN_DIRECTORY`.

Completion GRPO records actual sampled trajectories and per-token behavior log
probabilities, and recomputes a clipped token objective and reference KL. Gold
answers enter only the reward verifier. CPU sampling/serial rollouts prioritize
replay correspondence over GPU throughput. A severely undertrained pilot can
have zero rewards; executing optimizer steps does not imply an RL capability gain.

## Verification

```bash
python -m unittest discover -s integrations/trainlab/tests_data -v
python -m unittest discover -s integrations/trainlab/tests_fullcycle -v
python -m unittest discover -s integrations/forge/tests -v
python -m unittest discover -s integrations/trainlab/tests -v
python tools/quality_baseline.py check
```

The original-source conformance test can be run with `TAC104_REFERENCE_DIR` set
to the extracted original directory containing `tac_model.py` and `kernels.py`.
It compares loaded four-layer weights and logits bit-for-bit; absent the external
original, that one test is explicitly skipped. Other checks cover more than 256
token positions, cached/full correspondence, causality, state-owner isolation,
checkpointing gradients, completion reward-gradient direction, and exact native
completion-RL interruption/resume including rollout records.

`OUTCOME.md` defines acceptance/falsifiers. Executed training and resource evidence
must be read separately from the full recipe; no GPU run or 200M-token completion
is inferred from this documentation.
