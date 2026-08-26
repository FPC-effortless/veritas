# Veritas Capability Foundry

Veritas should be treated as a **capability-production system**, not only a simulator or benchmark.

The control objective is:

\[
E^*=\arg\max_E \frac{CapabilityGain\times Transfer\times VerifierReliability\times TaskCoverage}{RolloutCost\times RewardExploitability\times Variance\times EnvironmentBrittleness}
\]

The foundry sits above the validated CompanyWorld environments. It does **not** replace their verifiers or rewrite their rewards.

## Architecture

```text
Capability contracts
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
Outcome-dominant reward
      ↓
┌──────────────┬──────────────┬──────────────────┐
│ RL / SFT     │ evaluation   │ failure analysis │
└──────┬───────┴───────┬──────┴─────────┬────────┘
       ↓               ↓                ↓
  frontier stats   held-out/OOD     challenge generator
       └───────────────┬────────────────┘
                       ↓
             distribution expansion
```

## First-class objects

### CapabilityContract
Defines the capability before tasks are generated: objective, sub-capabilities, success/failure conditions, hard invariants and intended transfer targets.

### DifficultyVector
A parametric difficulty manifold: entities, tools, steps, distractors, missingness, conflicts, dependency depth, budget pressure, stochasticity and adversarial pressure.

### FoundryTaskMetadata
Separates the task distribution from the agent scaffold and executor using explicit `taskset_version`, `harness_version` and `runtime_version`. Every task also carries split, seed, capability tags and mutation lineage.

### RolloutTrace
The rollout is the source of truth: environment/task/harness/runtime versions, state hashes, observations/actions/tool events, state transitions, costs, verifier components, reward and termination.

### CounterfactualBranch
A replay branch points to a state snapshot plus an alternate action. Runtime-specific replay adapters can later execute the branch without changing the branch protocol.

### ChallengeSpec
Failures become structured challenge proposals instead of ad-hoc prompt edits. Evidence failures can create distractor/reordering variants; authority failures produce permission/handoff variants; recovery failures introduce controlled tool failures; exploits become verifier regression challenges.

## Learnability frontier

The curriculum sampler prioritizes under-observed tasks and tasks whose empirical success lies in a configurable frontier, initially 10–70%.

The goal is not a static easy/medium/hard label. The frontier moves as the policy improves.

## World splits

Foundry metadata distinguishes:

- `train`
- `iid_test`
- `ood`
- `adversarial`

A training reward increase is not sufficient evidence of capability gain. The primary learning result should report transfer into held-out and OOD worlds.

## Reward policy

Existing CompanyWorld outcome verifiers remain authoritative. Foundry should preserve:

1. hard invariant gates;
2. terminal outcome dominance;
3. minimal shaping;
4. evidence/process/efficiency as secondary dimensions;
5. acceptance of multiple valid policies that reach the same verified outcome.

No foundry component should reward an imagined workflow merely because it resembles a demonstration.

## Causal fidelity

Replicate what changes policy quality: permissions, entity relationships, state transitions, failures, information boundaries, temporal semantics and tool behavior. Cosmetic UI fidelity is optional unless it changes the information/action problem.

## Closed loop

```text
Train / evaluate
      ↓
Store traces
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

The loop proposes challenges; it does not silently modify hidden truth, verifier code or production task distributions. New challenges must pass the same leakage, oracle-solvability and exploit-resistance gates before promotion.

## Current implementation boundary

The first foundry release implements the control-plane primitives, deterministic public mutations, frontier scheduler, trace store, counterfactual branch descriptors, failure-to-challenge mapping, foundry objective and Pareto analysis.

Next runtime integration milestones are:

1. emit `RolloutTrace` directly from diagnostic/interactive/sequential/dynamic runtimes;
2. add runtime-specific state snapshot/restore and executable counterfactual replay;
3. generate four disjoint CompanyWorld distribution manifests from seed pools;
4. promote ChallengeSpecs through benchmark validation before training use;
5. add a trainer adapter (including VOPSD) that consumes traces without coupling task semantics to the learner harness.
