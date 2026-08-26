# Veritas North Star

Veritas is a **verified capability foundry**. Its purpose is not only to benchmark agents; it is to construct executable capability-development worlds, generate and curate verified trajectories, train or improve policies through external trainer adapters, and independently measure whether capability transfers to held-out worlds.

CompanyWorld is the first commercial environment and evaluation package. It is not the definition of Veritas.

## Canonical architecture

```text
Reality / data / expert knowledge
            ↓
World calibration specification
            ↓
World compiler / generator
            ↓
Capability contract
            ↓
Task distribution
            ↓
Executable partially-observable world
            ↓
Agent rollout trace  ← single source of truth
            ↓
Independent verifier
            ↓
Verified trajectory corpus
      ┌─────────────┬───────────────┬──────────────────┐
      ↓             ↓               ↓                  ↓
 Evaluation    SFT / preference    RL / VOPSD     Failure mining
      ↓             ↓               ↓                  ↓
 Held-out / OOD transfer       Updated policy     Challenge specs
      └─────────────┬───────────────┴───────────────┬──┘
                    ↓                               ↓
             capability report             distribution expansion
```

## Permanent product invariants

1. **Hidden truth is independent.** The evaluated or trained agent never receives private task oracles, hidden canonical identifiers, verifier targets, private seeds or challenge-generation secrets.
2. **Trace-first execution.** Training, evaluation, counterfactual analysis and failure mining derive from the same versioned rollout trace rather than separate hand-authored narratives.
3. **Verification precedes promotion.** A trajectory becomes an expert demonstration only after independent verification and invariant checks.
4. **Held-out worlds stay held out.** IID test, OOD and adversarial worlds are never silently folded into training data.
5. **World realism is calibrated, not claimed.** Synthetic worlds can be parameterized from public datasets, filings, operational documents, research, telemetry or expert knowledge using explicit calibration targets and provenance.
6. **Capability families remain distinct.** CompanyWorld enterprise control and External Investigation share foundry infrastructure but retain separate capability contracts, source surfaces and transfer targets.
7. **Learner algorithms remain modular.** SFT, preference learning, RL and VOPSD consume verified training bundles through adapters; environment semantics and verifier logic do not depend on a specific learner.
8. **Failure creates new tests, not new truth.** Failure mining may propose challenges and mutations, but hidden truth, production verifiers and benchmark distributions change only through explicit promotion gates.

## Four restored first-class layers

### 1. Expert trajectory system

`ExpertTrajectory`, `ExpertiseAssessment`, `PreferencePair` and `DemonstrationSet` distinguish raw rollouts from training-grade demonstrations. Expert qualification requires verifier-backed success rather than imitation of a preferred workflow.

The trajectory corpus should eventually include:

- successful expert traces;
- recovery traces;
- failed traces retained for diagnostics;
- counterfactual branches;
- chosen/rejected preference pairs;
- teacher-annotated structural guidance for VOPSD;
- provenance linking every derived training example to its source rollout.

### 2. Reality-calibrated world construction

`WorldCalibrationSpec` makes external knowledge an explicit input to world generation without exposing real records to the agent. Calibration sources can include public datasets, regulatory filings, operational documents, research corpora, expert knowledge and telemetry.

Calibration targets cover distributions, dependencies, procedures, common failures and recovery patterns. A generated world should be promoted only when its calibration report satisfies declared tolerances.

### 3. External Investigation capability family

External Investigation is a separate capability family for noisy heterogeneous evidence worlds. Its task surface includes entity resolution, ownership reconstruction, temporal reconstruction, provenance, conflict resolution and due diligence.

It should preserve the original Veritas investigation thesis: tool selection, identity resolution, source disagreement, provenance, hypothesis management, uncertainty, abstention and evidence-backed conclusions under cost constraints.

### 4. Complete training product boundary

`TrainingRecipe`, `TrainingExample` and `TrainingBundle` define what Veritas hands to a trainer. The bundle compiler enforces verifier thresholds, hard-invariant success, split isolation and trace provenance.

Concrete trainer adapters remain separate runtime integrations. The intended adapters are:

- SFT;
- preference optimization;
- RL;
- VOPSD.

A successful training run is not itself evidence of capability gain. The result must be re-evaluated on held-out and OOD worlds with the independent verifier.

## Commercial interpretation

The first wedge is **Veritas CompanyWorld Pilot v1** because private enterprise-agent evaluation is sellable before the complete training foundry is operational.

The long-term product hierarchy is:

```text
Veritas Capability Foundry
├── CompanyWorld
│   ├── private evaluation
│   ├── capability development
│   └── customer-specific enterprise variants
├── External Investigation World
│   ├── OSINT-style investigation
│   ├── provenance / identity / temporal tasks
│   └── domain-specific investigative variants
└── Training Products
    ├── verified demonstration sets
    ├── preference / counterfactual sets
    ├── RL task distributions
    ├── VOPSD bundles
    └── held-out transfer benchmarks
```

No future README, commercial package or environment should redefine Veritas more narrowly than this document without an explicit architecture decision.
