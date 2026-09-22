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
persistent operational world
  -> evidence / telemetry
  -> agent investigation
  -> stateful tool actions
  -> native artifact change
  -> independent seven-dimensional verification
  -> portable HUD task
  -> hosted trajectory / reward
```

## What the reviewer should see

1. A concrete SRE incident with partial observability.
2. Multiple evidence sources whose timestamps/provenance matter.
3. Stateful actions whose preconditions can block unsafe attempts.
4. A real native operational artifact, not only a synthetic status variable.
5. A verifier that reconstructs final state independently of the agent's narrative.
6. Trajectory-wide invariant checks, including harmful intermediate actions.
7. Efficiency/tool-budget scoring.
8. A successful HUD trace and a deliberately failed shortcut trace.

## Existing Veritas evidence

The repository's 0.11 portability contract states that the first proof SKU is SRE v4 and
that HUD is an adapter over a vendor-neutral portable contract. The contract includes
reset, capability, verifier, artifact/provenance/licensing, taskset visibility, and
content-derived identity guarantees.

The native SRE runtime uses the same qualified environment rather than recreating a second
HUD-only benchmark. Private task rows, hidden labels, evaluator oracles, credentials and
private artifacts remain outside the buyer-safe package.

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

Then, from the generated HUD package:

```bash
uv tool install hud --python 3.12 --with anthropic
hud set HUD_API_KEY=...
hud eval tasks.py claude --gateway --full
hud deploy
hud sync tasks <VERITAS_SRE_TASKSET_SLUG>
```

HUD's current documentation describes the same environment -> taskset -> eval -> deploy
loop and recommends a non-zero eval before training or marketplace publication.

## Evidence standard

Do not claim a hosted success rate, taskset ID, environment ID, job ID or trace URL until
it exists in HUD. The registration package must distinguish:

- repository/qualification evidence;
- local deterministic validation;
- hosted HUD execution evidence.

A polished recording should include one successful run and one adversarial/shortcut run.
The latter is important because it demonstrates that reward is tied to operational state
and verifier constraints rather than to plausible prose.

## DataVendor positioning

Recommended one-sentence description:

> Veritas supplies verifier-grounded agent environments in which models must investigate,
> act on persistent operational state, preserve safety and process invariants, and produce
> independently verified outcomes—not merely plausible answers.

Recommended flagship description:

> Veritas SRE Evaluation Pack v1 is a qualified, portable incident-response environment.
> Agents investigate partially observed production-style incidents, operate a native
> artifact, and are graded by an independent verifier over outcome, state, constraints,
> side effects, process, efficiency and evidence.

## Claims boundary

This page does not claim that Veritas has solved open-ended SRE, industrial simulation,
or universal agent reliability. It claims the narrower property that the qualified SRE v4
release has a deterministic, buyer-safe portability path and can be presented through HUD's
environment/taskset/evaluation interface.

The next evidence gate is a real hosted HUD rollout of the exact exported package.
