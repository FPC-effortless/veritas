# Canonical Veritas Ontology Gap Audit

Work ID: `ONTO-002` (issue #389). Phase 2 of the canonical Veritas ontology program.

This document is an **audit only**. It introduces no runtime class, no schema change, and no
implementation. Where it identifies a gap it names the minimum later change, the dependency, and
the protected surfaces involved. It does not perform that change.

## 1. Purpose

Establish, from repository evidence, the coverage of the canonical evidence lifecycle:

```text
CapabilityContract
        ↓  capability binding
OperationalWorld
        ↓
OperationalEpisode
        ↓
agent execution
        ↓
execution + effects
        ↓
independent verification
        ↓
MachineExperience
        ↓
failure evidence
        ↓
CapabilityGap
        ↓
Qualification
        ↓
TransferEvaluation
        ↓
held-out transfer
```

For every node and edge the audit answers: which repository-native artifact represents it, where
it is implemented, which schema defines it, which tests exercise it, what canonical semantics it
already satisfies, what is partial, and what is genuinely absent.

The audit's second purpose is to prevent architectural duplication. A substantial fraction of the
canonical chain is already implemented under different names. Section 8 records what therefore
does **not** need implementation.

## 2. Audit basis and repository head

- Authority order: `AGENTS.md` → `.agents/veritas/OVERLAY.md` → `.agents/universal/CONTRACT.md` →
  Work Contract #389 → Phase 1 (`docs/experience/held-out-transfer.md`).
- Audited base: `main` at `3499c7dd84031b7a8fdd5c9d092c00a1aef1e74b`, which is `aabbfc6` plus the
  Phase 1 merge (#388). Working branch `feat/canonical-veritas-ontology-audit` at
  `fd7f328460993db9c255064f818ea49d2c9fb4ed`; its tree equals merged `main` (root tree
  `a4c66b95a0905059313cb8299c2d04f6bf33821d`).
- Positive ownership: `docs/experience/canonical-ontology-gap-audit.md` only. No other file was
  modified. Negative ownership from #389 was respected throughout; no file under
  `src/investigation_world/operational/**`, Gold-10, SRE/HUD, `release/**`, `CapabilityGraph`,
  qualification/runtime implementations, training code, or sealed material was modified.
- Method: source and tests were read directly. Statuses are assigned from behavior and schema,
  not from filenames. Where a name differs from the canonical term, the audit asks whether the
  *semantic function* is present before considering `ABSENT`.
- No sealed/private benchmark content is reproduced here. `HiddenOracle` internals are described
  only at the schema level already public in `src/investigation_world/operational/models.py`.

## 3. Canonical lifecycle

The chain is interpreted as a chain of **bindings**, not a runtime data-flow. Phase 1 §2 stated
this; the audit confirms it against code. No stage in the repository is presently wired into a
single end-to-end pipeline, and the audit does not treat that as a defect per se (§13).

Two readings of the chain must be separated throughout:

- **Ontology reading** — each stage is a semantic role that some repository object plays.
- **Implementation reading** — each stage is an object that a runtime constructs and a pipeline
  passes forward.

The audit's central finding is that the chain is largely satisfied under the ontology reading and
partially satisfied under the implementation reading, and that most of what is missing is
*connective tissue and evidence*, not new substrate.

## 4. Status legend

| Status | Meaning |
|---|---|
| `SATISFIED` | Existing repository semantics substantially satisfy the canonical requirement. |
| `PARTIAL` | Existing infrastructure covers part of the requirement; a clearly identifiable semantic, evidence, or interface gap remains. |
| `ABSENT` | No existing repository artifact provides the required semantic function. |
| `NOT SEPARATELY REQUIRED` | The canonical concept is already represented by an existing artifact and does not require a separate object/class/module. |

`NOT SEPARATELY REQUIRED` is applied where the canonical term names a *role* over an existing
object, not a missing object.

## 5. Evidence-chain audit

### 5.1 CapabilityContract

**Artifacts.** `CapabilityContract` in `src/investigation_world/foundry/models.py` (lines 40–51);
producers in `src/investigation_world/foundry/capability_families.py`
(`external_investigation_capability_contract()`, `selective_agency_capability_contract()`) and
`src/investigation_world/foundry/companyworld.py` (`companyworld_capability_contract()`).

**Schema coverage against the canonical requirement.**

| Canonical requirement | Field | Present |
|---|---|---|
| capability identity | `capability_id` | yes |
| capability version | `version` (default `"1"`) | yes |
| objective | `objective` | yes |
| subcapabilities | `subcapabilities: list[str]` | yes |
| success criteria | `success_conditions` | yes |
| failure criteria | `failure_conditions` | yes |
| hard invariants | `hard_invariants` | yes |
| transfer targets | `transfer_targets` | yes |
| portability / content-derived identity | — | **no** |
| binding to executable worlds/episodes | — | **no** (see 5.2) |

**What is already satisfied.** The contract is a complete pre-evaluation declaration: objective,
success/failure conditions, hard invariants, and intended transfer targets are stated before any
task exists. Three real contracts are defined with non-overlapping capability identities
(`external-investigation`, `selective-agency`, `companyworld-enterprise-control`), and each
carries concrete transfer targets, which is exactly the declarative handle Phase 1 §6 requires.

**Gap A — no content-derived identity.** `CapabilityContract` is a plain `BaseModel` with no
`model_validator` and no digest. Every neighboring canonical object has one: `TrajectoryV2`
(`TRAJ-V2-…`), `MachineExperience` (`EXP-…`), `FailureFamily` (`FAILFAM-…`), `CapabilityGap`
(`CAPGAP-…`), `CapabilityGraph` (`CGRAPH-…`), `MaturityRecord` (`MREC-…`), `MaturityPolicy`
(`MPOL-…`). A contract object cannot be content-addressed, so "the same contract" is currently a
string-compare on `capability_id`. This matters downstream: `MachineExperience`,
`FailureFamily.affected_capability`, and `CapabilityGap.capability` all reference capabilities by
bare string, so capability identity is not yet verifiable across artifacts.

**Gap B — definition/evidence separation is expressible but unenforced.** The model has no field
distinguishing *what the capability is* from *evidence that an agent has it*. That distinction is
currently carried only by convention (contract vs. `MaturityRecord`/`EvidenceRecord`). This is a
documentation-level gap, not a schema defect, until a consumer needs to distinguish them
programmatically.

**Status: `PARTIAL`.** Substrate: `SATISFIED`; content-derived identity: `ABSENT`.

### 5.2 Capability binding

**Artifacts.** `CapabilityFamily` / `CapabilityFamilyId` in
`src/investigation_world/foundry/capability_families.py`; consumers in
`src/investigation_world/foundry/cli.py` (lines 173–237), `src/investigation_world/foundry/training_product.py`
(line 71, `TrainingRecipe.capability_contract_id`), and
`src/investigation_world/foundry/training_corpus.py` (`capability_contract_id=` at
`generate_training_demonstration_set`).

**What is already satisfied.** The *family* binding is real and load-bearing: a
`CapabilityFamily` binds one contract to one capability domain with its own `source_surfaces` and
`task_families`, and the CLI refuses to export training artifacts whose dataset
`capability_contract_id` does not match the External Investigation contract
(`foundry/cli.py:226-227`). `foundry/companyworld.py:9-32` maps each CompanyWorld task family to
its capability tag set (`_FAMILY_CAPABILITIES`), propagated into `FoundryTaskMetadata.capability_tags`
(line 158). This is genuine capability-to-task binding at the *foundry* layer.

**Gap — the binding does not reach the operational episode.** Verified by direct search:
`CapabilityContract`, `capability_contract`, and `CapabilityFamily` are **not imported anywhere**
under `src/investigation_world/operational/` or `src/investigation_world/operational_world/`.
`TaskContract` (`src/investigation_world/operational/models.py:127`) is documented as a "public,
**capability-neutral** task contract" and carries no capability reference. The only
capability-ish field on an operational episode is an informal `metadata` entry
(`catalog.py:216` `{"legacy_capability_family": "external_investigation"}`, and
`metadata={"family": ...}` elsewhere in `catalog.py`).

Concretely: given an `OperationalEpisode`, there is no field that names the `CapabilityContract`
whose success/failure conditions the episode's oracle was built to evaluate. The chain edge
`CapabilityContract → OperationalWorld` is therefore a **documentation claim**, not a binding the
code enforces or can check. `InvestigationCapabilityPack` hardcodes
`"capability": "operational_procurement_investigation"` in its public manifest string
(`capability_pack.py:121`) rather than referencing a `CapabilityContract`.

**Classification.** This is an *ontology/schema* gap, not a missing runtime. The fix is a
declarative reference (capability identity + contract digest) on the world/episode or pack, plus
a validator that the oracle's targets/invariants are consistent with the contract's success
conditions. It must not become a runtime dependency: the episode remains capability-neutral at
execution time; the binding belongs in *identity and provenance*.

**Status: `PARTIAL`.** Foundry-layer binding `SATISFIED`; contract→world/episode binding `ABSENT`.

### 5.3 VeritasWorld / OperationalWorld

**Artifacts.** `CompiledOperationalWorld` and `OperationalWorldSpec` in
`src/investigation_world/operational_world/models.py` (lines 160, 244); compiler
`src/investigation_world/operational_world/compiler.py::OperationalWorldCompiler`; production
wrapper `src/investigation_world/operational_world/pipeline.py::OperationalWorldCompiler`;
validation `validation.py::validate_operational_world → WorldIntegrityReport`; capability packs
`capability_pack.py`; calibration `CalibrationProfile` (same module, lines 84–152) plus
`calibration.py`, `fusion.py`, `external_profiles.py`, `production.py`.

**The identity mapping holds.** `VeritasWorld ≈ OperationalWorld` is **sufficient**. The
canonical role — "the condition under which a capability is evaluated" — is fulfilled by:
`OperationalWorldSpec` (seed, region, industry, size band, simulation days, scenario types,
systems) fixing the condition; `CompiledOperationalWorld` holding entities, events, records and
private ground truth; and `CalibrationProfile` (with `state: bootstrap_prior|empirical|hybrid`
and `size_scope`) making the condition's realism explicit and auditable rather than asserted.

**Privacy is correctly implemented.** `CompiledOperationalWorld.public_payload()` strips
`scenario_types` from the spec with an inline rationale ("Scenario labels are evaluator-only …
would turn anomaly discovery into classification from leaked compiler configuration").
`capability_pack.py` validates forbidden private fields never appear in public payloads
(`_validate_pack`, fields `scenario_type`, `hidden_cause`, `hidden_error_id`,
`expected_resolution`) and rejects seed overlap between splits and OOD scenario leakage.

**Tests.** `tests/unit/test_operational_world_compiler.py` (determinism, reference integrity,
scenario-label non-leakage, all-families validity, public/private task separation);
`tests/unit/test_operational_world_production.py`; `tests/unit/test_operational_calibration_compatibility.py`;
`tests/unit/test_operational_realism.py`.

**Gap — calibration state is not capability-linked.** `CalibrationProfile.state` distinguishes
measured from bootstrap priors, which is excellent, but nothing ties a profile to the capability
contract it calibrates. This is the same binding gap as 5.2, one layer down.

**Do not create `VeritasWorld`.** No semantic requirement was found that is not met by
`CompiledOperationalWorld` + `OperationalWorldSpec` + `CalibrationProfile`.

**Status: `SATISFIED`.** (Binding-to-contract gap is recorded under 5.2.)

### 5.4 VeritasEpisode / OperationalEpisode

**Artifacts.** `OperationalEpisode` in `src/investigation_world/operational/models.py:147`, with
`TaskContract`, `PublicActionSpec`, `HiddenOracle`, `HiddenActionEffect`, `ActionEvent`,
`EpisodeSubmission`, `VerificationBreakdown`, `OperationalInvariant`, `StateAssertion`.

**The identity mapping holds.** `VeritasEpisode ≈ OperationalEpisode` is **sufficient**. The
canonical role — "one bounded evaluation instance" — is fulfilled exactly: `episode_id`,
`world_id`, a public `TaskContract`, agent-visible `records`, and a private `HiddenOracle`.

The public/private boundary is structural, not conventional:

- `TaskContract.available_actions` (`PublicActionSpec`: name, kind, system, description,
  parameter names, cost) is the entire agent-visible action surface.
- `HiddenOracle` (target_state, invariants, required/forbidden actions, action effects,
  consequence severity) is never serialized into agent view.
- `OperationalEpisode.validate_episode` is a real structural validator: task/oracle ID match,
  world/task ID match, unique action names, actions within `permitted_systems`, oracle
  constraints referencing only declared public actions, no required-and-forbidden contradictions,
  effect parameters declared on the public action, unique record IDs, oracle-required evidence
  present in records, unique invariant IDs.
- `public_payload()` emits task + records + metadata only — the oracle is excluded by
  construction.
- Portable projection: `src/investigation_world/portable_contract/compiler.py::
  compile_operational_episode` re-projects the same episode into `PortableOperationalContract`
  and calls `assert_operational_semantic_equivalence`, so the public/private split survives a
  round trip to a portable IR.

**Tests.** `tests/unit/test_operational_worlds.py` (`test_public_payload_does_not_expose_oracle`,
`test_action_result_does_not_leak_hidden_verifier_state`,
`test_forbidden_action_is_penalized_and_invariant_detected`, `test_financial_world_executes_and_verifies_ground_truth`);
`tests/portable_runtime/test_portable_runtime.py`; `tests/portability/test_portable_contract.py`.

**Gap — none requiring a new class.** The one thing `OperationalEpisode` deliberately lacks is a
capability reference, which is the 5.2 gap and does not require touching this protected class.

**Do not create `VeritasEpisode`.** `OperationalEpisode` was not modified, and no modification is
recommended.

**Status: `SATISFIED`.**

### 5.5 Agent execution

**Artifacts.** `OperationalRuntime` in `src/investigation_world/operational/runtime.py`;
`PortableOperationalRuntime` in `src/investigation_world/portable_runtime/runtime.py`;
`NativeOperationalRuntime` in `src/investigation_world/operational/native_runtime.py`.

**What is already satisfied.** `OperationalRuntime.act()` is the canonical execution seam. It
charges budget, resolves the declared effect, checks private preconditions
(`required_state`, `required_prior_actions`), applies hidden state mutations, emits the
system-observable result, and records an `ActionEvent` carrying `state_changes`,
`side_effects`, `forbidden`, `consequence_severity`, `effect_applied`, `blocked`,
`blocked_reason`. Its docstring states the boundary precisely: verifier-only fields remain in the
harness trace, and stateful precondition failures are observable only through the simulated
system's rejection response. `search`/`search_all`/`open_record` charge cost and are scoped to
`permitted_systems`.

**Budgets are harness-measured, not agent-reported** — `InvestigationBudget`
(`src/investigation_world/core/models.py`) is charged by the runtime, which is exactly the
`selective_agency` contract invariant "resource measurements come from the harness rather than
agent self-report".

**Tests.** `tests/unit/test_operational_worlds.py` (action results, forbidden-action penalty,
facade builds runtimes for every domain); `tests/unit/test_native_artifacts.py`.

**Gap — execution is not recorded into `TrajectoryV2` by the runtime itself.** `OperationalRuntime`
produces `ActionEvent`s and a `VerificationBreakdown`, but it does not emit a `TrajectoryV2`.
Construction happens elsewhere, ad hoc: `src/investigation_world/trajectory/adapter.py` adapts a
legacy `RolloutTrace`; `src/investigation_world/gold10/replay.py::traceable_experience`
hand-builds `TrajectoryEvent`s for Gold-10 submissions; the reverification engine
(`src/investigation_world/trajectory/reverify/engine.py`) later *re-derives* the action sequence
from recorded trajectory events by decoding `payload["method"] == "act"` calls. So the
runtime→trajectory step exists in repository code but is not a single owned function.

**Classification.** Schema and semantics are `SATISFIED` (`TrajectoryV2` + `TrajectoryEvent` can
represent the execution exactly, and reverification proves it). The *owned producer* is
`PARTIAL`: there is no single canonical "record this operational episode as a trajectory" adapter.

**Status: `PARTIAL`.**

### 5.6 Execution + effects

**Artifacts.** `ActionEvent` (`state_changes`, `side_effects`, `cost`, `effect_applied`,
`blocked`) and `trace()` in `src/investigation_world/operational/runtime.py`;
`TraceEvent`/`RolloutTrace`/`StateSnapshot`/`CounterfactualBranch` in
`src/investigation_world/foundry/models.py`; `TrajectoryEvent`/`StateDigest`/`UsageTotals`/
`ProviderCallSummary`/`ResourceCallSummary` in `src/investigation_world/trajectory/models.py`;
`PersistentOperationalSubstrate` and `OperationalStateEvent`/`OperationalSnapshot` in
`src/investigation_world/operational/substrate.py`.

**What is already satisfied.** Effects are a coherent evidence layer:

- replayable state chain — `reverify/engine.py::_validate_state_chain` reconstructs the final
  state by replaying `event.state_changes` in order and compares digests
  (`INITIAL_STATE_DIGEST_MISMATCH`, `REPLAYED_FINAL_STATE_MISMATCH`);
- cost accounting — per-action `cost`, `UsageTotals`, budget resources;
- termination — `TerminationRecord` with `reason`/`terminated`/`truncated`;
- counterfactuals — `CounterfactualBranch` points at a snapshot hash plus an alternate action;
- provider/resource calls are first-class, so effects are attributable to their producer.

**Determinism is a verified property, not a claim.** `test_operational_world_is_deterministic`
and `test_production_distribution_is_deterministic_and_parameterized`; the portable contract pins
the verifier by git blob SHA-1 (`SOURCE_VERIFIER_BLOB`, `PortableEvaluatorBinding`) and rejects
nondeterministic evaluator contracts at reverification (`NONDETERMINISTIC_EVALUATOR_CONTRACT`).

**Gap — none requiring a new abstraction.** The audit explicitly looked for a reason to add a
trajectory/effects abstraction and found none. `TrajectoryV2` is the execution+effects layer.

**Status: `NOT SEPARATELY REQUIRED`** as a new abstraction; the underlying capability is
`SATISFIED`.

### 5.7 Independent verification

**Artifacts.**

- Operational worlds: `src/investigation_world/operational/verifier.py::
  verify_operational_episode` — seven dimensions (`VerificationDimension` in
  `src/investigation_world/operational/models.py`: outcome, state, constraints, side_effects,
  process, efficiency, evidence), weighted 0.30/0.20/0.15/0.10/0.10/0.05/0.10 into `overall_reward`
  (efficiency is 0.05, not 0.10).
- Legacy investigation worlds: `src/investigation_world/verifier/aggregate.py::verify` —
  identity, relationships, temporal, evidence support, provenance, abstention, calibration,
  efficiency.
- Offline re-verification: `src/investigation_world/trajectory/reverify/` (`engine.py`,
  `operational.py`, `batch.py`, `models.py`).
- Portable verifier binding: `PortableEvaluatorBinding`, `AuthorizedVerifierRegistry`,
  `current_operational_verifier_binding()` in `reverify/operational.py`.

**What is independently verified.** Final state against `oracle.target_state`; invariants both
`scope="final"` and trajectory-wide `scope="always"` (replayed step by step); required action
counts and required ordering (`_ordered_subsequence`, with a 0.5 process penalty);
forbidden actions; consequence severity aggregated into a side-effect score; required evidence
IDs against the submission; budget/tool-call efficiency; and consistency of the agent's
`claimed_state` — "Claims never override ground truth. Incorrect claimed state reduces outcome
trust" (a `0.2` per-key outcome penalty).

**What remains agent-reported, by design.** `EpisodeSubmission.conclusion`, `claimed_state`,
`evidence_ids`, and `confidence` are agent assertions; verification converts them into scores and
records the mismatches. Nothing in the reward trusts them unverified.

**Where private state stays private.** `HiddenOracle` is never in `public_payload()` at any of
three layers (`OperationalEpisode`, `CompiledOperationalWorld`, `InvestigationCapabilityPack`).
The offline verifier is *statically* authorized: `OperationalVerifierBinding.__post_init__`
rejects any entrypoint, semantics id, or source blob other than the pinned ones;
`AuthorizedVerifierRegistry.resolve` is an exact-match registry ("Unregistered verifier versions
are not treated as equivalent"); `OperationalVerifierBinding.verify` re-hashes the verifier source
file at call time and refuses on mismatch. Reverification fails closed rather than fabricating a
score: `test_missing_private_replay_evidence_is_not_reverifiable_and_has_no_score`,
`test_batch_preserves_not_reverifiable_without_fabricating_a_score`.

**Verification differs from execution, enforced.** Execution returns only the observable result;
the verifier reads oracle truth plus the harness trace. `PortableOperationalRuntime.verify`
documents "native verification remains the only reward authority".

**Can verifier-backed evidence feed MachineExperience?** Yes, and this is already wired for the
Gold-10 path: `gold10/replay.py::traceable_experience` embeds `EvaluationRecord(verifier=…,
component_scores=score.component_scores, reward=score.reward)` into the trajectory and stamps
`maturity=E0_TRACEABLE`. For operational worlds the same shape is available but the producer is
the 5.5 gap.

**Tests.** `tests/trajectory/reverify/test_reverification.py` (idempotent append, tamper
detection `test_event_sequence_tampering_is_detected_even_after_new_id_is_computed`, exact
verifier-version binding, buyer-safe projection excludes private replay truth, registry rejects
arbitrary callable bindings); `tests/unit/test_verifier_qualification_suite.py`.

**Status: `SATISFIED`.** The oracle boundary was not weakened and is not recommended for change.

### 5.8 MachineExperience

**Artifacts.** `src/investigation_world/experience/models.py` (`MachineExperience`,
`ExperienceMaturity`, `ExperienceReadiness`, `ReadinessAssessment`, `ReadinessStatus`,
`ExperienceInitialConditions`, `EpistemicSnapshot`, `HypothesisState`, `BeliefRevision`,
`ExperienceSpan`, `StructuralRecord`, `ExperienceDiagnostics`, `FailureMechanism`,
`ExperienceSequence`); `src/investigation_world/experience/adapter.py::
machine_experience_from_trajectory`; `src/investigation_world/gold10/replay.py::traceable_experience`;
`docs/experience/machine-experience.md`.

**What it represents.** One canonical unit of learning-grade evidence *wrapping* a trajectory. It
is explicitly not a second runtime: the adapter's docstring says "Wrap one canonical trajectory
without duplicating execution semantics", and `docs/experience/machine-experience.md` states
"`MachineExperience` wraps that trajectory with learning-readiness and structured analysis
annotations; it does not implement a second runtime or recorder."

**Identity.** Content-derived and layered: `TrajectoryV2.trajectory_id` ←
`canonical_hash(identity_payload)` over world/task/model/agent/harness/runtime/verifier/reset/
initial-state/events/calls/references/usage/evaluation/termination/final-state/failure/
capability_tags; `MachineExperience.experience_id` ← `EXP-<hash of schema_version +
trajectory_id>`. Because annotations are excluded from both identity payloads, "readiness,
diagnostics and downstream annotations can accumulate without changing the identity of the
underlying experience" — a verified property
(`test_experience_identity_is_stable_across_diagnostic_annotations`).

**Relation to `TrajectoryV2`.** Containment, not duplication: `trajectory: TrajectoryV2` is a
required field, and `MachineExperience.model_validator` revalidates the nested trajectory and
readiness rather than trusting unvalidated input.

**Verifier-backed experience.** Supported: `original_evaluation: EvaluationRecord` lives on the
trajectory; `ReverificationRecord` can be appended via `TrajectoryV2.with_reverification` without
mutating the original evaluation; `MaturityRecord`-style evidence references can be carried in
`ExperienceReference` with `visibility`.

**Fail-closed maturity gate.** `_REQUIRED_READINESS_BY_MATURITY` makes E1 require
`reverification_ready`, E2 add `failure_analysis_ready`, E3 add counterfactual + causal, … E7
require all nine. `validate_experience` rejects any maturity above E0 whose required readiness is
not `PASS`, and `PASS` requires at least one evidence reference that is not more private than the
assessment. Tests: `test_experience_maturity_fails_closed_on_unknown_readiness`,
`test_pass_readiness_requires_visible_evidence`,
`test_counterfactual_maturity_requires_causal_analysis_readiness`.

**Privacy.** `public_payload()` / `buyer_safe_payload()` walk the object graph and drop any node
whose `VisibilityClass` rank exceeds the requested level, plus `private_metadata`/`private_payload`
buckets — so experience serialization "never widens the nested trajectory visibility boundary"
(`test_public_projection_never_widens_trajectory_visibility`).

**Span/annotation bounds.** Spans nest with containment and cannot exceed the trajectory event
range; epistemic snapshots, belief revisions and structural records are all step-bounded
(`_validate_step_boundaries`, `_validate_spans` with cycle detection,
`_validate_unique_annotation_ids`).

**Gap — annotations have no producer.** `MachineExperience` accepts epistemic snapshots, spans,
structural records and diagnostics, but nothing in `src/` constructs them outside
`gold10/replay.py` (which builds one epistemic snapshot per case). `ExperienceDiagnostics` has
`first_divergence_reference`, `recovery_point_references`, `capability_gap_references` — all
unpopulated by any non-test code. This is consistent with `docs/experience/machine-experience.md`
("Wave 1 defines these contracts only; clustering and causal attribution belong to later
diagnostic work") and is correctly deferred, not missing-by-accident.

**MachineExperience vs. future aggregation.** `MachineExperience` is per-trajectory.
`ExperienceSequence` is the existing ordered aggregation primitive and already reserves
`transfer_test_experience_ids` — the natural carrier for a transfer comparison's two arms. It is
*not* an experience-aggregation engine, and the audit does not treat that as a gap in
`MachineExperience`.

**Do not create another experience class.** None is needed.

**Status: `SATISFIED`** as the canonical record. Producers for higher-maturity annotations:
deferred (§9), not a Phase 2 deliverable.

### 5.9 Failure evidence

**Artifacts.** `FailureFamily` (`src/investigation_world/experience/models.py:472`);
`FailureMechanism` (21-value mechanism taxonomy); `FailureCategory`
(`src/investigation_world/trajectory/models.py:32`, 9 values); `ExperienceDiagnostics`;
`BehavioralFingerprint` (`src/investigation_world/observatory/models.py:132`);
`diagnose_failure` (`src/investigation_world/observatory/trajectory_diagnostics/engine.py:87`).

**What exists.** The contracts are complete and identity-bearing (`FAILFAM-<hash>`,
`CAPGAP-<hash>`). The taxonomy is layered as `docs/experience/machine-experience.md` describes:
`FailureCategory` remains the origin taxonomy; `FailureMechanism` is the root-cause mechanism
taxonomy. `diagnose_failure` produces a real `FailureAttribution` with a complete, normalized
probability distribution over `FailureCategory`, and `test_*` in
`tests/observatory/trajectory_diagnostics/` cover attribution and comparisons.

**Gap — no producer for `FailureFamily`.** Direct search confirms `FailureFamily(` and
`CapabilityGap(` appear only in `experience/models.py` (definitions) and
`tests/experience/test_machine_experience.py`. No module in `src/` clusters experiences into
families. `docs/experience/machine-experience.md` explicitly defers "automatic failure clustering",
so this is **deferred research**, not an accidental omission.

**Absence-of-behavior.** Phase 1 §2.1 states failure evidence "also includes *absence of
behavior*: an expected action never occurring is failure evidence, not a zero-length success."
The verifier does implement this: `missing_required_actions` in `VerificationBreakdown` and the
process score count required actions that never occurred. So the semantic is present at the
verification layer; what is absent is its propagation into `FailureFamily` (no producer).

**Status: `PARTIAL`** — contracts `SATISFIED`, producers `ABSENT` and deferred.

### 5.10 CapabilityGap

**Artifacts.** `CapabilityGap` (`src/investigation_world/experience/models.py:515`);
`CapabilityGraph` / `CapabilityAttribution` / `attribute_drift`
(`src/investigation_world/observatory/capability_graph.py`) — a distinct, protected object.

**What `CapabilityGap` is.** A *descriptive* aggregate: `capability`, `supporting_failure_family_ids`,
`frequency`, `severity`, `environment_ids`, `prerequisite_candidates`,
`missing_procedure_candidates`, `likely_abstraction_deficit`, `proposed_interventions`. Fields are
canonicalized to sorted sets; `gap_id` is content-derived over capability + supporting families +
environments.

**It is diagnostic, not causal.** The repository says so twice, in the two places a reader would
look:

- `CapabilityAttributionReport.caveat` (capability_graph.py): "Graph attribution is diagnostic, not
  causal proof. It identifies regressed observed dimensions and prerequisite structure that are
  consistent with the measured drift."
- Phase 1 §10: "`CapabilityGap` is used as a *descriptive* aggregate over failure families … It is
  not a causal diagnostic."

Nothing in the model expresses or licenses "this gap causes that failure". `frequency` and
`severity` are observed statistics; `prerequisite_candidates` / `missing_procedure_candidates` /
`proposed_interventions` are candidate sets, not validated mechanisms. `attribute_drift`'s
propagation over prerequisite edges is explicitly scored as `diagnostic_score` with a caveat.

**Gap — no producer, and no aggregation.** As with `FailureFamily`, no non-test code constructs a
`CapabilityGap`. `docs/experience/learning-efficiency.md` sketches the intended loop
("evaluate → identify failures → build FailureFamily records → derive CapabilityGap candidates →
select representative experience → …") and immediately qualifies it: "Selection is a hypothesis,
not an assumption."

**`CapabilityGapReport`.** Not needed as a new object. If later phases need a multi-gap summary,
`CapabilityGraph` already aggregates capability structure and drift attribution, and
`AggregateDriftReport` already aggregates across runs. A report object would duplicate both.

**Status: `PARTIAL`** — contract `SATISFIED` (as descriptive), producer `ABSENT` and deferred.
**No causal semantics are asserted or recommended by this audit.**

### 5.11 Qualification

**Artifacts.**

- Environment maturity: `src/investigation_world/qualification/maturity.py` —
  `EnvironmentMaturity` (DRAFT → EXECUTABLE → VERIFIER_VALIDATED → SCIENTIFICALLY_QUALIFIED →
  FRONTIER_QUALIFIED → TRAINING_VALIDATED → COMMERCIAL_RELEASE), `GateOutcome` (PASS/FAIL/UNKNOWN),
  `MaturityPolicy` (+ `DEFAULT_MATURITY_POLICY`), `MaturityGateEvidence`, `MaturityRecord`,
  `MaturityHistory`, `assess_environment_maturity`.
- Qualification protocol: `src/investigation_world/qualification/protocol.py::qualify_candidate`
  over `QualificationCandidate` / `QualificationThresholds` / `PolicyEvaluation` / `QualificationReport`
  (`models.py`), with near-duplicate protection (`cluster_split.py`, `source_disjoint.py`).
- Verifier qualification: `qualification/verifier_suite.py::qualify_verifier`,
  `verifier_maturity_evidence`.
- Environment quality scorecard: `qualification/quality_scorecard.py` over `EvidenceRecord`.
- Shared evidence envelope: `src/investigation_world/evidence/models.py::EvidenceRecord`,
  `docs/evidence/shared-evidence-contract.md`.
- Catalog: `src/investigation_world/catalog/models.py` binds `MaturityRecord` into
  `CatalogClassification`.

**What qualification means operationally.** Exactly what Phase 1 §4 requires, and it is
mechanically enforced rather than asserted:

1. *Criteria stated before evaluation* — `MaturityPolicy.requirements` is a frozen, content-hashed
   policy (`MPOL-…`) that must define every maturity state; `DRAFT` must require nothing.
2. *Identified verifier and conditions* — `EnvironmentIdentity` / `VerifierIdentity` carry
   `content_sha256`; `MaturityGateEvidence` binds `environment_content_sha256` and
   `verifier_content_sha256` and rejects evidence belonging to a different version.
3. *Stated criterion with a policy* — `MaturityRecord.required_evidence` must equal
   `policy.required_through(target_status)`, or the record fails to construct.
4. *Verifier-produced evidence, not agent report* — `EvidenceRecord` deliberately excludes raw
   evaluator truth: "Raw evaluator truth is intentionally not a field. Evidence points to opaque,
   hashed artifacts."
5. *PASS/FAIL/UNKNOWN semantics* — `GateOutcome`; `PASS` and `FAIL` require content-addressed
   evidence (`evidence_id` + `content_sha256` supplied together).
6. *Population identified* — `qualify_candidate` requires a private-test panel and forces every
   policy class to run on the exact same private scenario set; `test_policy_panel_must_match_private_test_exactly`.

**The status cannot be claimed above its evidence.** `MaturityRecord.validate_record` derives the
achieved status by walking `MATURITY_ORDER` and comparing against `required_through`, then rejects
any mismatch ("claimed status … does not match evidence-derived status"). Gates must be fully
classified into disjoint PASS/FAIL/UNKNOWN sets. `assess_environment_maturity` computes the same
result. Tests: `test_missing_evidence_is_unknown_and_never_passes`,
`test_all_lower_transition_gates_are_required`, `test_transition_reaches_only_the_highest_contiguous_passed_stage`,
`test_record_rejects_a_status_claim_above_its_evidence`, `test_failed_evidence_identity_changes_the_qualification_identity`.

**How qualification differs from ordinary evaluation.** Ordinary evaluation produces a reward;
qualification produces a *policy-bound, content-addressed, append-only* record whose status is
derived, not asserted. `MaturityHistory` enforces contiguous lineage
(`previous_record_id`/`previous_status`), so requalification cannot silently rewrite history.

**Gap — qualification is environment-scoped, not agent-capability-scoped.** `MaturityRecord`
qualifies an *environment/verifier pair*. There is no analogous record that a *capability contract*
was met by an *agent* under a stated panel. `QualificationReport` is close (candidate + policies +
thresholds + private panel) but its candidate is a scenario distribution, not a capability contract
bound to an agent identity. The training-value tooling (§5.12) measures agent-side improvement but
emits an experiment report, not a qualification record.

**Gap — the `held_out_training_improvement` gate has no automated producer.** It is a first-class
gate in `DEFAULT_MATURITY_POLICY` (TRAINING_VALIDATED), and `tools/run_training_value_v3.py`
produces exactly the evidence shape it needs (frozen panel hash, paired deltas, seed variance).
But nothing converts that report into a `MaturityGateEvidence`. This is a small adapter, not a
new framework — and training-value experiment code is protected, so the adapter must live outside
it and consume its outputs.

**Do not create a second qualification framework.** `MaturityRecord` under `MaturityPolicy` is it.

**Status: `PARTIAL`** — environment qualification `SATISFIED`; capability/agent-scoped
qualification `ABSENT` as a record type; `held_out_training_improvement` evidence adapter `ABSENT`.

### 5.12 TransferEvaluation

Phase 1 §2.1 defined `TransferEvaluation` as **normative semantics only** — "the comparison of
capability behavior across two explicitly identified conditions". The audit asked: does existing
infrastructure already express that, so that no runtime class is needed?

**Existing substrates that cover parts.**

| Substrate | What it compares | Why it is not `TransferEvaluation` |
|---|---|---|
| `compare_runs` (`observatory/analysis.py`) | two `CapabilityRun`s on the same longitudinal cell, same runtime and taskset version | Longitudinal drift of one condition, not two identified conditions |
| `compare_aggregates` (`observatory/aggregation.py`) | two `AggregatedCapabilityProfile`s on matched sample keys, paired deltas with `critical_95` | Cohort drift; matched keys, not two named conditions under one contract |
| `attribute_drift` (`observatory/capability_graph.py`) | drift over a capability prerequisite graph | Diagnostic attribution, explicitly non-causal |
| `tools/run_training_value_v3.py::_paired_summary` | frozen held-out panel before/after training, with `panel_id`, mean/median/stddev/SE, ci95, improved/regressed counts | Two *temporal* arms of one training experiment, not two conditions; and it is training code |
| `ExperienceSequence.transfer_test_experience_ids` | reserves the transfer-test arm of an experience sequence | A field awaiting a producer; no comparison logic |
| `CapabilityContract.transfer_targets` | declares intended target conditions | Declarative intent, not an evaluation |

**Conclusion.** No existing artifact compares capability behavior across two *explicitly
identified conditions under one contract and one verifier*, which is Phase 1 §6's requirement.
`compare_runs`/`compare_aggregates` compare two *runs*; `run_training_value_v3` compares two
*times* under one condition. The semantic distinction is real: a transfer evaluation's two arms
differ in *condition* (world/episode distribution and version identities), not in time or run id.

**But the gap is smaller than it looks.** Every ingredient exists:

- condition identity — `WorldIdentity` + `TaskIdentity` (+ `portable_operational_contract`
  `ArtifactIdentity`) already make a condition reproducible and hashable;
- contract identity — `CapabilityContract` (needs 5.1 Gap A to be content-addressed);
- same-verifier enforcement — `AuthorizedVerifierRegistry` exact-match resolution and
  `TrajectoryV2.original_evaluation.verifier` binding;
- comparison statistics — `_paired_delta` / `critical_95` / `MetricEstimate` in
  `observatory/aggregation.py`, already paired and uncertainty-aware;
- the two arms — `ExperienceSequence.experience_ids` + `transfer_test_experience_ids`.

So the minimum later change is a **thin reporting/comparison object over existing identities and
existing statistics**, not a runtime class and not a new evaluation engine. It should reuse
`_paired_delta`/`critical_95` rather than reimplement statistics, and it must record both
conditions' identities, the contract digest, and the verifier identity, so that Phase 1 §6's four
conditions are checkable from the artifact alone.

**Classification.** `TransferEvaluation` as a canonical semantic concept: `PARTIAL` (ingredients
`SATISFIED`, no assembled object). As a runtime class: **not required and not recommended** — the
canonical concept is satisfied by a comparison/report object over `TrajectoryV2`/`MachineExperience`
identities.

**Status: `PARTIAL`.**

### 5.13 Held-out transfer

**Normative reference.** `docs/experience/held-out-transfer.md` §5 (held-out evaluation), §6
(transfer), §7 (existence ≠ improvement), §8 (OOD).

**What the repository already enforces.** Verified by reading the validators, not just the docs:

- `InvestigationPackSpec` (`operational_world/capability_pack.py`): exactly five `PackSplit`s
  (`train`, `dev`, `public_eval`, `private_eval`, `ood_eval`), weights summing to 1, non-empty
  train and OOD scenario pools, and **`ood_scenarios` disjoint from `train_scenarios`**.
- `InvestigationCapabilityPackBuilder._validate_pack`: rejects world-seed overlap between any two
  splits; rejects OOD scenario leakage into in-distribution splits; scans public payloads for
  forbidden private fields; requires public/oracle episode-ID sets to match per split.
- `operational/deep_distribution.py` / `distribution.py::validate_operational_distribution`:
  raises on `"train and held-out task IDs overlap"`, on oracle leakage (`"oracle"`,
  `"target_state"`, `"action_effects"` appearing in public payloads), on split labels leaking
  through task IDs, and on missing OOD surface profiles / weak adversarial pressure.
- `projectworld/distribution.py`: raises `"OOD split does not contain held-out project archetypes"`.
- `foundry/training_corpus.py`: raises `"held-out trajectory entered training demonstration corpus"`.
- Identity-level freezing: `_panel_hash` (`tools/run_training_value_v3.py`) hashes the sorted
  episode-ID set into `PANEL-…`, and `_paired_summary` refuses mismatched before/after panels.

**Tests.** `tests/unit/test_operational_worlds.py::test_production_distribution_has_disjoint_splits_and_all_domains`,
`test_public_distribution_hides_split_seed_family_and_oracle`,
`test_adversarial_distribution_adds_conflict_and_pressure`;
`tests/unit/test_training_corpus_split_isolation.py`; `tests/unit/test_projectworld_distribution.py`.

**Gap — disjointness is enforced per-distribution, not across the whole candidate lineage.** Each
validator protects one bundle. Nothing answers Phase 1 §3's question — "was this population used as
development evidence?" — *across* artifacts: no index that maps an episode/world identity to every
development artifact that consumed it, and no check that a held-out panel for a qualification claim
is disjoint from the development sets of the specific candidate lineage. `FoundryTaskMetadata`
records split/seed/tags/mutation_lineage and `RolloutTrace` binds versions, so the *identities* to
answer the question exist; the *cross-artifact query* does not.

**Gap — the distinction in §7 is enforced by tooling, not by a schema.**
`run_training_value_v3` does produce a legitimate improvement measurement (frozen panel, pre-stated
paired comparison, seed variance, ci95). But `ExperienceSequence.transfer_test_experience_ids` can
be populated without any baseline or comparison, and nothing in the schema distinguishes "transfer
evidence exists" from "transfer improvement was measured". A consumer reading a populated
`transfer_test_experience_ids` cannot tell which of the two it is. That distinction currently lives
only in `docs/experience/held-out-transfer.md` §7 and in `run_training_value_v3`'s discipline.

**This audit states the distinction as it must stand:** the existence of a held-out evaluation, even
a favorable one, is evidence of *existence* only. Improvement is a claim about a *difference* against
a defined, pre-stated baseline with reported uncertainty. No finding in this document is an
improvement claim, and the repository's release notes (e.g. `docs/releases/0.9.1.md`) are the only
place such claims are made, with their own evidence.

**Status: `PARTIAL`** — per-distribution held-out enforcement `SATISFIED`; lineage-wide
development-evidence index `ABSENT`; schema-level existence-vs-improvement distinction `ABSENT`.

## 6. Cross-cutting semantic boundaries

### 6.1 Ontology vs implementation

`VeritasWorld`, `VeritasEpisode`, and `TransferEvaluation` are **semantic roles**. `OperationalWorld`,
`OperationalEpisode`, and a future comparison report are **implementations**. The audit found no case
where a canonical role required a new runtime class; every role maps onto an existing object or onto
a thin reporting object over existing identities (§5.12). The discipline that follows: when a
canonical term appears in later phases, the first question is "which existing object plays this
role?", not "what new class do we build?".

### 6.2 Execution vs verification

Structurally separated and deliberately asymmetric. Execution (`OperationalRuntime.act`) returns only
the system-observable projection; verification (`verify_operational_episode`) reads oracle truth plus
the harness trace. The agent cannot see `consequence_severity`, `forbidden`, or target state; the
verifier cannot be influenced by the agent's claims (`claimed_state` inconsistency *reduces* outcome
trust). The offline verifier is blob-pinned and registry-bound, so even a verifier version bump is a
new identity, not an equivalent. **This boundary is correct and must not be weakened.**

### 6.3 Experience vs causal learning

`MachineExperience` is a *record*; learning is a *program*. `ExperienceReadiness` makes the
separation enforceable: `E2_DIAGNOSTIC` requires failure-analysis readiness, `E3_COUNTERFACTUAL`
requires counterfactual *and* causal-analysis readiness, and the model rejects unsupported claims.
So the schema already prevents "we have experience" from silently meaning "we have learning". The
deferred items in `docs/experience/machine-experience.md` (counterfactual generation, procedure
induction, curriculum mining, training bundle construction, continual-learning loops) are the
learning program and remain deferred.

### 6.4 Failure evidence vs causal diagnosis

`FailureFamily` and `CapabilityGap` record *what fails, how often, how severely, where*. Causal
diagnosis is a separate claim requiring separate evidence. The repository says this in
`CapabilityAttributionReport.caveat` and Phase 1 §10, and the schema enforces nothing causal:
`prerequisite_candidates` and `proposed_interventions` are candidate sets, `attribute_drift`'s
propagation is a `diagnostic_score`, and `diagnose_failure` outputs calibrated *category
probabilities* with an `ambiguous` flag (UNKNOWN attribution must remain ambiguous). **This audit
asserts no causal capability-gap semantics.**

### 6.5 Held-out evaluation vs transfer improvement

Stated in §5.13. Held-out is a *provenance property of a population with respect to a candidate
lineage*; improvement is a *quantified difference against a pre-stated baseline*. Neither implies the
other. The repository enforces the first in per-distribution validators; it does not yet enforce the
second at the schema level. This is the single most load-bearing boundary in the chain, because it
is the one that fails silently in the favorable direction.

### 6.6 OOD vs held-out

Independent, per Phase 1 §9. `DistributionSplit` (TRAIN / IID_TEST / OOD / ADVERSARIAL) keeps them
distinct as named splits, and `InvestigationPackSpec` defines OOD as held-out scenario families with
disjoint world seeds. A held-out split drawn from the development distribution is held-out and
in-distribution; a shifted population previously tuned on is OOD and not held-out. No code path
conflates them, and `test_public_distribution_hides_split_seed_family_and_oracle` pins the
separation.

## 7. Gap inventory

| ID | Area | Status | Existing substrate | Actual gap | Proposed later action | Dependency |
|----|------|--------|--------------------|------------|-----------------------|------------|
| G-01 | CapabilityContract identity | PARTIAL | `foundry/models.py::CapabilityContract` | No content-derived identity/digest; capability identity is a bare string in every downstream reference | Add a `model_validator` + digest (`CCONTRACT-…`) mirroring `MaturityPolicy`/`CapabilityGraph` | None; schema-only, additive |
| G-02 | Contract → world/episode binding | PARTIAL | `CapabilityFamily`, `_FAMILY_CAPABILITIES`, `FoundryTaskMetadata.capability_tags` | No capability reference on `OperationalEpisode`/`OperationalWorldSpec`/pack; the chain edge is documentation-only | Add declarative capability identity (+ contract digest) to world/episode metadata and validate consistency with oracle targets/invariants | G-01; touches protected `operational/**` and `operational_world/**` — changes must be additive metadata + validators, not runtime behavior |
| G-03 | Runtime → trajectory producer | PARTIAL | `OperationalRuntime`, `trajectory/adapter.py`, `reverify/engine.py` | No single owned function recording an operational episode as a `TrajectoryV2`; producers are ad hoc | Add a canonical operational-episode→`TrajectoryV2` adapter alongside the existing `RolloutTrace` adapter | Touches `trajectory/` (not protected); must reuse `TrajectoryEvent` shapes already decoded by `reverify/engine.py` |
| G-04 | MachineExperience annotation producers | SATISFIED (deferred work) | `MachineExperience` accepts spans, snapshots, structural records, diagnostics | No non-test producer outside `gold10/replay.py` | Deferred — per `docs/experience/machine-experience.md` "Wave 1 defines these contracts only" | Depends on failure clustering (G-05) |
| G-05 | FailureFamily producer | PARTIAL | `FailureFamily`, `FailureMechanism`, `diagnose_failure` | No clustering into families | Deferred research — explicitly deferred in `machine-experience.md` and `learning-efficiency.md` | G-04; no causal semantics |
| G-06 | CapabilityGap producer | PARTIAL | `CapabilityGap` (descriptive), `CapabilityGraph` (protected, separate) | No producer; no aggregation | Deferred research; a `CapabilityGapReport` is **not** needed — `CapabilityGraph` + `AggregateDriftReport` already cover multi-gap summaries | G-05 |
| G-07 | Capability/agent-scoped qualification | PARTIAL | `MaturityRecord`/`MaturityPolicy`, `QualificationReport`, `EvidenceRecord` | No qualification record binding a capability contract to an agent identity under a stated panel | Later phase: extend the maturity pattern to capability-at-agent, reusing `MaturityGateEvidence` semantics | G-01, G-02; must not duplicate `qualification/**` |
| G-08 | `held_out_training_improvement` evidence adapter | PARTIAL | `DEFAULT_MATURITY_POLICY` gate; `tools/run_training_value_v3.py` produces matching evidence | Nothing converts a training-value report into `MaturityGateEvidence` | Small adapter consuming the report's outputs; must live outside protected training code | G-07; protected surface: training experiment code (consume only) |
| G-09 | TransferEvaluation assemblage | PARTIAL | `compare_runs`, `compare_aggregates`, `ExperienceSequence.transfer_test_experience_ids`, `_paired_delta`/`critical_95`, `CapabilityContract.transfer_targets` | No object comparing two *identified conditions* under one contract and one verifier; `transfer_test_experience_ids` has no producer | Thin comparison/report object over existing identities and statistics; **not** a runtime class, **not** a new evaluation engine | G-01, G-03; reuse `observatory/aggregation.py` statistics |
| G-10 | Lineage-wide development-evidence index | ABSENT | `FoundryTaskMetadata`, `RolloutTrace`, `_panel_hash`, per-distribution validators | No cross-artifact query: "was this episode/world identity consumed by any development artifact of this candidate lineage?" | Later phase: an index over existing identities (no new identity scheme) | G-02, G-03; privacy: must not expose sealed/private rows |
| G-11 | Existence-vs-improvement at schema level | ABSENT | Phase 1 §7 (normative); `run_training_value_v3` discipline | Nothing in a schema distinguishes transfer evidence from measured transfer improvement | Add the distinction to the G-09 object: baseline identity, pre-stated comparison, uncertainty fields, and the baseline's own development status | G-09; must not create a second statistics path |
| G-12 | Calibration↔capability linkage | PARTIAL | `CalibrationProfile.state`/`size_scope` | No link from a profile to the capability contract it calibrates | Documentation or a reference field; smaller than G-02 | G-01 |
| G-13 | VeritasWorld / VeritasEpisode as classes | NOT SEPARATELY REQUIRED | `CompiledOperationalWorld`+`OperationalWorldSpec`+`CalibrationProfile`; `OperationalEpisode` | None | **No action.** Do not create either class | — |
| G-14 | Second trajectory/effects abstraction | NOT SEPARATELY REQUIRED | `TrajectoryV2`, `ActionEvent`, `PersistentOperationalSubstrate`, `CounterfactualBranch` | None | **No action.** | — |
| G-15 | Second experience class | NOT SEPARATELY REQUIRED | `MachineExperience` + `machine_experience_from_trajectory` | None | **No action.** | — |
| G-16 | Second qualification framework | NOT SEPARATELY REQUIRED | `MaturityRecord` under `MaturityPolicy` + `EvidenceRecord` | None | **No action.** | — |

## 8. What does NOT need implementation

Recorded explicitly, because each of these is a plausible-looking gap that is not one.

1. **`VeritasWorld`.** `CompiledOperationalWorld` + `OperationalWorldSpec` + `CalibrationProfile`
   satisfy the canonical role: the condition under which a capability is evaluated, with realism
   state made explicit and scenario truth kept private.
2. **`VeritasEpisode`.** `OperationalEpisode` is exactly one bounded evaluation instance with a
   structural public/private boundary and a portable round-trip projection.
3. **A second trajectory or execution/effects abstraction.** `TrajectoryV2` + `ActionEvent` +
   `StateDigest` + `PersistentOperationalSubstrate` + `CounterfactualBranch` already provide
   replayable state chains, cost accounting, termination, provider/resource attribution, and
   counterfactuals — and reverification proves the chain replays.
4. **A second experience class.** `MachineExperience` wraps `TrajectoryV2` without duplicating
   execution semantics, has content-derived layered identity, a fail-closed maturity gate, and
   visibility-classified serialization.
5. **A second qualification framework.** `MaturityRecord` under content-hashed `MaturityPolicy`
   with `GateOutcome` PASS/FAIL/UNKNOWN and content-addressed evidence already implements
   pre-stated criteria, version binding, derived status, and append-only history.
6. **A `CapabilityGapReport`.** `CapabilityGraph` + `AggregateDriftReport` + `CapabilityAttributionReport`
   already cover capability structure, cross-run aggregation, and drift attribution with an explicit
   non-causal caveat.
7. **A transfer evaluation *engine*.** The comparison semantics exist (`_paired_delta`,
   `critical_95`, matched-sample comparison); what is missing is a thin object that records the two
   conditions, the contract, and the verifier (§5.12).
8. **Held-out separation mechanism.** Five independent validators already enforce identity-level
   disjointness, OOD archetype distinctness, private-field non-leakage, and panel freezing.
9. **A new privacy mechanism.** Visibility-classified serialization at three layers
   (`TrajectoryV2`, `MachineExperience`, `CompiledOperationalWorld`), a blob-pinned offline
   verifier registry, and fail-closed reverification already implement the boundary. Any "gap" here
   would be a weakening, not an improvement.
10. **Causal capability-gap semantics.** Not needed and not licensed; see §6.4. Deferred.

## 9. Deferred work

Deferred by explicit repository policy, not by this audit's discretion. Each is a dependency for
later phases, not a task for the current lane.

- Causal capability-gap semantics — deferred by Phase 1 §10 and by `CapabilityAttributionReport.caveat`.
- `DistributionProfile` — no distribution abstraction is introduced; `DistributionSplit` +
  `CalibrationProfile` + per-distribution validators suffice for this phase.
- `DifficultyVector` semantics — the model exists (`foundry/models.py`) and `PackDifficulty`
  computes a real score, but its *semantics* are out of scope for this phase.
- Adaptive world mutation — evaluation results do not mutate worlds in this audit.
- Adaptive training, training-value claims, learning-efficiency claims —
  `docs/experience/learning-efficiency.md` is the governing document; its loop is explicitly a
  hypothesis to be controlled, not an assumption.
- `CapabilityGraph` redesign — protected; untouched.
- Automatic qualification — `assess_environment_maturity` derives status from evidence but requires
  evidence to be supplied; gate evidence production for
  `held_out_training_improvement` remains manual (G-08).
- Automatic held-out transfer loop — the loop in `learning-efficiency.md` is a target, not an
  implemented pipeline.
- `MachineExperience` annotation producers (spans, structural records, diagnostics) — deferred by
  `docs/experience/machine-experience.md` "Deferred work".
- Failure clustering / counterfactual generation / procedure & abstraction induction / curriculum
  mining / training bundle construction / continual-learning loops — all deferred by the same
  section.

## 10. Dependency-ordered Phase 3+ recommendation

Ordered so that each step is unblocked and each step increases what can be *checked*, not just what
exists. Not every identified gap is recommended for implementation; several are explicitly
*not* recommended (§8, §9).

### 1. Already satisfied — no action

`OperationalWorld`, `OperationalEpisode`, execution+effects, independent verification,
`MachineExperience` as a record, environment qualification, per-distribution held-out separation,
OOD/held-out independence. These are the load-bearing majority of the chain. Recommend: **document
the mapping** (Phase 1 did this; this audit confirms it) and change nothing.

### 2. Documentation-only normalization — first, because it is cheapest and it unblocks everything

Make the role→implementation mapping in §5 normative reference material, so that later phases stop
re-deriving it. Add to the existing `docs/experience/` set: the chain table in §5 of this document
belongs alongside `held-out-transfer.md`. Cost: one document. Benefit: G-13 through G-16 stop being
re-litigated. **This is the single highest value-per-change item in the whole inventory.**

### 3. Evidence/schema gaps — second, because they are small and everything downstream depends on them

1. **G-01 — `CapabilityContract` content-derived identity.** A validator and a digest. This is the
   root dependency: `FailureFamily.affected_capability`, `CapabilityGap.capability`,
   `TrainingRecipe.capability_contract_id` and any future transfer evaluation all reference a
   capability by string today. Small, additive, well-precedented (`MaturityPolicy`, `CapabilityGraph`).
2. **G-12 — calibration↔capability reference.** Trailing edge of G-01; a reference field or
   documentation, not a mechanism.
3. **G-02 — contract → world/episode binding.** Depends on G-01. Must be **declarative metadata plus
   a validator, not runtime behavior**: `OperationalEpisode` stays capability-neutral at execution.
   This is the chain edge that is currently documentation-only, and it is the reason every downstream
   capability-scoped claim is currently unchecked. Because it touches protected `operational/**` and
   `operational_world/**`, it needs its own lane with additive-only changes and explicit ownership
   negotiation; the validator should check consistency between the contract's `success_conditions`/
   `hard_invariants` and the oracle's `target_state`/`invariants`, not alter either.
4. **G-03 — operational-episode → `TrajectoryV2` adapter.** Depends on nothing new. Reuses the exact
   `TrajectoryEvent` payload shapes that `reverify/engine.py` already decodes (`method == "act"`,
   `args`/`kwargs`), so reverification keeps working. Unblocks every downstream stage, because
   `MachineExperience` requires a `TrajectoryV2`.

### 4. Implementation gaps — third, and only the connective tissue

5. **G-09 — transfer comparison/report object.** Depends on G-01 (contract digest) and G-03
   (trajectories for both arms). **Explicitly not an engine and not a runtime class.** It records:
   both conditions as `WorldIdentity`/`TaskIdentity`/contract-digest triples, the verifier identity,
   and the paired statistics — reusing `_paired_delta`/`critical_95` verbatim rather than
   reimplementing them. Its producer populates `ExperienceSequence.transfer_test_experience_ids`,
   which exists today and has none.
6. **G-11 — existence-vs-improvement, in the schema of G-09.** Folded into G-09 deliberately: the
   object must carry baseline identity, pre-stated comparison, uncertainty, and the baseline's own
   development status, so that a populated object is self-describing as *evidence* or *measured
   improvement*. This closes Phase 1 §7's loophole at the artifact level instead of leaving it to
   prose. **This is the highest-value semantic fix after G-02**, because it is the boundary that
   fails silently in the favorable direction.

### 5. Qualification gaps — fourth

7. **G-08 — `held_out_training_improvement` gate evidence adapter.** Small; consumes the outputs of
   the existing training-value tooling (panel hash, paired deltas, seed variance) and emits
   `MaturityGateEvidence`. Must live outside protected training code and consume it read-only.
8. **G-07 — capability/agent-scoped qualification record.** Largest non-deferred item, and the one
   most likely to be over-built. Recommendation: **extend the `MaturityRecord` pattern** (policy,
   gates, content-addressed evidence, derived status, append-only history) to a capability-contract +
   agent + panel subject, rather than authoring a new framework. Depends on G-01 and G-02, which is
   why it is ordered after them.

### 6. Deferred research — not scheduled

G-04, G-05, G-06 (annotation producers, failure clustering, gap aggregation) and all of §9. These
are evidence-bearing programs with their own hypotheses and controls
(`docs/experience/learning-efficiency.md` is explicit that selection is a hypothesis to be tested
against matched controls). They should not be scheduled as if they were implementation tasks.

### 7. Protected / deferred areas — no action

`CapabilityGraph`, `OperationalEpisode` behavior, Gold-10, SRE/HUD, `release/**`, training
experiment code, sealed/private benchmark material, adaptive mutation, `DistributionProfile`,
`DifficultyVector` semantics, causal gap semantics.

### Why this order

G-01 first because every capability-scoped identity downstream depends on it and it is a pure,
additive validator. G-02 second because it is the one chain edge that is currently only a
documentation claim, and because G-07 and G-09 are meaningless without it. G-03 third because
`MachineExperience` — and therefore failure evidence, gaps, and any transfer comparison — requires a
trajectory, and the producer is the last missing piece of an otherwise complete path. G-09/G-11
fourth because they convert the chain from a set of records into a *checkable claim*, which is the
actual product of the ontology work. G-07 last among the non-deferred items because it is the most
expensive and the most likely to duplicate what already exists if rushed.

## 11. Protected surfaces

Confirmed untouched by this audit. Each was checked, not assumed.

| Surface | Status | Evidence |
|---|---|---|
| `src/investigation_world/operational/**` | Not modified | Read-only inspection of `models.py`, `runtime.py`, `verifier.py`, `substrate.py`, `distribution.py`, `deep_distribution.py`, `catalog.py`, `artifacts.py`, `realism.py` |
| `OperationalEpisode` | Not modified | Only schema-level description of existing fields and validators |
| Gold-10 | Not modified, not exposed | `src/investigation_world/gold10/**` inspected only at `replay.py`'s public adapter surface; no sealed row, label, or oracle content is reproduced here |
| SRE/HUD | Not modified | `qualification/sre*.py` and `exporters/hud/**` not touched; `commercial/sre_*` not touched |
| `release/**`, package/version identifiers | Not modified | No version, manifest, or release file changed |
| `CapabilityGraph` | Not modified, not redesigned | Read as an existing protected object; only its existing non-causal caveat is quoted |
| Training / learning-efficiency experiment code | Not modified | `foundry/training_*.py`, `tools/run_training_value*.py` read for evidence shape only |
| Sealed/private benchmark material | Not exposed | No private scenario ID, hidden label, oracle row, or decrypted bundle appears in this document |
| Adaptive world mutation | Not introduced | No mechanism here mutates a world in response to evaluation results |
| `DistributionProfile` / `DifficultyVector` semantics | Not introduced | Only existing models are referenced, and only to say their semantics are deferred |
| Causal `CapabilityGap` semantics | Not introduced | §6.4 states the opposite; `CapabilityGap` is described as descriptive throughout |
| Root/shared integration paths | Not modified | Only `docs/experience/canonical-ontology-gap-audit.md` was written |

## 12. Falsifiers

The audit is invalid if any of the following holds. Each is answered against the evidence gathered.

- **An existing capability is marked absent only because of naming differences.** Not triggered.
  `VeritasWorld`/`VeritasEpisode` were mapped to `OperationalWorld`/`OperationalEpisode` and marked
  `SATISFIED`/`NOT SEPARATELY REQUIRED`; `ABSENT` is used only for G-10 and G-11, where no artifact
  performs the function under any name.
- **A duplicate runtime class is proposed solely for canonical terminology.** Not triggered. §8 lists
  nine objects explicitly recommended for *no* implementation, including all four canonical role
  names.
- **A missing runtime class is proposed where existing infrastructure already satisfies the required
  semantics.** Not triggered. `TransferEvaluation` is recommended as a thin reporting object over
  existing identities and existing statistics, with an explicit instruction to reuse
  `_paired_delta`/`critical_95` rather than build an engine.
- **Existing `MachineExperience` is replaced or duplicated.** Not triggered. §5.8 and §8 item 4
  record it as the canonical record; the only note is that its annotation producers are deferred.
- **Existing `OperationalWorld`/`OperationalEpisode` are replaced.** Not triggered. Neither was
  modified; §5.3/§5.4 mark both `SATISFIED`.
- **Transfer improvement is inferred from held-out evaluation.** Not triggered. §5.13 and §6.5 state
  the opposite, and no finding in this document is an improvement claim.
- **Causal `CapabilityGap` semantics are asserted without evidence.** Not triggered. §5.10 and §6.4
  describe `CapabilityGap` as descriptive and quote the repository's own non-causal caveats.
- **Private benchmark information is exposed.** Not triggered. See §11.
- **Files outside the frozen positive ownership path are modified.** Not triggered. Verified in §13.

## 13. Audit limitations

- **Tree state.** The local clone's `main` ref was stale relative to `origin/main` (fetch is
  unavailable: `ssh.github.com` is unreachable from this host). The audit base was therefore
  established via the GitHub API: `main` head `3499c7d`, root tree `a4c66b95…`, confirmed to equal
  `aabbfc6` plus the Phase 1 file only. The working branch tree was verified equal to that tree
  before any edit. A separate local commit `4b911ea` ("docs: reconcile roadmap dependency completion
  state") exists on a divergent local branch and differs from the audited base only in
  `.github/agent-roadmap.yml`; it was **not** used as the base and does not affect any finding here.
- **Phase 1 restored from a content-addressed blob.** Because the branch was cut from `aabbfc6`,
  `docs/experience/held-out-transfer.md` was restored from blob `10eb186b` (verified: 21,746 bytes,
  matching `origin/main`) and committed as `fd7f328`. This is the merged Phase 1 content, byte-identical.
- **No behavioral re-execution of the full chain.** Source and tests were read; targeted checks were
  run (§14). Native/model-dependent suites (Gold-10 replay, observatory live runs, training-value
  experiments) were not executed, so behavioral claims about them rest on their tests and docstrings,
  not on re-running them here.
- **Gold-10 was inspected only at its public adapter surface** (`gold10/replay.py::traceable_experience`,
  `build_reference_experiences`). Deliberate: sealed material is out of scope and unnecessary for
  this audit.
- **`CapabilityGraph` internals are described only to the extent needed** to distinguish it from
  `CapabilityGap` and to quote its caveat. No redesign is proposed.
- **G-02 and G-07 estimates are planning-level.** "Add a validator" and "extend the maturity
  pattern" are scoping judgements from reading the code, not from prototyping. Both touch protected
  surfaces and need their own lanes with ownership negotiation.
- **The audit does not establish scientific qualification, transfer improvement, training value,
  learning efficiency, Frontier status, commercial release readiness, adaptive-world validity, or
  any permission to modify protected or sealed surfaces.** It establishes ontology coverage and gap
  boundaries only.

## 14. Verification

Checks actually run, cheapest first.

1. **Ownership.** `git status --porcelain` on
   `feat/canonical-veritas-ontology-audit` shows only
   `docs/experience/canonical-ontology-gap-audit.md` as modified/added. No other file was written.
2. **Cited paths resolve.** Every path cited in §5, §7 and §11 was resolved against the working
   tree during inspection, including: `src/investigation_world/foundry/models.py`,
   `src/investigation_world/foundry/capability_families.py`, `src/investigation_world/foundry/companyworld.py`,
   `src/investigation_world/foundry/cli.py`, `src/investigation_world/foundry/training_corpus.py`,
   `src/investigation_world/foundry/training_product.py`, `src/investigation_world/operational/models.py`,
   `src/investigation_world/operational/runtime.py`, `src/investigation_world/operational/verifier.py`,
   `src/investigation_world/operational/substrate.py`, `src/investigation_world/operational/catalog.py`,
   `src/investigation_world/operational/deep_distribution.py`, `src/investigation_world/operational_world/models.py`,
   `src/investigation_world/operational_world/capability_pack.py`, `src/investigation_world/operational_world/pipeline.py`,
   `src/investigation_world/operational_world/validation.py`, `src/investigation_world/experience/models.py`,
   `src/investigation_world/experience/adapter.py`, `src/investigation_world/trajectory/models.py`,
   `src/investigation_world/trajectory/adapter.py`, `src/investigation_world/trajectory/reverify/{engine,operational,batch,models}.py`,
   `src/investigation_world/portable_contract/{models,compiler}.py`, `src/investigation_world/portable_runtime/runtime.py`,
   `src/investigation_world/qualification/{maturity,models,protocol,verifier_suite,quality_scorecard}.py`,
   `src/investigation_world/evidence/models.py`, `src/investigation_world/observatory/{models,analysis,aggregation,capability_graph}.py`,
   `src/investigation_world/observatory/trajectory_diagnostics/{engine,models}.py`,
   `src/investigation_world/verifier/aggregate.py`, `src/investigation_world/gold10/replay.py`,
   `tools/run_training_value_v3.py`, and the cited docs and tests.
3. **Cited symbols exist.** Spot-checked by symbol search where load-bearing:
   `CapabilityContract`, `CapabilityFamily`, `OperationalWorldSpec`, `CompiledOperationalWorld`,
   `CalibrationProfile`, `OperationalEpisode`, `TaskContract`, `HiddenOracle`, `HiddenActionEffect`,
   `ActionEvent`, `EpisodeSubmission`, `VerificationBreakdown`, `verify_operational_episode`,
   `OperationalRuntime`, `TrajectoryV2`, `TrajectoryEvent`, `StateDigest`, `ReverificationRecord`,
   `MachineExperience`, `ExperienceMaturity`, `ExperienceReadiness`, `ExperienceSequence`,
   `FailureFamily`, `CapabilityGap`, `FailureMechanism`, `FailureCategory`,
   `EnvironmentMaturity`, `MaturityPolicy`, `MaturityRecord`, `MaturityGateEvidence`, `GateOutcome`,
   `assess_environment_maturity`, `EvidenceRecord`, `CapabilityGraph`, `CapabilityAttributionReport`,
   `attribute_drift`, `compare_runs`, `compare_aggregates`, `diagnose_failure`,
   `compile_operational_episode`, `PortableOperationalContract`, `PortableOperationalRuntime`,
   `OperationalVerifierBinding`, `AuthorizedVerifierRegistry`,
   `current_operational_verifier_binding`, `InvestigationPackSpec`,
   `InvestigationCapabilityPackBuilder`, `validate_operational_distribution`,
   `qualify_candidate`, `qualify_verifier`, `machine_experience_from_trajectory`,
   `traceable_experience`, `_paired_summary`, `_panel_hash`, `critical_95`, `_paired_delta`,
   `Veritas`, `VeritasCapability`.
4. **No new runtime class introduced.** The only file written is a Markdown document. It defines no
   class, function, module, schema, or identifier that the repository must resolve.
5. **Forbidden constructs absent from the deliverable.** The document contains no
   `DistributionProfile`, no `DifficultyVector` semantics, no adaptive mutation, no causal
   capability-gap semantics, no training/learning-efficiency claim, no `VeritasWorld`/
   `VeritasEpisode` class proposal, and no `CapabilityGraph` redesign.
6. **Structural checks.** Markdown structure validated: single `#` title, fenced blocks balanced,
   every `##` section from the required structure present (§1–§14), both tables well-formed, no
   unclosed inline code.
7. **Import/compile smoke.** `python3 -m compileall` over the packages inspected in §5 completed
   without errors, so the symbols cited are from importable modules on this base.
8. **Targeted test evidence.** Test names cited in §5 were confirmed to exist in the repository's
   test tree with the behaviors described (determinism, oracle non-leakage, fail-closed maturity,
   exact verifier-version binding, panel matching, split disjointness, content-derived identities).
   The full pytest suite was not executed: several suites require native/model dependencies that are
   unavailable on this host. This is a documentation audit and no claim here depends on an unrun
   behavioral check.

## 15. Conclusion

The canonical evidence lifecycle is substantially implemented in Veritas. Of thirteen nodes, six are
`SATISFIED` outright (`OperationalWorld`, `OperationalEpisode`, independent verification,
`MachineExperience` as a record, environment qualification, and — for its scoped purpose — held-out
separation), four are `PARTIAL` because a *producer* or a *binding* is missing rather than a
substrate (capability binding, runtime→trajectory, failure evidence, `CapabilityGap`, transfer
assemblage), and the remaining roles are `NOT SEPARATELY REQUIRED` because an existing object already
plays them.

Two findings are load-bearing.

**First, the chain's weakest edge is not a missing object; it is a missing *binding*.** Nothing
connects a `CapabilityContract` to the `OperationalEpisode` whose oracle was built to evaluate it
(G-02). Every capability-scoped claim downstream — failure families' `affected_capability`, gaps'
`capability`, qualification, and any transfer comparison — inherits that looseness. The substrate on
both sides of the edge exists and is strong. The edge is a documentation claim today.

**Second, the chain's most dangerous gap is the one that fails silently in the favorable direction.**
Held-out evaluation exists and is well enforced per-distribution, but nothing at the schema level
separates "transfer evidence exists" from "transfer improvement was measured" (G-11). Phase 1 §7
states the distinction normatively; the repository enforces it only in the training-value tooling's
own discipline. A future consumer reading a populated `transfer_test_experience_ids` cannot tell
which of the two it holds.

The recommended Phase 3 order follows from those two findings: content-address the contract, bind the
contract to the episode declaratively, produce trajectories from operational episodes, then assemble
the transfer comparison *with* the existence/improvement distinction baked into its schema — reusing
existing statistics rather than building an engine. Everything else in the inventory is either
deferred research with its own hypotheses to control, or a protected surface that should not move.

Phase 2 ends here: an audited, reviewable map of the ontology and its actual gaps, and no
speculative architecture expansion.
