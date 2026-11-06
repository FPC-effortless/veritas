# Held-out Transfer Semantics

Canonical ontology for evaluation regimes in Veritas. Semantic role: the "VeritasWorld"
of the canonical ontology is the existing `OperationalWorld`; the "VeritasEpisode" is the
existing `OperationalEpisode`. No duplicate runtime classes are introduced.

Status: **semantics and evidence boundaries only.** This document does not implement the
later adaptive loop, and it defines no runtime class, training pipeline, or qualification gate.

Owning Work ID: `ONTO-001` / #387 — branch `feat/canonical-veritas-ontology`,
positive ownership `docs/experience/held-out-transfer.md` only.

## 1. Purpose and scope

Veritas reasons about capability evidence across several evaluation regimes. Those regimes
are adjacent, and their names are used loosely across subsystems ("held-out", "transfer",
"OOD"). That adjacency is the failure mode this document closes: one regime's evidence being
cited as if it were another's, and an existence claim being read as an improvement claim.

The terms below are **operational**, not terminological. Each definition states the condition
that must be checkable in the repository's own evidence artifacts, and each is falsifiable in
the same terms.

In scope: the five evaluation regimes, the distinction between transfer-existence and
transfer-improvement, and the evidence chain expressed in existing repository artifacts.

Out of scope (explicitly deferred, see §10): `DistributionProfile`, `DifficultyVector`
semantics, adaptive world mutation, causal capability-gap semantics, training pipelines, and
all later phases of the canonical ontology work.

## 2. Evidence chain

The chain below is stated entirely in artifacts that exist in the repository today. Each arrow
is a binding, not a data flow; the document does not require any of them to be wired together
in a new runtime path.

```text
CapabilityContract            what capability is being evaluated
        ↓  capability binding
OperationalWorld              the condition under which it is evaluated
        ↓
OperationalEpisode            one bounded evaluation instance
        ↓
Agent execution               actions taken under the episode's task contract
        ↓
Execution + Effects           state transitions, costs, termination
        ↓
Independent verification      verifier against the hidden oracle
        ↓
MachineExperience             canonical, visibility-classified experience record
        ↓
Failure evidence              failure families; missing/absent behavior
        ↓
CapabilityGap                 recurring, severity-weighted capability deficit
        ↓
Qualification                 maturity record under an explicit policy
        ↓
TransferEvaluation            comparison of capability behavior across conditions
        ↓
Held-out transfer             transfer evidence whose target population was never
                              development evidence
```

### 2.1 Stage-by-stage

| Stage | Repository-native artifact | Role in the chain |
|---|---|---|
| `CapabilityContract` | `src/investigation_world/foundry/models.py` | Declares the capability: `capability_id`, `objective`, `subcapabilities`, `success_conditions`, `failure_conditions`, `hard_invariants`, and the intended `transfer_targets`. A capability is not defined by task text; it is defined by this contract. |
| Capability binding | `CapabilityFamily` (`src/investigation_world/foundry/capability_families.py`) | Binds a contract to one capability domain. Families deliberately do not collapse into one task taxonomy: `external_investigation_capability_contract()` and `selective_agency_capability_contract()` are separate families even where they reuse foundry infrastructure. |
| `OperationalWorld` | `src/investigation_world/operational_world/` | The condition under which the capability is evaluated: the compiled world, its permitted systems, its action surface, and its scenario distribution. "VeritasWorld" in the canonical ontology *is* this. |
| `OperationalEpisode` | `src/investigation_world/operational/models.py` | One bounded evaluation instance: `episode_id`, `world_id`, a `TaskContract`, `records`, and a `HiddenOracle`. "VeritasEpisode" in the canonical ontology *is* this. |
| Agent execution | agent actions under the task's `available_actions` | The behavior being evaluated. The task's public action surface is what the agent sees; the oracle is what it does not. |
| Execution + Effects | `OperationalRecord`, `TraceEvent`, `StateSnapshot` | Observable state transitions, costs, and termination. Effects are what verification reads; intent is not. |
| Independent verification | `src/investigation_world/verifier/aggregate.py::verify` | Task-scoped verification against the hidden oracle: identity, relationships, temporal, evidence support, provenance, abstention, calibration, efficiency. Verifies the *artifact produced*, not the process that produced it. |
| `MachineExperience` | `src/investigation_world/experience/models.py` | The canonical record of one verified episode: `TrajectoryV2`, `ExperienceMaturity`, readiness, initial conditions, epistemic snapshots, spans, structural records, and a `VisibilityClass`. |
| Failure evidence | `FailureFamily` (`src/investigation_world/experience/models.py`) | Grouped recurring failures with affected capability, candidate origin, and mechanisms. Also includes *absence of behavior*: an expected action never occurring is failure evidence, not a zero-length success. |
| `CapabilityGap` | `src/investigation_world/experience/models.py` | A recurring, severity-weighted capability deficit supported by failure families, with `environment_ids`, `prerequisite_candidates`, `missing_procedure_candidates`, and `proposed_interventions`. |
| Qualification | `MaturityRecord` under `MaturityPolicy` (`src/investigation_world/qualification/maturity.py`) | Evidence that an environment's maturity requirements are met under an explicit policy, with per-gate `GateOutcome` values. |
| `TransferEvaluation` | defined normatively in §8 | The comparison of capability behavior across two explicitly identified conditions. |
| Held-out transfer | defined normatively in §5 | Transfer evidence whose target population was never used as development evidence. |

