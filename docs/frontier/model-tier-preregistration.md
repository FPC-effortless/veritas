# SRE v4 model-tier preregistration — zero-capital cycle 1

Preregistered: 2026-08-27, before new cycle-1 scores are inspected.

This file fixes the intended tier interpretation for the first zero-personal-spend SRE v4 calibration cycle. It is not a claim that every listed model will fit available free hardware, nor that any listed model is a frontier-lab system.

| Declared tier | Model ID | Role |
| --- | --- | --- |
| weak | `HuggingFaceTB/SmolLM2-360M-Instruct` | low-capability anchor |
| weak | `Qwen/Qwen2.5-0.5B-Instruct` | low-capability anchor |
| medium | `mistralai/Ministral-3-8B-Instruct-2512` | intermediate open-weight calibration |
| strong | `Qwen/Qwen3.8-27B` | strong open-weight calibration candidate |

No model is preregistered as `frontier` in cycle 1.

## Snapshot rule

A run is admissible only when its `FrontierCalibrationObservation.model_snapshot` records an immutable model revision/version captured before that run's benchmark score is inspected. A moving `main`, `latest`, or provider alias is not silently treated as immutable.

## Substitution rule

If a preregistered model is technically impossible to execute within free compute limits, that is an operational result, not permission to choose a replacement after comparing benchmark scores. A replacement requires a new dated preregistration entry stating:

- exact model ID;
- intended tier;
- technical reason for substitution;
- immutable revision-selection rule;
- confirmation that no replacement-model SRE score had been inspected before the change.

## Claim boundary

`strong` here means only "admitted to the policy's strong tier for this preregistered zero-capital calibration cycle." It does not mean frontier-lab parity, state of the art, or independent multi-provider frontier validation.
