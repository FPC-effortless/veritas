# Veritas Capability Foundry

Veritas is a **capability-production system**, not only a simulator or benchmark. CompanyWorld is the first commercial environment; the foundry is the permanent product architecture.

The control objective is:

\[
E^*=\arg\max_E \frac{CapabilityGain\times Transfer\times VerifierReliability\times TaskCoverage}{RolloutCost\times RewardExploitability\times Variance\times EnvironmentBrittleness}
\]

See [`veritas-north-star.md`](veritas-north-star.md) for the architecture invariants that must survive future product narrowing.

## Architecture

```text
Reality / data / expertise
      ↓
World calibration specification
      ↓
World compiler / generator
      ↓
Capability contract
      ↓
Task distribution engine ── imported / procedural / adversarial variants
      ↓
Episode compiler
      ↓
Taskset × Harness × Runtime
      ↓
Executable partially-observable world
      ↓
Rollout trace (single source of truth)
      ↓
Independent verifier stack
      ↓
Verified trajectory corpus
      ↓
┌────────────────┬─────────────────────┬────────────────┬──────────────────┐
│ evaluation     │ SFT / preference    │ RL / VOPSD     │ failure analysis │
└──────┬─────────┴──────────┬──────────┴───────┬────────┴─────────┬────────┘
       ↓                    ↓                  ↓                  ↓
 held-out/OOD         training bundle      new policy      challenge generator
       └────────────────────┬──────────────────┘                  │
                            ↓                                     ↓
                      transfer report                  distribution expansion
```

## First-class objects

### WorldCalibrationSpec
Captures how real-world information calibrates synthetic world generation. Sources can include public datasets, filings, operational documents, research corpora, expert knowledge, telemetry and synthetic priors. Calibration targets can represent distributions, causal/dependency relationships, procedures, failures and recovery patterns.

Calibration does not expose real records or hidden benchmark truth to the agent. It constrains and validates the generated world.

### CapabilityContract
Defines the capability before tasks are generated: objective, sub-capabilities, success/failure conditions, hard invariants and intended transfer targets.

### CapabilityFamily
Keeps capability domains separate even when they reuse the same foundry infrastructure. CompanyWorld and External Investigation must not collapse into a single task taxonomy.

### DifficultyVector
A parametric difficulty manifold: entities, tools, steps, distractors, missingness, conflicts, dependency depth, budget pressure, stochasticity and adversarial pressure.

### FoundryTaskMetadata
Separates the task distribution from the agent scaffold and executor using explicit `taskset_version`, `harness_version` and `runtime_version`. Every task also carries split, seed, capability tags and mutation lineage.

### RolloutTrace
The rollout is the source of truth: environment/task/harness/runtime versions, state hashes, observations/actions/tool events, state transitions, costs, verifier components, reward and termination.

### ExpertTrajectory
A raw rollout becomes a training-grade trajectory only after independent verification and invariant checks. Expert trajectories retain their source trace and can be tagged for expert, recovery, counterfactual, failure or preference roles.

### PreferencePair and DemonstrationSet
Preference pairs represent verifier-backed chosen/rejected trajectories. Demonstration sets collect qualified trajectories and preferences into versioned capability-development assets.

### TrainingRecipe and TrainingBundle
The training product boundary is learner-agnostic. Recipes specify SFT, preference, RL or VOPSD use, verifier thresholds, train splits and held-out splits. Bundle compilation preserves source-trace provenance and excludes held-out/OOD/adversarial trajectories from training examples.

### CounterfactualBranch
A replay branch points to a state snapshot plus an alternate action. Runtime-specific replay adapters can execute the branch without changing the branch protocol.

### ChallengeSpec
Failures become structured challenge proposals instead of ad-hoc prompt edits. Evidence failures can create distractor/reordering variants; authority failures produce permission/handoff variants; recovery failures introduce controlled tool failures; exploits become verifier regression challenges.

## Capability families

### CompanyWorld

CompanyWorld tests enterprise investigation and control across heterogeneous operational systems, including action, authority, recovery, concurrency, deadlines, budgets and independently verifiable outcomes.

### External Investigation

External Investigation preserves the original investigation thesis: noisy heterogeneous evidence, source selection, entity resolution, temporal/relationship reconstruction, provenance, hypothesis management, uncertainty, abstention and precise evidence-backed conclusions.

It has its own capability contract, source surfaces and transfer targets and should eventually have executable task distributions distinct from CompanyWorld.

## Learnability frontier

The curriculum sampler prioritizes under-observed tasks and tasks whose empirical success lies in a configurable frontier, initially 10–70%.

The goal is not a static easy/medium/hard label. The frontier moves as the policy improves.

## World splits

Foundry metadata distinguishes:

- `train`
- `iid_test`
- `ood`
- `adversarial`

A training reward increase is not sufficient evidence of capability gain. The primary learning result should report transfer into held-out and OOD worlds. Held-out trajectories are never emitted by the training bundle compiler.

## Reward and demonstration policy

Existing outcome verifiers remain authoritative. Foundry preserves:

1. hard invariant gates;
2. terminal outcome dominance;
3. minimal shaping;
4. evidence/process/efficiency as secondary dimensions;
5. acceptance of multiple valid policies that reach the same verified outcome;
6. promotion of demonstrations only after independent verification.

No foundry component should reward an imagined workflow merely because it resembles a demonstration.

## Causal fidelity and calibration

Replicate what changes policy quality: permissions, entity relationships, state transitions, failures, information boundaries, temporal semantics and tool behavior. Cosmetic UI fidelity is optional unless it changes the information/action problem.

World realism should be represented through explicit calibration targets and provenance rather than an unsupported claim that a synthetic environment is realistic.

## Closed loop

```text
Train / evaluate
      ↓
Store traces
      ↓
Verify and classify trajectories
      ↓
Promote expert / recovery / preference assets
      ↓
Classify capability failures and exploits
      ↓
Generate ChallengeSpec + mutations
      ↓
Strengthen verifier regression suite
      ↓
Add harder / OOD / adversarial tasks
      ↓
Update frontier statistics
      ↓
Train / evaluate again
```

The loop proposes challenges; it does not silently modify hidden truth, verifier code or production task distributions. New challenges must pass leakage, oracle-solvability and exploit-resistance gates before promotion.

## Current implementation boundary

Implemented foundry layers now include:

- control-plane capability contracts and difficulty vectors;
- deterministic public mutations and task distributions;
- frontier scheduler and foundry objective/Pareto analysis;
- trace store, trace-first runtime proxy and replay descriptors;
- counterfactual branch descriptors and failure-to-challenge mapping;
- CompanyWorld foundry adaptation/materialization;
- External Investigation capability-family contract;
- expert-trajectory qualification, preference-pair and demonstration-set primitives;
- reality-calibration source/target/report primitives;
- trainer-agnostic SFT/preference/RL/VOPSD recipe and bundle compiler with split isolation.

Next integration milestones are:

1. emit `RolloutTrace` directly and consistently from every diagnostic/interactive/sequential/dynamic runtime;
2. add runtime-specific state snapshot/restore and broader executable counterfactual replay;
3. ingest real datasets/domain corpora into `WorldCalibrationSpec` and score generated worlds against calibration targets;
4. build a fully executable External Investigation distribution separate from CompanyWorld;
5. implement expert/reference policies and automated demonstration curation at scale;
6. implement concrete trainer adapters for SFT, preference learning, RL and VOPSD;
7. run post-training transfer evaluation on frozen IID/OOD/adversarial worlds;
8. promote ChallengeSpecs through benchmark validation before training use.
