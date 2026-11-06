# HUD / DataVendor Flagship: Veritas SRE Evaluation Pack v1

## Purpose

This document defines the commercial demonstration path for Veritas on HUD/DataVendor.
The flagship is **Veritas SRE Evaluation Pack v1**, not a parallel synthetic benchmark.
It uses the already-qualified Veritas SRE v4 release through the vendor-neutral 0.11
portability contract.

## Why this is the flagship

Veritas already identifies SRE v4 as its first portability proof: it is qualified, frozen,
sealed, real-model-tested, and pilot-rehearsed. The portability layer exports that qualified
release to HUD without making HUD the Veritas core abstraction.

The demonstration should therefore prove one coherent chain:

```text
frozen qualified SRE v4 panel
  -> incident title and early public updates
  -> model / agent causal-class answer
  -> deterministic evaluator-private classification grader
  -> portable HUD task / reward
  -> buyer-safe aggregate evaluation report
```

## What the reviewer should see

1. A permitted public/synthetic incident fixture with incomplete early evidence.
2. The distinction between early agent-visible updates and later evaluator-only evidence.
3. A structured answer selecting regression, infrastructure, capacity or transient.
4. Deterministic classification grading rather than a narrative-quality judgment.
5. Correct, incorrect, empty and malformed-answer smoke cases with expected rewards.
6. Buyer-safe aggregate metrics, clearly distinguished from single-fixture smoke results.
7. Hosted evidence only after a separately authorized run has actually completed.

The frozen SRE SKU does not implement stateful remediation, native-artifact mutation,
trajectory-wide operational invariants, tool-budget scoring or seven-dimensional verification.
Those broader Veritas capabilities require their own environment and evidence contracts.

## Existing Veritas evidence

The repository's 0.11 portability contract states that the first proof SKU is SRE v4 and
that HUD is an adapter over a vendor-neutral portable contract. The contract includes
reset, capability, verifier, artifact/provenance/licensing, taskset visibility, and
content-derived identity guarantees.

The SRE HUD adapter uses the canonical classification reward rather than recreating a second
HUD-only benchmark. The generated export is operator-private and includes hidden scoring truth.
Private task rows, hidden labels, evaluator oracles, credentials and private artifacts must
remain outside buyer-safe/public distribution.

## HUD publication path

The current HUD workflow is:

```bash
python tools/export_sre_portable_package.py \
  --qualification /secure/path/qualification.json \
  --output /secure/output/veritas-sre \
  --adapter hud \
  --source-bundle-sha256 <EXACT_SOURCE_SHA256> \
  --expected-candidate-id <EXACT_ID> \
  --expected-evidence-manifest-id <EXACT_ID> \
  --expected-report-id <EXACT_ID> \
  --expected-panel-id <EXACT_ID> \
  --expected-private-release-manifest-id <EXACT_ID>
```

For local validation, follow the generated README's HUD v6 protocol-first task-start/task-grade
commands. Hosted evaluation and deployment are separate, authorized operator actions: first
verify current SDK commands, account permissions and the private evaluator boundary. Do not
upload the generated private taskset or export as a public marketplace artifact. Sealed-data
access, provider transmission and paid compute are not authorized by this document.

## Evidence standard

Do not claim a hosted success rate, taskset ID, environment ID, job ID or trace URL until
it exists in HUD. The registration package must distinguish:

- repository/qualification evidence;
- local deterministic validation;
- hosted HUD execution evidence.

A recording should use an explicitly public/synthetic fixture and show both a correct reference
class and an incorrect/malformed answer. This proves the demonstrated grader behavior, not model
success on the private panel. Private evaluation traces and labels remain operator-only; publish
only authorized buyer-safe aggregates.

## DataVendor positioning

Recommended one-sentence description:

> Veritas supplies verifier-grounded agent environments in which models must investigate,
> act on persistent operational state, preserve safety and process invariants, and produce
> independently verified outcomes—not merely plausible answers.

Recommended flagship description:

> Veritas SRE Evaluation Pack v1 is a qualified, portable incident-cause classification
> environment. Models or agents infer one of four causal classes from incomplete early
> incident evidence and receive deterministic evaluator-private grading and buyer-safe
> aggregate reports.

## Claims boundary

This page does not claim that Veritas has solved open-ended SRE, industrial simulation,
or universal agent reliability. It claims the narrower property that the qualified SRE v4
release has a deterministic, buyer-safe portability path and can be presented through HUD's
environment/taskset/evaluation interface.

The next evidence gate is a real hosted HUD rollout of the exact exported package.
