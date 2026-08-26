# CompanyWorld v0.1 — next experiment status

Updated: 2026-08-26

## Implemented, awaiting successful execution

### Training-value v2

Tool: `tools/run_training_value_v2.py`

Purpose: distinguish four cases that the original held-out-only SFT experiment could not separate:

1. model fails to fit training examples;
2. model fits training examples but does not transfer;
3. model fits and transfers to held-out worlds;
4. target/scorer pipeline is invalid.

Required measurements:

- train-before;
- train-after;
- heldout-before;
- heldout-after;
- parse failures on each split;
- audit generations;
- exact-target verifier sanity check.

The first planned run uses `Qwen/Qwen2.5-0.5B-Instruct`, 12 train examples, 12 held-out examples, 3 LoRA/SFT epochs, and the existing CompanyWorld verifier.

### Noise/conflicting-evidence ablation

Tool: `tools/run_noise_ablation.py`

Perturbation:

- add six irrelevant public operational records;
- add a plausible but non-authoritative `system_projection` containing a conflicting field;
- do not read or modify private oracle state;
- require the deterministic public reference solver to remain at reward 1.0.

Primary measurement:

`clean verifier reward -> perturbed verifier reward`

with parse failures reported separately.

The ablation is intended to test robustness to evidence-selection pressure and misleading operational projections, not simply context length.

## Execution blocker

The repository's public GitHub Actions path has not scheduled the newly added PR-triggered jobs for the current PR head as of this update. A previously observed evidence workflow also ended in failure without producing usable new model artifacts. Therefore the two experiments above must be described as **implemented but not yet executed**.

No empirical result should be inferred from the presence of the workflow or tools.

## External evidence actions already initiated

- Independent reproduction request: GitHub issue #41.
- Marius Hobbhahn / Manifund fit-check email sent 2026-08-26.
- Snorkel Open Benchmarks Grant fit-check email sent 2026-08-26.
- BlueDot Rapid Grant routing/fit-check email sent 2026-08-26.

## Promotion gate

Do not upgrade the current evidence grade until at least one of the following occurs:

1. training-value v2 successfully executes and produces auditable output;
2. the noise/conflict ablation successfully executes on a real model;
3. a stronger model (preferably >=7B or a current API system) is evaluated with baseline-adjusted scoring;
4. a third party independently reproduces an existing calibration result.
