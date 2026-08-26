# CompanyWorld model calibration

This calibration layer measures real language models against a fixed representative slice of the four validated CompanyWorld capability levels:

1. diagnostic investigation;
2. single-action interactive operation;
3. deterministic sequential control;
4. dynamic concurrent portfolio control.

The first calibration mode is `full_context_plan`. The model receives only the public payload and must emit structured JSON. This intentionally isolates reasoning, evidence use, structured output, and control planning from search/tool-loop quality. It is not a replacement for the full tool-using benchmark.

Every run reports three anchors:

- `empty_anchors`: reward from submitting no useful work;
- `reference_anchors`: the oracle-blind public reference controllers, expected to score 1.0;
- `model_scores`: the measured model results.

The fixed slice contains three diagnostic episodes, three interactive episodes, three sequential episodes including delegated-authority cases, and one three-case dynamic portfolio with shared-resource contention and stochastic evaluator-only outcomes.

## CPU calibration ladder

The non-required `Model Calibration` GitHub Actions workflow currently runs:

- `HuggingFaceTB/SmolLM2-135M-Instruct`
- `HuggingFaceTB/SmolLM2-360M-Instruct`
- `Qwen/Qwen2.5-0.5B-Instruct`

These small models establish the low-capability end of the curve inexpensively. Stronger model and tool-loop calibration should be added after the harness and score reporting are stable.

## Run locally

Install a CPU or GPU PyTorch build plus Transformers/Accelerate, then run:

```bash
python tools/run_model_calibration.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --output calibration-results/qwen2.5-0.5b.json
```

Calibration JSON includes per-level mean/min/max reward, parse failures, reference anchors, empty anchors, and runtime metadata.
