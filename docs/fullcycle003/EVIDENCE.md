# FULLCYCLE-003 executed evidence

Full 200M-token GPU training **has not run**: the executing host has CPU-only
PyTorch 2.15.0 and zero CUDA devices. The separate full recipe requests CUDA and
refuses unavailable hardware. Its one-GPU pretraining budget is 200,015,872 token
presentations, followed by post-training. GPU/distributed correspondence and
throughput remain unverified.

The **CPU lifecycle completed** with 274 committed optimizer updates and a
verified exported chat bundle. Its 32,768 pretraining token positions are only a
smoke budget. **Capability outcome failed**: free chat repeats words, final public
math/instruction scores are 0/2, and all four actual RL trajectories received
zero reward. No useful assistant or DPO/RL capability gain is established.

## Exact model and inputs

- New random initialization; 10,040,600 total/trainable parameters.
- Original four-layer allocation: width 120, 4 heads, key/value 16, write rank 2,
  FFN 224, local window 128, chunks 32, rotary fields/local RoPE, tied embedding.
- Depth increased to 40 distinct layers; fitted BPE vocabulary 3,072.
- Training implementation: `eefc1d4c500584bc1f0e8e08b0bd35a600c3a0ed`.
- Forge manifest: `7685a510195b2e2466878c9b634abe7f888e02096c271d41f14272001e5b4b9b`.
- BPE artifact: `87567e3e62a688ab666c2e8d25e76917df7709986a7a53cc5be36697d3552609`.

The BPE consumes at most 16 MiB of screened TRAIN text. Official TEST and
TRAIN-derived validation prompt fingerprints total 53,620 normalized prompts;
all official TEST prompt groups are reserved before any quota/context filtering.
This is a public fingerprint screen, not semantic contamination certification.

| Selected records | TRAIN | Validation | TEST |
| --- | ---: | ---: | ---: |
| Text documents | 135,786 | 86 | 108 |
| Conversations, including math solutions | 26,927 | 502 | 1,447 |
| Preference pairs | 4,000 | 64 | 64 |
| Math rollout tasks | 6,927 | 374 | 1,319 |

TRAIN text contains **200,100,507** fitted-BPE tokens, including document EOS.
Independent text budgets also passed: validation 131,470 and TEST 131,895 tokens.
Conversations include exactly 20,000 selected short Smol TRAIN chats plus 6,927
TRAIN GSM8K solutions. These public synthetic/model-judged components are identified
in source metadata; they are not relabeled as human-authored demonstrations.

Ten pinned parquet files total 3,359,380,492 bytes. Two/three-shard conversation
candidates failed the unchanged 20,000-chat quota; the final plan uses all four
pinned TRAIN shards. Over-context conversations and preference answers are rejected
whole, without target truncation. The release audit checked 168,980 global source
groups without a split crossing or official-TEST reassignment. The downloadable
archive reverified all 100 release files and its tokenizer/recipe pins.

## Executed correspondence checks

- All **175** targeted/regression checks passed: 17 acquisition/native/completion
  checks, 13 existing lifecycle checks, 68 Forge, 38 TrainLab, and 39 qualification
  regressions. Original-source four-layer weights/logits match bit-for-bit; this
  external-source test ran here and is explicitly skipped when that source is absent.
- Native full/cached causality and state ownership after 256 token positions;
  activation-checkpointed gradient correspondence; scripted actual completion
  rewards produce a policy gradient toward the correct answer.
- Exact native completion-RL replay at unit scale, including sampled trajectories.
- Actual 40-layer/10M CPU pretraining paused at update 32 and resumed to 33 matches
  an uninterrupted 33-update control: weights, optimizer, scaler, loss history,
  token counts, sampler and Torch RNG are bit-exact. Saved step numbers were also
  directly re-read and compared. The 33 control updates are separate work.
- Actual TRAIN BPE sequence length 512, batch 1, activation checkpointing enabled:
  full 10M forward/backward passed with all parameter gradients finite. Loss
  8.0748148; measured forward/backward wall time 36.126 seconds and process high
  water RSS 530,481,152 bytes. This is a CPU shape/gradient check, not GPU throughput.
- Forge, TrainLab and Veritas wheels build; installed-wheel native forward/backward
  works outside the checkout with the fully resolved architecture configuration.
