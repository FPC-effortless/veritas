# Gold-10 flagship pilot

Status: executable pilot candidate. This package does not establish scientific,
Frontier, training-value, learning-efficiency, release, or commercial qualification.

## Purpose

ROADMAP-001 turns the frozen CASE-001 selection into ten deterministic, source-grounded
investigation tasks without reopening source selection or RIGHTS-001 authority.

The runtime consumes the canonical Gold-10 manifest and the already reviewed pilot
manifests. It does not commit raw CSB PDFs, duplicate source bytes, create private ground
truth, or reinterpret mutable artifact-review status as authority.

## Trust and evidence boundary

The pilot inherits these frozen CASE-001 properties:

- exactly ten USCSB cases;
- case-disjoint 6 train / 2 dev / 2 eval split;
- exact report, receipt, catalog, URL, source-policy, and task-use authority binding;
- internal task/verifier evidence use only;
- no raw/public redistribution authority;
- no model-training, commercial, scientific, or Frontier authority;
- public temporal cuts with later evidence withheld;
- institutional findings remain evidence, not omniscient/private truth;
- Chevron Richmond remains the pre-model calibration case.

`build_task()` reconstructs CASE-001 before exposing a task. It then reads the matching
reviewed pilot manifest and exposes only public fragments available at the frozen
`simulation_as_of` cut. Later public material is still withheld. Raw report bytes are never
loaded by this layer.

## Task contract

Each task uses the native Veritas `TaskSpec` and has a stable ID:

`GOLD10-<case-id>`

The public task contains:

- the reviewed public objective;
- the frozen case/split identity;
- the evidence IDs available at the temporal cut;
- capability targets;
- public link/content references and modalities;
- the explicit no-hindsight rule;
- the explicit rule that institutional findings are not private truth.

The frozen task and verifier owner paths are materialized under
`src/investigation_world/gold10/tasks/` and
`src/investigation_world/gold10/verifiers/`. Shared behavior lives in the Gold-10 package
so the ten tasks do not fork into ten incompatible mini-frameworks.

## Submission contract

A submission must provide:

- a primary hypothesis;
- a materially distinct alternative hypothesis;
- confidence for both while leaving coherent residual probability mass;
- cited evidence IDs;
- structured epistemic claims;
- unresolved questions where appropriate.

Allowed claim kinds are `fact`, `allegation`, `institutional_finding`, `hypothesis`, and
`uncertainty`. There is deliberately no `ground_truth` claim kind.

## Deterministic verifier

The verifier does not call an LLM. It scores structural and evidence-discipline properties:

- evidence coverage;
- hypothesis structure;
- epistemic integrity;
- calibration integrity;
- rights/temporal integrity.

Submitting evidence that exists canonically but was not available at the frozen cut is a
zero-reward hindsight hard failure. Invented evidence is also a zero-reward hard failure.

An `institutional_finding` claim must cite evidence whose canonical epistemic role is an
official finding. This prevents the structured verifier target from silently promoting a
different evidence class into an institutional conclusion.

For the frozen calibration case, the pilot contract requires explicit unresolved questions
and at least 0.15 residual probability mass across the primary/alternative hypothesis pair.
That threshold is a pilot diagnostic convention, not a scientific calibration claim.

The verifier intentionally does not judge free-form semantic truth. That is a current
maturity limitation, not a hidden LLM-judge fallback. The pilot therefore establishes an
E0 executable/traceable candidate and a falsifiable evidence-discipline surface; stronger
capability claims require later verifier qualification.

## Native trajectory and MachineExperience

`traceable_experience()` records the episode as native `TrajectoryV2`:

1. task reset;
2. evidence inspection;
3. structured findings submission.

The original evaluation is attached through a native `VerifierIdentity`. The trajectory is
then wrapped in native `MachineExperience` at exactly `E0_TRACEABLE`.

No E1+ readiness flag is fabricated. Public experiences contain no private evaluator
reference, event private payload, trajectory private metadata, or experience private
metadata.

Reference episodes are deterministic protocol/solvability fixtures only. They demonstrate
that the task surface, verifier, trajectory identity, and E0 experience capture compose.
They are not expert trajectories and are not evidence of model capability.

## Falsifiers

The owned tests fail if:

- the taskset is not exactly ten cases or the split is not 6/2/2;
- fewer than two evidence modalities remain available across the pilot;
- later Texas City evidence leaks through the 2005 cutoff;
- Chevron Richmond stops being the frozen calibration case;
- invented or hindsight evidence receives nonzero reward;
- a submission can encode a `ground_truth` claim kind;
- hypothesis confidence consumes more than total probability mass;
- calibration collapses uncertainty without penalty;
- reference trajectory or MachineExperience identity becomes nondeterministic;
- E0 experience capture widens private visibility.

## Next qualification work

This implementation is intentionally below verifier/capability qualification. Before any
Frontier, training-value, or commercial claim, follow-on work should add evidence-content
normalization where rights permit, stronger task-specific falsifiers, exploit/shortcut
analysis, case/source/causal/task-structure coverage, and independent verifier
qualification.