## 3. Development evaluation

**Definition.** Evaluation used while developing, selecting, or revising an agent or system.

**Operational test.** An evaluation is *development evaluation* iff its results were available to
a decision that changed the candidate — the agent's prompt or scaffold, its tool surface, the
selected candidate among alternatives, or the environment/task generation that produced it.

**Consequences.** Development evaluation is legitimate and necessary, but it carries no
qualification weight, because the outcome is conditional on the loop it informed. A development
evaluation that looks at a population, and is then used to tune toward that population, has
disclosed that population to the candidate. Any later evaluation on that same population measures
the tuning as much as the capability.

**What makes it falsifiable.** Development status is a provenance claim about a population, not a
claim about the evaluator's intentions. It is falsified by any artifact showing the evaluation
population informed a candidate revision — split membership alone does not prove it, and split
membership alone does not disprove it.

**Repository grounding.** `FoundryTaskMetadata` records the split, seed, capability tags, and
`mutation_lineage` of each task; `RolloutTrace` binds the environment/task/harness/runtime
versions. Those identities are what make "was this population used as development evidence?"
answerable, rather than a matter of recollection.

## 4. Qualification

**Definition.** Evidence that an explicitly defined capability/evaluation contract has met its
stated qualification criteria under the applicable verifier and evaluation conditions.

**Operational test.** Qualification holds iff all of the following are checkable:

1. a `CapabilityContract` identifies the capability, with its success conditions, failure
   conditions, and hard invariants stated *before* evaluation;
2. an applicable verifier and evaluation conditions are identified (world, episode, budget,
   oracle, version identities);
3. a stated qualification criterion exists — a threshold, or a gate set, with a policy;
4. the evidence is produced by verification of the agent's artifact against the hidden oracle,
   not by the agent's own report;
5. the outcome is recorded under that policy, with `PASS`/`FAIL`/`UNKNOWN` semantics;
6. the population that satisfied the criterion is identified, so that the qualification can be
   scoped to it and not extended by analogy.

**Consequences.** Qualification is scoped to the exact contract, verifier, conditions, and
population it was recorded against. It is not a property of the agent in general, and it is not
transitive: qualification on one capability contract says nothing about another, and
qualification under one distribution says nothing about another.

**What makes it falsifiable.** Qualification is falsified by any of: criteria stated after
evaluation; a criterion satisfied only by weakening the verifier or the gate; evidence produced
by the evaluated party; an unrecorded or unidentified population; or a scope extension beyond
the recorded population.

**Repository grounding.** `EnvironmentMaturity` / `MaturityPolicy` / `MaturityRecord` /
`GateOutcome` (`src/investigation_world/qualification/maturity.py`) already implement this pattern for environments, and
`EvidenceRecord` (`docs/evidence/shared-evidence-contract.md`) supplies the fail-closed
`OBSERVED`/`PASS`/`FAIL`/`UNKNOWN` envelope. Note the deliberate non-equivalences: implementation
verification is not scientific qualification; scientific qualification is not frontier
qualification; none is release readiness (`.agents/veritas/OVERLAY.md`).

## 5. Held-out evaluation

**Definition.** Evaluation on a separately identified evaluation population that was not used as
development evidence.

**Operational test.** An evaluation is *held-out* iff, and only if, the evaluation population
satisfies all of:

1. **Identified.** The population is named as an explicit set of episode/world identities — not
   "the hard ones", not "the rest".
2. **Disjoint at identity.** No episode identity in the evaluation population appears in any
   development evidence set. Disjointness is at the level of episode/world identity and its
   generating seed, not at the level of scenario-family label or difficulty description. Two
   episodes generated from the same world seed are the same evaluation instance, not two.
