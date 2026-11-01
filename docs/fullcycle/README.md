# FULLCYCLE-001 and FULLCYCLE-002

Forge, TrainLab and Veritas now execute a bounded model-development lifecycle:
streaming release → tokenizer → pretraining → mid-training → assistant-only SFT →
frozen-reference DPO → policy-generated GRPO → public evaluation → model export →
local streaming chat. Both backends completed real training; see [EVIDENCE.md](EVIDENCE.md).
This is an engineering implementation, not a capable-assistant or production-scale qualification.

## Install and reproduce

Python 3.12+ is required for the optional Veritas evaluator. Existing TrainLab and
Forge workbenches retain their lighter default dependencies.

```sh
python -m pip install -e . -e integrations/forge -e 'integrations/trainlab[training]'
curl --fail --location https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt -o input.txt
python integrations/trainlab/examples/fullcycle/prepare_demo.py input.txt .trainlab/data
python -m trainlab pipeline run .trainlab/data/transformer.json --output .trainlab/reference
python -m trainlab pipeline status .trainlab/reference
python -m trainlab pipeline verify .trainlab/reference
python -m trainlab pipeline report .trainlab/reference
python -m trainlab model chat .trainlab/reference/model
python -m trainlab model serve .trainlab/reference/model --port 8787
```

Open `http://127.0.0.1:8787` for the local interface. It streams actual model output,
isolates request state, uses a same-origin token for mutation, and executes no tools.
The public SFT fixture contains tool-role examples; those are formatting/training
examples, not evidence of working agentic tool execution.

Repeat with `tac098.json` and a fresh output directory. That is the exact native
LANGMATH098 module with byte IDs, not a new stacked TAC architecture. The reference
is a native PyTorch causal Transformer with RMSNorm, gated feed-forward blocks,
learned positions, tied embeddings and cached incremental decode. It is not a
nanochat implementation or a nanochat/Hugging Face checkpoint-compatible model.

## Contracts and recovery

A `trainlab.pipeline.v1` JSON configuration pins a `forge.language.v1` dataset,
model, seed, runtime budget and the five ordered training stages. Each stage
requires positive optimizer-update and batch counts. Accepted optional settings
include positive gradient accumulation, gradient clipping, DPO beta, GRPO group
size, KL regularization, bounded stage time and a nonnegative `replay_weight`.

Forge's `language-release` and `language-verify` commands expose the streaming
format. Rows are text, role/content conversations, chosen/rejected preferences or
public verifier tasks. Global source groups stay in one deterministic split.
SQLite indexes support exact-payload deduplication and long-document four-MinHash
signature screening. Rights/provenance must be explicitly declared. This screen
is not semantic contamination attestation; the example splits one Shakespeare
corpus into nonoverlapping chunks, rather than holding out authors or plays.

BPE fitting uses TRAIN only and an explicit bounded byte budget (8 MiB by default).
The native TAC adapter uses a fixed 256-byte vocabulary. Packed uint32 text streams
and disk-backed post-training row indexes avoid loading whole corpora into RAM.
Language training never requests TEST. The public evaluator receives an explicit
validation or final public test split; no protected Veritas panel is opened.

Each run preserves configuration and training/evaluator source hashes, dependency
and device identity, tokenizer and token-stream digests, initial and stage checkpoint
references, evaluation outcomes and metrics. Completed-stage skipping verifies its
exact dependency and artifact set. Resume refuses changed source, runtime, world
size, data or optimizer configuration.

```sh
python -m trainlab pipeline run .trainlab/data/transformer.json --output .trainlab/recovery --stop-stage sft --stop-after 10
python -m trainlab pipeline resume .trainlab/recovery
```

Graceful SIGINT/SIGTERM pauses after an optimizer update. Immutable step checkpoint
blobs are written before an atomic index selects them; the preceding selected
blob remains until publication completes. Checkpoints include optimizer, scaler,
CPU/CUDA RNG and per-rank sampler RNG state. Exact CPU replay is tested for all
objectives, including general-text replay and an injected crash between blob and
pointer publication. This does not establish bitwise cross-hardware equivalence.

