# FULLCYCLE-003 outcome and falsifiers

Build dataset acquisition/caching/preparation for real pretraining, mid/SFT,
preferences and verifier-backed RL. Pin public upstream repository revisions,
license metadata, shard paths and digests; keep raw data outside Git. Fit BPE
only on TRAIN. Freeze public held-out splits and never train on benchmark TEST.

Use the actual LANGDEPTH106 four-layer allocation as the width blueprint:
d_model=120, heads=4, key/value dimensions=16, write rank=2, FFN=224,
window=128, chunk=32, rotary fields, local RoPE, tied embeddings. Increase
unique layer depth to reach 10M +/-1% after adding a 3072-symbol fitted BPE.
Do not substitute the old fixed-size TAC098 or reuse one layer's parameters.

Acceptance: actual public source downloads, reproducible locked manifests,
correct split and role conversion, real 10M forward/backward/checkpoint/generation,
all lifecycle stages on public-data pilot, immutable full-scale run configuration,
resource measurements and an honest full-training/compute status. Full run target
is 200M pretraining token presentations plus post-training; this is an engineering
budget, not a promised capability or compute optimum.

Falsifiers: unpinned changing inputs; public TEST imported as TRAIN; tokenizer fit
on held-out text; secret values in logs/receipts; hidden truncation of conversations;
synthetic labels reported as model rollouts; missing model layers/parameters;
finite-loss-only validation; training artifacts omitted; CPU pilot reported as full
200M-token training; invented GPU availability, throughput or capability claims.

Scope: task branch, Forge language/acquisition, TrainLab adapters/controller/CLI,
public evaluator, tests/docs/manual runners. Existing qualification rules remain
unchanged. No main merge, account subscription, or paid capacity upgrade implied.
