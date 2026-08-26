# CompanyWorld v0.1 — evidence status

Updated: 2026-08-26

## Current evidence grade

**Real pipeline-validity baseline; not yet grant-grade capability validation.**

## Completed evidence

- Fixed CompanyWorld v0.1 protocol and public/private evaluation boundary.
- Six open-model calibration artifacts recovered from public GitHub Actions runs:
  - Qwen2.5-0.5B-Instruct
  - Qwen2.5-1.5B-Instruct
  - Qwen2.5-3B-Instruct
  - SmolLM2-135M-Instruct
  - SmolLM2-360M-Instruct
  - SmolLM2-1.7B-Instruct
- Model-output parsing failures recorded separately from verifier reward.
- Existing held-out LoRA/SFT experiments recovered and reported as negative results.
- Evidence manifest records workflow run IDs, source commits, artifact digests, and raw result hashes.
- Independent reproduction request opened as GitHub issue #41.
- Funding/application packets committed under `funding/APPLICATION_PACKETS.md`.

## Validity upgrade completed

Full-context interactive/sequential/dynamic evaluation surfaces have non-zero no-work anchors. Rather than silently treating raw reward as capability, calibration now supports:

- raw reward;
- above-no-work reward;
- normalized reward relative to the public-reference ceiling.

This preserves the existing reward decomposition while making cross-level interpretation explicit.

## Implemented but not yet successfully executed

### Training-value v2

Measures train-before/train-after and heldout-before/heldout-after using the same verifier, with parse failures and audit generations reported separately. The purpose is to distinguish training-fit failure from lack of held-out transfer.

### Noise/conflicting-evidence ablation

Adds irrelevant public records and a plausible non-authoritative `system_projection` while preserving public-reference solvability. Measures clean-to-perturbed verifier degradation.

### CI status

GitHub Actions has not scheduled the newly added PR-triggered experiment jobs for the current head. Therefore these experiments remain implemented, not empirically completed. See `NEXT_EXPERIMENTS.md`.

## External validation / funding actions initiated

- Independent reproduction request: GitHub issue #41.
- Marius Hobbhahn / Manifund fit-check email sent 2026-08-26.
- Snorkel Open Benchmarks Grant fit-check email sent 2026-08-26.
- BlueDot Rapid Grant routing/fit-check email sent 2026-08-26.

## Remaining promotion gates

1. Execute training-value v2 successfully.
2. Execute noise/conflict ablation on a real model.
3. Add at least one substantially stronger model baseline (prefer >=7B or a current API system).
4. Run a larger frozen stratified evaluation rather than only the 10-episode calibration slice.
5. Add horizon/tool-budget/OOD or adversarial ablations.
6. Obtain a third-party reproduction.
7. Demonstrate positive held-out training lift before making any training-improves-capability claim.

## Claims that remain prohibited

Do not claim that Veritas training improves held-out capability, that current CompanyWorld results rank frontier systems, that the benchmark predicts real deployment performance, or that independent reproduction has been achieved until the corresponding evidence exists.
