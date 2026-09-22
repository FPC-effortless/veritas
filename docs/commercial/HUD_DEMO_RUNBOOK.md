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

## 1. Export the HUD package

Run `tools/export_sre_portable_package.py` with the exact qualification artifact and all
expected release identities. Do not use an unqualified or locally modified task bundle.

## 2. Local checks

Build the generated HUD image and run the portability validation suite. Confirm deterministic
reset and reward parity before any hosted run.

## 3. Hosted baseline

```bash
hud eval tasks.py claude --gateway --full
```

Record:
- environment identity/version;
- taskset identity;
- model identity;
- run/job identity;
- reward distribution;
- successful trace ID.

HUD documentation recommends this eval before training because it confirms that the reward
fires, the environment is reachable and the base model has non-zero success.

## 4. Adversarial trace

Run a deliberately unsafe/out-of-order trajectory against a permitted test case. Preserve the
trace and verify that the independent grader rejects it. Do not modify the task or grader between
the success and failure runs.

## 5. Recording

The 90-second recording should show:

1. incident prompt;
2. evidence inspection;
3. stateful tool actions;
4. native artifact/state change;
5. independent reward;
6. adversarial shortcut and rejection.

Avoid showing private task rows, hidden labels, credentials or evaluator-only artifacts.

## 6. DataVendor submission

Replace the `PENDING` placeholders in `docs/commercial/DATAVENDOR_REGISTRATION.md` only with
identifiers copied from the actual HUD deployment/evaluation. Never invent a trace URL or
performance number.
