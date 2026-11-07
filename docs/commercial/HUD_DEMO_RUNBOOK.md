# HUD Flagship Demo Runbook

## Goal

Produce buyer-inspectable evidence for Veritas SRE Evaluation Pack v1 using the exact
qualified release exported by the Veritas 0.11 portability layer.

## Prerequisites

- Python 3.12
- Docker
- authenticated HUD account and `HUD_API_KEY`
- authorized access to the sealed SRE qualification artifact
- exact source-bundle SHA-256 and five release identities

Sealed-data access, third-party transmission, hosted evaluation and deployment each require
their applicable authorization. This runbook does not grant it. The generated HUD export is
operator-private and contains hidden scoring truth; never publish the export or its task rows.

## 1. Export the HUD package

Run `tools/export_sre_portable_package.py` with the exact qualification artifact and all
expected release identities. Do not use an unqualified or locally modified task bundle.
Use a new, empty output directory for each HUD export. The exporter rejects nonempty
directories rather than reusing stale runtime or provenance files.

## 2. Local checks

Build the generated HUD image and run the portability validation suite. Confirm deterministic
reset and reward parity before any hosted run.

## 3. Hosted baseline

Use the generated package README's HUD v6 protocol-first task-start/task-grade flow for local
validation. Before a separately authorized hosted evaluation, verify the installed SDK's
supported commands, the receiving account and the evaluator-side privacy boundary. Do not assume
an older `hud eval tasks.py` command or a public taskset upload is compatible or safe.

Record:
- environment identity/version;
- taskset identity;
- model identity;
- run/job identity;
- reward distribution;
- operator-private trace ID and separately approved buyer-safe evidence reference.

Record observed model outcomes, including zero success or parse failures, without changing
the panel or grader to make the result look successful. A reference-answer smoke test validates
the grader, not the evaluated model's capability.

## 4. Adversarial trace

Using a permitted public/synthetic fixture, compare a correct reference class with an incorrect
class, an empty answer and a malformed answer. Verify deterministic expected rewards without
changing the task or grader between cases. These are classification/parse falsifiers, not
evidence of remediation safety or trajectory-wide operational invariant enforcement.

## 5. Recording

The 90-second recording should show:

1. incident prompt;
2. evidence inspection;
3. the model's structured causal-class answer;
4. deterministic grading without displaying hidden evaluator truth;
5. clearly labelled aggregate metrics or public-fixture smoke results;
6. an incorrect/malformed answer receiving the expected failure reward.

Use a public/synthetic demonstration fixture for the recording. Do not show private task rows,
hidden labels, credentials, raw private traces or evaluator-only artifacts. SRE v4's frozen
classification SKU does not demonstrate native-artifact changes or stateful remediation.

## 6. DataVendor submission

Replace the `PENDING` placeholders in `docs/commercial/DATAVENDOR_REGISTRATION.md` only with
identifiers copied from the actual HUD deployment/evaluation. Never invent a trace URL or
performance number.