## Post-training and evaluation

Mid-training uses full conversational sequence loss; SFT masks all non-assistant
targets. DPO compares chosen/rejected sequence log probabilities against the frozen
stage-start reference. RL samples actual categorical actions from the policy,
verifies integer comparisons, standardizes group rewards and uses the clipped
GRPO objective with reference KL. Its supported action space is exactly two
one-token responses (`0` and `1`); it is not a general multi-token agent RL engine.
Per-update rollout records, action probabilities, rewards and verifier identities
are retained under a pinned rollout manifest.

The demonstration's post-training stages mix general-text replay at weight 0.5.
This was added after a pilot showed severe language forgetting. Replay tokens and
executed supported-operator FLOPs are included in resource accounting.

The evaluator runs in a new process and reloads checkpoint bytes and public data.
It does not accept trainer scores. It reports language NLL/perplexity/bits per
decoded UTF-8 byte, assistant loss, bounded generated exact matches, preferences,
constrained decisions, and warmed CPU inference timings. Its default generated
panel is eight cases; the evidence supplement evaluates **all** public held-out
conversations and explicitly includes the majority-class diagnostic. Raw failed
outputs are retained. Both final models fail to show useful general chat or
nontrivial integer-comparison generalization.

All reports remain `NOT_QUALIFIED`, with independent execution attestation
`UNKNOWN` and `training_validated=false`. Existing TRAIN-001 qualification gates
and protected/financial Verified Learning Bridge semantics are unchanged. This
adapter does not convert that financial bridge's exports into neural trainer data.

## Real GPU execution

```sh
python integrations/trainlab/examples/fullcycle/gpu_run.py .trainlab/data/transformer.json --output .trainlab/gpu-reference --gpus 2
```

The launcher checks real CUDA availability, configures `torchrun`/DDP, chooses
BF16 when supported and otherwise FP16 with scaling for the Transformer. Native
TAC098 remains FP32. Activation checkpointing and gradient accumulation are
supported. Multi-node DDP requires the same shared run/data paths and identical
runtime versions; configure the ordinary torchrun rendezvous for that environment.
FSDP, elastic world-size changes, sharded optimizers and efficient large-scale
external inference engines are not implemented here.

The current execution host has CPU PyTorch and no GPU. Actual Gloo DDP initialization
was attempted and blocked by socket permissions. GPU mixed precision, multi-GPU
correctness, GPU memory/speed and distributed exact replay are therefore unverified.
The manual `fullcycle.yml` workflow exercises the public lifecycle and two-rank
CPU DDP on a conventional runner; it is not reported as having run in this session.

Resource reports distinguish measured supported-operator FLOPs from the unknown
full-operation total and from the separate 6N heuristic. Token counts for BPE and
bytes and unmatched parameter sizes do not establish a fair architecture comparison.
Training timings were measured while other validation jobs shared the CPU host.

## Tests

```sh
python -m unittest discover -s integrations/trainlab/tests_fullcycle -v
python -m unittest discover -s integrations/trainlab/tests -v
python -m unittest discover -s integrations/forge/tests -v
python -m pytest tests/training_qualification -q
python -m ruff check integrations/trainlab/src/trainlab/fullcycle integrations/trainlab/tests_fullcycle integrations/trainlab/examples/fullcycle integrations/forge/src/forge_data/language.py src/investigation_world/lm_evaluation.py
```

The multi-GiB check uses constructed nonlinguistic text and validates ingestion,
reproduction and memory bounds only:

```sh
python integrations/trainlab/examples/fullcycle/streaming_stress.py .trainlab/stress
```

Models are self-contained registry bundles of weights, tokenizer, model config,
chat template and content manifest. Fresh processes verified both bundles using
built, installed wheels outside the checkout. No package release or main merge
is implied by these developer checks.

Native TAC source provenance: `FPC-effortless/TAC-OSM`, commit
`427db08e1d2c971b4fb4c3c579214e289211762e`,
`research/mathematical-engineering/langmath098/model.py`; only formatting changed
in the vendored native module.