3. **No prior disclosure.** No member of the population was shown to, tuned against, selected
   against, or filtered out by a candidate-revision decision (§3).
4. **Frozen for the claim.** The population is frozen at claim time. Adding members after a poor
   result, or removing members after a poor result, voids the held-out status of that claim.

**Consequences.** Held-out is a *provenance* property of a population with respect to a candidate
lineage. It is not a difficulty property and not a novelty property. A held-out population can be
easy; an easy held-out population is still held-out. Conversely a hard population that was used
for development tuning is not held-out, however hard it is.

**What makes it falsifiable.** Held-out status is falsified by any overlap at identity level with
a development evidence set, or by any prior disclosure of a member to the candidate lineage.

**Repository grounding.** The repository already enforces this shape in several places.
`InvestigationPackSpec` (`src/investigation_world/operational_world/capability_pack.py`) declares
`PackSplit = "train" | "dev" | "public_eval" | "private_eval" | "ood_eval"` and rejects
`ood_scenarios` that intersect `train_scenarios`; the pack's public manifest states
`"ood_definition": "held-out scenario families with disjoint world seeds"`, and pack compilation
rejects OOD scenario leakage into in-distribution splits. `src/investigation_world/operational/distribution.py` and
`src/investigation_world/projectworld/distribution.py` both raise on train/held-out task-ID overlap and on OOD splits that
lack held-out archetypes. The foundry training-bundle compiler excludes held-out/OOD/adversarial
trajectories, and `src/investigation_world/foundry/training_corpus.py` raises if a held-out trajectory enters the training
demonstration corpus (`docs/capability-foundry.md`, "World splits").

Held-out in this document generalizes those mechanisms to the evidence chain as a whole: the same
identity-level disjointness that protects a training split protects a qualification claim.

## 6. Transfer

**Definition.** Evidence that capability behavior carries from one explicitly defined
condition/domain/distribution to another.

**Operational test.** Transfer evidence exists iff all of:

1. a `CapabilityContract` identifies the capability being transferred;
2. two conditions are explicitly identified — a source condition and a target condition — each
   stated as the world/episode distribution and version identities that make it reproducible;
3. the capability is observed to hold in the target condition, under the same contract's success
   and failure conditions and the same verifier;
4. the two conditions are not the same condition restated (a renamed copy of one distribution is
   not a distinct target).

**Consequences.** Transfer evidence is *comparative only in the sense that two conditions are
compared*. It says behavior carries. It does not say behavior carries *well*, or better than
before, or better than an alternative. See §7.

**What makes it falsifiable.** Transfer evidence is falsified by: an unspecified or
unreproducible source or target condition; the target condition being a restatement of the
source; the target observation failing the contract's success conditions; or the two observations
being made under different contracts or different verifiers.

**Repository grounding.** `CapabilityContract.transfer_targets` is the intended declarative
handle: a contract names the conditions it intends to transfer into, before evaluation.
`docs/capability-foundry.md` already states the core discipline — "A training reward increase is
not sufficient evidence of capability gain. The primary learning result should report transfer
into held-out and OOD worlds." This document makes that discipline apply to *all* transfer
claims, not only training-linked ones.

## 7. Transfer evidence exists ≠ transfer improvement has been measured

These are distinct evidence classes. Neither implies the other in the direction that matters.

**Transfer evidence exists.** The conditions of §6 hold: the capability is observed to hold in an
identified target condition. This is an existence claim about behavior carrying across a
boundary. It is compatible with the target result being poor in absolute terms, and compatible
with no change from the source condition at all — carrying is not improving.

**Transfer improvement has been measured.** A *quantified* comparison against a defined baseline,
satisfying all of:

1. a pre-stated comparison: which metric, which baseline, which direction counts as improvement,
   and over which identified populations;
2. a defined baseline, and the baseline's own development/held-out status stated explicitly;
3. uncertainty reported — seeds/replicates, variability or intervals, failures, and limitations —
   consistent with `.agents/veritas/OVERLAY.md` evidence semantics;
4. no selection over candidate comparisons after seeing results; the comparison that is reported
   is the comparison that was pre-stated.

**Forbidden inference.** The existence of a held-out evaluation does not imply that transfer
improvement was measured. Neither does the existence of a held-out evaluation with a favorable
result, nor the existence of a favorable held-out result alongside a weaker development result.
A favorable held-out result is a single point of evidence about a target condition; improvement is
a claim about a *difference* against a defined baseline, and a difference requires a baseline and
a pre-stated comparison.

