# Machine Experience Foundation

Veritas treats a trajectory as a versioned unit of machine experience.

This layer is additive. `TrajectoryV2` remains the canonical execution, replay, identity, provider/resource-call, verification, termination and public/private visibility record. `MachineExperience` wraps that trajectory with learning-readiness and structured analysis annotations; it does not implement a second runtime or recorder.

## Product boundary

Veritas owns evidence that a capability works and evidence that experience creates transferable capability. It does not become a trainer, model-serving stack, generic memory platform, agent framework, workflow engine, sandbox cloud or observability vendor.

## Two maturity axes

Environment maturity remains independent from experience maturity.

Experience maturity is:

1. `E0_TRACEABLE`
2. `E1_REVERIFIABLE`
3. `E2_DIAGNOSTIC`
4. `E3_COUNTERFACTUAL`
5. `E4_CURRICULUM_READY`
6. `E5_PROCEDURE_READY`
7. `E6_ABSTRACTION_READY`
8. `E7_CONTINUAL_LEARNING_READY`

The implementation fails closed. A maturity declaration above E0 is rejected unless the readiness evidence required for that level is explicitly `PASS`.

## Readiness

Every readiness field is `PASS`, `FAIL`, `UNKNOWN` or `NOT_APPLICABLE`:

- reverification
- failure analysis
- counterfactual analysis
- causal analysis
- procedure induction
- abstraction induction
- curriculum construction
- training construction
- continual learning

`PASS` requires at least one evidence reference. PASS evidence may not be more private than the assessment itself, preventing a public/buyer-safe PASS from silently depending on evidence that is hidden at that same serialization level.

## Structured epistemic state

Machine Experience does not require or store hidden chain-of-thought. Environments may deliberately elicit compact protocol outputs such as:

- hypotheses;
- confidence;
- evidence for and against;
- unresolved questions;
- contradictions;
- missing information;
- decision thresholds;
- belief revisions tied to evidence references.

These records are explicit task/environment outputs suitable for verification and analysis.

## Hierarchical spans

`ExperienceSpan` annotates ranges of canonical trajectory steps. Spans may nest, but a child must be fully contained by its parent. Spans cannot extend beyond the trajectory event range. This supports capability/subgoal/tool/procedure analysis without modifying the trajectory schema.

## Failure semantics

Trajectory `FailureCategory` remains the origin taxonomy: model, harness, tool/action, environment runtime, verifier, dataset/task, infrastructure/provider, budget termination or unknown.

The experience layer adds a root-cause mechanism taxonomy: knowledge, observation, retrieval, evidence weighting, identity resolution, planning, tool selection/execution, permission/authority, state tracking, temporal reasoning, process, recovery, verification, resource budget, premature termination, over-action, under-action and coordination.

`FailureFamily` groups experiences with a shared precursor/divergence and affected capability. `CapabilityGap` summarizes supporting failure families, severity, environments and candidate interventions. Wave 1 defines these contracts only; clustering and causal attribution belong to later diagnostic work.

## Stable identity

`experience_id` is content-derived from the canonical `trajectory_id`. Readiness, diagnostics and downstream annotations can accumulate without changing the identity of the underlying experience.

`ExperienceSequence`, `FailureFamily` and `CapabilityGap` also use deterministic content-derived identities.

## Privacy

Public and buyer-safe Machine Experience serialization never widens the nested trajectory visibility boundary. Evaluator-private/sealed references and private metadata are omitted at lower visibility levels.

## High-Stakes Investigation / Gold-10

Gold-10 is the first proving ground for this axis, but current source/report acquisition is not blocked by learning-readiness work.

Staged target:

- acquisition/reconstruction: no experience maturity required;
- first executable episodes: E0 traceable;
- verifier/capability-screen stage: target E1 reverifiable + E2 diagnostic;
- counterfactual claims: require E3;
- curriculum/procedure/abstraction/training/continual-learning claims: require their explicit later readiness evidence.

Investigation tasks should elicit structured hypotheses, confidence and evidence updates where they are capability-relevant so Veritas can measure belief revision without relying on hidden reasoning.

## Deferred work

The foundation intentionally does not implement:

- first-divergence analysis;
- recoverability scoring;
- automatic failure clustering;
- counterfactual generation;
- procedure induction;
- abstraction induction;
- curriculum mining;
- training bundle construction;
- continual-learning loops.

Those are separate evidence-bearing programs built on this contract.