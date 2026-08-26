# Veritas CompanyWorld v0.1 — empirical evidence report

## Status

**Evidence grade: pipeline-validity baseline, not yet a grant-grade capability benchmark.**

This report promotes already-completed GitHub Actions artifacts into a durable, reviewable evidence bundle. It does not reinterpret failed jobs as successes and does not claim that the current small-model slice validates real-world enterprise transfer.

## Calibration results

Raw mean rewards are shown first. `Net` means reward above the no-work anchor for that level. The deterministic public-reference anchor is 1.0 for every level.

| Model | Parse failures / 10 | Diagnostic | Interactive | Interactive net | Sequential | Sequential net | Dynamic | Dynamic net |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen/Qwen2.5-0.5B-Instruct | 3 | 0.000 | 0.200 | +0.100 | 0.150 | +0.000 | 0.250 | +0.000 |
| Qwen/Qwen2.5-1.5B-Instruct | 0 | 0.000 | 0.133 | +0.033 | 0.150 | +0.000 | 0.250 | +0.000 |
| Qwen/Qwen2.5-3B-Instruct | 0 | 0.000 | 0.133 | +0.033 | 0.100 | -0.050 | 0.250 | +0.000 |
| HuggingFaceTB/SmolLM2-1.7B-Instruct | 7 | 0.000 | 0.100 | +0.000 | 0.150 | +0.000 | 0.250 | +0.000 |
| HuggingFaceTB/SmolLM2-135M-Instruct | 7 | 0.000 | 0.100 | +0.000 | 0.150 | +0.000 | 0.250 | +0.000 |
| HuggingFaceTB/SmolLM2-360M-Instruct | 9 | 0.000 | 0.100 | +0.000 | 0.150 | +0.000 | 0.250 | +0.000 |

No-work anchors in this full-context runtime are diagnostic 0.00, interactive 0.10, sequential 0.15, and dynamic 0.25. This differs from the diagnostic-only benchmark-validation contract, where the empty public policy must score zero. The two evaluation surfaces must therefore be described separately or reconciled before publication.

## What the data currently supports

1. **The evaluation pipeline is operational.** Six open models completed the same 10-episode full-context calibration protocol across diagnostic, interactive, sequential, and dynamic levels.
2. **Structured-output compliance and task capability are separable.** Qwen2.5-1.5B and Qwen2.5-3B had zero parse failures, but their verifier reward remained close to the no-work anchors.
3. **The current slice does not show monotonic capability scaling.** Qwen2.5-0.5B achieved the highest interactive mean (0.20) despite three parse failures; Qwen2.5-1.5B and 3B both achieved 0.133 on the same three interactive episodes. With n=3, this is a diagnostic observation, not a scaling-law claim.
4. **Attempting a sequential plan can score below doing nothing.** Qwen2.5-3B achieved 0.10 on the sequential slice versus a 0.15 no-work anchor. This makes above-anchor reporting essential and is a reason to inspect component rewards before using aggregate score as a leaderboard metric.
5. **The current diagnostic slice is too hard or insufficiently elicited for these models.** Every model scored 0.0 on the three diagnostic episodes, including Qwen2.5-3B.

## Held-out training-value experiments

| Model | Train examples | Held-out | Before | After | Absolute gain | Parse failures before → after | Mean training loss |
|---|---:|---:|---:|---:|---:|---:|---:|
| HuggingFaceTB/SmolLM2-135M-Instruct | 24 | 12 | 0.000 | 0.000 | +0.000 | 12 → 12 | 0.949 |
| Qwen/Qwen2.5-0.5B-Instruct | 24 | 12 | 0.000 | 0.000 | +0.000 | 0 → 0 | 0.635 |

**Result:** neither existing LoRA/SFT experiment improved held-out verifier reward. SmolLM2-135M failed to produce parseable held-out outputs before and after training. Qwen2.5-0.5B remained fully parseable but scored 0.0 before and after. Falling token-level training loss is therefore not evidence of capability improvement in this experiment.

## Validity issues discovered

- **No-work reward semantics differ by evaluation surface.** The diagnostic benchmark validator expects zero empty-policy reward, while interactive/sequential/dynamic runtimes intentionally or incidentally award partial baseline reward to an empty submission. Any public aggregate must report reward above the appropriate level-specific baseline, not raw reward alone.
- **Episode count is too small for comparative claims.** This calibration has only 3 diagnostic, 3 interactive, 3 sequential, and 1 dynamic episode.
- **Parse failure is a major confound for SmolLM and Qwen-0.5B.** Capability and schema compliance need separate reporting.
- **The training experiment lacks a seen-training evaluation.** A zero held-out gain cannot distinguish failure to fit the training distribution from successful fitting without transfer. The next experiment should report train-before/train-after as well as held-out-before/held-out-after.

## Promotion gate for the next evidence release

The next release should not be called grant-grade until it adds: (1) a larger frozen stratified sample, (2) level-specific above-baseline normalization, (3) at least one stronger API/frontier or >=7B open model, (4) noise/conflict/budget/horizon/OOD ablations, (5) a training experiment with seen-vs-held-out diagnostics, and (6) one independent reproduction.

## Provenance

`EVIDENCE_MANIFEST.json` records GitHub workflow run IDs, source commits, artifact digests, and SHA-256 hashes of the extracted raw JSON files. The source GitHub artifacts remain the external execution record until their retention period expires.