- Targeted Ruff and the repository quality ratchet pass without new diagnostics.
  The manual lifecycle workflow now includes the new constructed unit controls;
  it was not dispatched and does not acquire the multi-GB training plan in CI.

## Measured primary lifecycle

| Stage | Updates | Forward positions | Active seconds | Validation NLL |
| --- | ---: | ---: | ---: | ---: |
| pretrain | 256 | 32,768 | 1156.76 | 6.866850 |
| midtrain | 4 | 7,125 | 64.93 | 6.866292 |
| sft | 8 | 13,990 | 133.33 | 6.861148 |
| dpo | 4 | 8,237 | 108.14 | 6.868757 |
| rl | 2 | 2,984 | 67.74 | 6.867149 |

Frozen validation text NLL fell from 8.061948 to 6.867149 on a 512-token
panel. Final TEST text NLL is 6.873340 (perplexity 966.17; 3.06216 bits per
decoded UTF8 byte). These tiny one-seed panels do not establish general capability.

Committed stage time totals 1,530.91 seconds (25.52 minutes). Observed wall time
from pipeline initialization to final report is 2,943.32 seconds (49.06 minutes),
including packing, pauses, control work, recovery and evaluation. A shared 8 GiB
memory-limit kill after checkpoint 192 required resume. Its uncheckpointed lost
work is unknown (0–32 updates) and is excluded from committed metrics. File-cache
release hints on this task's files restored RAM headroom; no data/config/math was
changed. This is a host-limited observation, not an architecture speed comparison.

RL sampled four real full-vocabulary trajectories, all with zero verified reward.
Its two optimizer updates therefore do not demonstrate reward-driven improvement;
general-text replay and regularization remain part of that stage's objective.

The final warmed CPU inference observation was 23.71 decode tokens/sec, 42.18 ms
per token, and 829,440 tensor-state bytes after 16 decoding steps (one replicate).
A separate forced-length stress sampled 273 tokens / 910 UTF8 bytes at temperature
0.9 with finite logits/state; stop/control tokens were masked for this diagnostic.
It does not establish coherent long-form generation or natural stopping.

Fresh installed-wheel chat, request isolation and localhost SSE passed. Missing
chat token/cross-origin requests returned 403; malformed JSON returned 400. All stage
dependency/checkpoint/tokenizer/registry hashes recomputed successfully.

Counted supported training operators total 4,618,367,444,480 FLOPs over committed
work, with the coverage limits in each metric. Total hardware FLOPs remain unknown;
GPU-hours are zero. Coding/tool-use and general instruction benchmarks were not run.

## Downloaded artifacts

- [Prepared data and BPE tokenizer](https://chatgpt.com/library?file_id=libfile_54a58f500e608191b02128b02692d5aa&account_id=personal),
  303,554,879 bytes, SHA256 `1324ad164ebb54f74c9d9154ad3678f2acdb889d6d32f935021b78429ee2883a`.
- [Recovery checkpoints and comparison](https://chatgpt.com/library?file_id=libfile_5075c25fbce081919f07fa36053c38b1&account_id=personal),
  371,938,394 bytes, SHA256 `1fa62b8bc0d425ea36cddeb525bb8fb5820719ade8a9c3da9b875344c57f5a47`.

- [Pilot model and BPE](https://chatgpt.com/library?file_id=libfile_d5f8e6b2656c8191a3d697bfc4dde0e4&account_id=personal), 37,204,983 bytes.
- [Pilot reports, rollouts and validation logs](https://chatgpt.com/library?file_id=libfile_cde3725c5de48191a1e4ac5cab2cfdbb&account_id=personal), 105,523 bytes.
- Five per-stage checkpoint bundles are indexed with hashes and download identities
  in `EVIDENCE.json`; these contain the actual optimizer/model artifacts.

Raw shards are outside Git. The prepared-data archive contains an offline resolved
CUDA recipe and selected release, so a training node can use it without the raw
Hub cache after installing dependencies and this source version.

## Claim boundary

Public evidence remains **NOT_QUALIFIED**; execution attestation is **UNKNOWN**.
The small CPU pilot cannot establish useful assistant behavior, reasoning gains,
DPO/RL benefit, architectural superiority or full-training completion. Full GPU
execution, mixed precision, distributed correspondence, coding/tool benchmarks and
independent scientific qualification remain unverified or unevaluated.