**Why this is the load-bearing distinction.** "We evaluated held-out and it went up" is the
characteristic form of an unmeasured improvement claim. The favorable result may be real; the
*improvement* is not measured by it, because no baseline was fixed and no comparison was
pre-stated. Under this document that statement is evidence of transfer existence only.

**What makes it falsifiable.** An improvement claim is falsified by: no pre-stated comparison; a
baseline selected after results; missing uncertainty reporting; or a baseline whose own
development status is unstated (an in-development baseline makes the comparison part of the
development loop).

## 8. OOD evaluation

**Definition.** Evaluation under a distributional condition that differs from the specified
development distribution.

**Operational test.** An evaluation is *OOD* iff all of:

1. a **development distribution is specified** — explicitly, as the world/scenario distribution
   and version identities that the candidate was developed against;
2. the evaluation distribution **differs from it**, and the difference is identified — which
   scenario families, which world seeds, which condition parameters were changed;
3. the evaluation population satisfies the held-out conditions of §5 with respect to the
   candidate lineage, unless the evaluation is *explicitly labeled* as a non-held-out OOD probe.

**Consequences.** OOD is relative to a *specified* development distribution. Without one, nothing
can be out of distribution, because there is no distribution to be out of. An OOD population is
not automatically held-out, and a held-out population is not automatically OOD — a held-out split
drawn from the same distribution is held-out but in-distribution.

**What makes it falsifiable.** An OOD claim is falsified by: no specified development
distribution; an unspecified difference; or a difference that is only a relabeling of the
development distribution.

**Repository grounding.** `DistributionSplit` distinguishes `TRAIN`, `IID_TEST`, `OOD`, and
`ADVERSARIAL` (`src/investigation_world/foundry/models.py`), so in-distribution and out-of-distribution are already
distinct named splits rather than adjectives. `InvestigationPackSpec` enforces disjointness of
`ood_scenarios` from `train_scenarios` and defines OOD as held-out scenario families with
disjoint world seeds. ProjectWorld distribution validation requires OOD splits to contain
held-out project archetypes.

## 9. Regime matrix

| Regime | Core assertion | Defeating overlap | Implies improvement? |
|---|---|---|---|
| Development evaluation | Result informed a candidate revision | — | No |
| Qualification | Contract met its stated criteria under a stated policy | Unrecorded population; criteria stated after evaluation | No |
| Held-out evaluation | Population disjoint from development evidence | Identity overlap with a development set | No |
| Transfer | Behavior carries between two identified conditions | Target is a restatement of source | No |
| OOD | Distribution differs from a specified development distribution | No specified development distribution | No |

Two further non-implications are deliberate:

- **Held-out does not imply OOD.** A held-out split drawn from the development distribution is
  held-out, and in-distribution.
- **OOD does not imply held-out.** A distribution-shifted population previously used for
  development tuning is OOD and not held-out.

## 10. Explicitly deferred

This document defines semantics and evidence boundaries. It does not define, and must not be read
as implying:

- `DistributionProfile` — no distribution abstraction is introduced here;
- `DifficultyVector` semantics — the parametric difficulty manifold exists
  (`src/investigation_world/foundry/models.py`) but its semantics are out of scope for this phase;
- adaptive world mutation — the world is not modified by evaluation results in this document;
- causal capability-gap semantics — `CapabilityGap` is used as a *descriptive* aggregate over
  failure families, with frequency, severity, and candidate prerequisites/procedures. No causal
  claim ("this gap *causes* that failure") is defined or licensed;
- training pipelines — no training, curriculum, or learning loop is defined. Where this document
  touches training artifacts, it is to state what they must exclude, not what they must do;
- the later phases of the canonical ontology work, including any adaptive loop.

`CapabilityGap` appears in the evidence chain as the stage where recurring failures become a named,
severity-weighted capability deficit. Its appearance is descriptive and associational: it records
what fails, how often, how severely, in which environments, and which prerequisites or procedures
are candidates. It is not a causal diagnostic.

## 11. Non-implementation statement

This document introduces no runtime class. It changes no product, verifier, qualification,
release, SRE/HUD, or training code. It does not modify `OperationalEpisode`, `OperationalWorld`,
`CapabilityGraph`, Gold-10 surfaces, release artifacts, or any package or schema version.

Where it names artifacts, it names them so that claims about evaluation regimes can be checked
against the repository's own identities. That is the whole of Phase 1: making the boundary
between regimes, and the boundary between existence and improvement, a matter of record rather
than of phrasing.
