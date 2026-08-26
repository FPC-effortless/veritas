# CompanyWorld v0.1 evidence package

This directory defines the first public empirical evidence package for Veritas CompanyWorld. It freezes the evaluation protocol before baseline results are interpreted.

## Research question

How reliably do language-model agents reconstruct operational state from heterogeneous, partially conflicting enterprise evidence when correctness is checked against evaluator-only ground truth?

## Frozen baseline matrix

The initial calibration matrix uses the same full-context harness, task slice, deterministic generation settings, and verifier for:

- `HuggingFaceTB/SmolLM2-135M-Instruct`
- `HuggingFaceTB/SmolLM2-360M-Instruct`
- `Qwen/Qwen2.5-0.5B-Instruct`

The matrix is intentionally small and inexpensive. It is a pipeline-validity and discrimination baseline, not a claim about frontier-model performance.

## Execution

The authoritative baseline workflow is `.github/workflows/model-calibration.yml`.

For a local public-model run:

```bash
python -m pip install -e ".[test]"
python -m pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.4,<3"
python -m pip install "transformers>=4.46,<5" "accelerate>=1,<2" sentencepiece

python tools/run_model_calibration.py \
  --model HuggingFaceTB/SmolLM2-135M-Instruct \
  --output results/companyworld-v0.1/smollm2-135m.json \
  --max-new-tokens 256 \
  --max-input-tokens 7168
```

An OpenAI-compatible endpoint can be evaluated with `tools/run_endpoint_calibration.py` without downloading the model locally.

## Integrity prerequisites

Model scores must not be promoted as benchmark evidence until the corresponding CompanyWorld build passes the benchmark-validation harness described in `docs/benchmark-validation.md`.

Required properties include:

- no public/private oracle leakage;
- deterministic public payloads for the frozen build;
- public solvability of answerable tasks;
- zero reward for empty, conclusion-only, citation-only, always-abstain, and blind-projection shortcut policies;
- bounded reward for field stuffing;
- strictly greater reward for evidence-backed correct answers than unsupported correct answers.

## Evidence outputs

Every completed workflow run should produce:

- one raw JSON calibration report per model;
- a comparative `REPORT.md` generated from those raw reports;
- `EVIDENCE_MANIFEST.json` containing the source commit, workflow run identifier, file sizes, and SHA-256 hashes;
- the workflow logs and GitHub Actions provenance for the run.

Raw model outputs are primary evidence. Aggregated reports are derived artifacts and must remain traceable to the raw reports.

## Promotion criteria

`CompanyWorld-v0.1` becomes a publishable baseline only when all of the following are true:

1. the benchmark-integrity report passes;
2. at least three real models complete the identical frozen protocol;
3. the raw results and aggregate report are retained;
4. model/harness/version metadata are recorded;
5. the run is reproducible from a clean checkout;
6. no evaluator oracle, private seed, or private benchmark asset is exposed to the model.

A stronger research release additionally requires an OOD/adversarial comparison, uncertainty estimates where stochastic sampling is used, and at least one external reproduction.

## Interpretation policy

Do not describe a difference between models as a capability finding unless the difference survives basic reproducibility checks and cannot be explained by output-format failure alone.

Do not describe a training improvement as evidence of transfer unless evaluation uses held-out worlds/tasks excluded from the training bundle.

Do not describe CompanyWorld as a validated proxy for real enterprise deployment until external deployment evidence supports that claim.

## Current status

**Protocol frozen; empirical baseline pending successful compute execution.**

The repository already contains the evaluation runners, verifier, anti-shortcut validation harness, report builder, and held-out training-value experiment. The remaining step for this package is execution on external compute followed by publication of the resulting artifacts.
