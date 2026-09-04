# Gold-10 flagship pilot

Status: executable pilot candidate. This package does not establish scientific,
Frontier, training-value, learning-efficiency, release, or commercial qualification.

## Purpose

ROADMAP-001 turns the frozen CASE-001 selection into ten deterministic,
source-grounded investigation tasks without reopening source selection or
RIGHTS-001 authority.

The runtime consumes the canonical Gold-10 manifest and the already reviewed
pilot manifests. It does not commit raw CSB PDFs, duplicate source bytes, create
private ground truth, or reinterpret mutable artifact-review status as authority.

## Trust and evidence boundary

The pilot inherits the frozen CASE-001 properties:

- exactly ten USCSB cases;
- case-disjoint 6 train / 2 dev / 2 eval split;
- exact report, receipt, catalog, URL, source-policy, and task-use authority binding;
- internal task/verifier evidence use only;
- no raw/public redistribution authority;
- no model-training, commercial, scientific, or Frontier authority;
- public temporal cuts with later evidence withheld;
- institutional findings remain evidence, not omniscient/private truth;
- Chevron Richmond remains the calibration case.

`build_task()` reconstructs CASE-001 before exposing a task. It then reads the
matching reviewed pilot manifest and exposes only public fragments available at
the frozen `simulation_as_of` cut. Later public material is withheld. Raw report
bytes are never loaded by this layer.

## Task and submission contract

Each task uses native Veritas `TaskSpec` and has stable ID
`GOLD10-<case-id>`. A submission must provide:

- a falsifiable primary hypothesis and a distinct alternative;
- confidence for both with coherent residual probability mass;
- cited evidence IDs;
- structured epistemic claims;
- unresolved questions where appropriate.

Allowed claim kinds are `fact`, `allegation`, `institutional_finding`,
`hypothesis`, and `uncertainty`. There is deliberately no `ground_truth` kind.

Primary and alternative hypotheses are not rewarded merely because their strings
are non-empty or because they repeat a submitted claim. The verifier owns a
case-specific target contract in `gold10.targets`. For every case, the primary and
alternative working hypotheses have distinct target IDs, exact statements, and
exact support-evidence IDs that must be available at the frozen temporal cut.

Those targets are evaluation fixtures for the deterministic pilot verifier. They
are explicitly working hypotheses, not private truth, final causal findings, or
scientific qualification. Their purpose is to prevent arbitrary prose from
receiving the maximum available unqualified reward while preserving the pilot's
non-LLM deterministic boundary.

A valid hypothesis claim therefore must match all of:

- the task-specific hypothesis target ID;
- the exact target statement for its primary or alternative role; and
- the exact frozen-cut evidence binding.

Positive reward also requires at least one separate canonical public factual
verifier target. Hypothesis and uncertainty targets do not count as factual targets.
Supported factual targets are:

- `evidence:<fragment-id>` for a `fact` claim whose statement and evidence ID
  exactly match the deterministic evidence-availability target; or
- `finding:<finding-id>` for an `institutional_finding` claim whose statement
  and evidence IDs exactly match an available canonical institutional finding.

Institutional findings remain institutional evidence. Matching one does not
promote it to private or omniscient truth.

## Deterministic verifier and reward ceiling

The verifier does not call an LLM. It scores:

- evidence coverage;
- task-specific hypothesis/evidence binding;
- canonical factual-target fidelity;
- calibration integrity;
- rights and temporal integrity.

Hindsight or invented evidence is a zero-reward hard failure. Missing hypothesis
bindings, missing canonical targets, unknown canonical targets, target-kind drift,
target-statement drift, and target-evidence drift are also fail-closed conditions.
A valid FACT or institutional-finding target cannot authorize unrelated or
nonsensical hypothesis text.

The verifier does not claim to establish open-ended semantic correctness or
plausibility of arbitrary free-form hypothesis prose. The pilot contract therefore
applies a `0.75` multiplicative reward ceiling. A target-bound scripted reference
scores `0.75`, not `1.0`. This is a pilot safety boundary, not a scientific
threshold or a capability score.

For the Chevron Richmond calibration case, residual probability mass alone is
insufficient. The verifier has one exact case-specific uncertainty target bound to
the surveillance evidence available at the frozen cut. Calibration credit requires
that exact unresolved question and an `uncertainty` claim with the exact target ID,
statement, and evidence binding. Repeating arbitrary unresolved boilerplate is a
hard failure even if an unrelated canonical factual target remains valid.

## Native trajectory and MachineExperience

`traceable_experience()` records task reset, evidence inspection, and structured
submission as native `TrajectoryV2`, then wraps the result in native
`MachineExperience` at exactly `E0_TRACEABLE`.

No E1+ readiness flag is fabricated. Public experiences contain no private
evaluator reference, private event payload, trajectory private metadata, or
experience private metadata. The trajectory records the unqualified verifier
ceiling explicitly in public metadata.

Reference episodes are deterministic target-bound protocol-solvability fixtures
only. They are not expert trajectories and are not model-capability evidence.

## Mandatory pilot-level gate report

`build_pilot_gate_report()` is the executable ROADMAP-001 gate report. It binds
its own SHA-256 identity and covers every required pilot-level gate:

1. deterministic taskset rebuild identity;
2. exact-duplicate and near-duplicate objective analysis;
3. contamination assessment;
4. case/source/causal/task-structure coverage;
5. reference/scripted solvability;
6. exploit/shortcut probes;
7. the canonical multidimensional Veritas environment-quality scorecard.

The report can be materialized with:

```bash
python - <<'PY'
import json
from investigation_world.gold10 import build_pilot_gate_report

print(json.dumps(build_pilot_gate_report(), indent=2, sort_keys=True))
PY
```

### Duplicate and near-duplicate analysis

Objectives are normalized to lowercase alphanumeric tokens. Exact normalized
duplicates are reported separately. Near duplicates use deterministic Jaccard
similarity with the threshold frozen in `pilot_contract_v1.json`.

This is a structural screen, not a claim of semantic independence.

### Contamination assessment

The report explicitly classifies the pilot as
`high_public_historical_nonsealed`. All ten cases are public historical USCSB
material. The report therefore sets `contamination_clean_claim_authorized=false`.

Case-disjoint splitting and temporal cuts mitigate some evaluation leakage but
do not make the corpus contamination-clean.

### Coverage report

The executable report records:

- all ten case IDs and 6/2/2 split counts;
- source counts and source diversity;
- modality counts and modality diversity;
- capability-target coverage;
- calibration cases;
- cases with available institutional findings;
- explicit causal-edge counts by case;
- task-specific hypothesis and calibration-target requirements;
- supported task/claim structure.

Single-source USCSB coverage is visible rather than presented as broad source
diversity.

### Exploit and shortcut policy

The report executes adversarial probes and fails its exploit gate unless all pass:

- arbitrary hypotheses with valid public evidence but no canonical target must
  receive zero reward;
- nonsense primary/alternative hypotheses must receive zero reward even when an
  otherwise valid canonical FACT or institutional-finding target is preserved;
- canonical target statement mismatch must receive zero reward;
- hindsight evidence must receive zero reward;
- collapsed calibration uncertainty must receive zero reward;
- structured meaningless calibration boilerplate must receive zero reward even
  when an unrelated valid canonical target remains intact.

Residual risks are retained in the report. The deterministic target contract does
not establish open-ended semantic-verifier qualification, and public historical
material remains contamination-prone.

### Canonical VQ multidimensional scorecard

ROADMAP-001 does not define a parallel quality formula. The gate report projects
its evidence through the existing canonical
`veritas.environment-quality-scorecard.v1` implementation in
`investigation_world.qualification.quality_scorecard`.

That canonical scorecard contains all 18 fixed dimensions and uses separate
`PASS`, `FAIL`, and `UNKNOWN` outcomes. It deliberately does not average quality
into a scalar score.

Gold-10's own pilot-gate evidence is emitted only as `OBSERVED`, because this lane
is not a qualification authority. The observations cover reward-hack probing,
reset/rebuild determinism, task ambiguity/calibration, structural diversity,
reproducibility, and provenance completeness. Under the canonical scorecard,
`OBSERVED` is still `UNKNOWN`, and dimensions without qualifying evidence also
remain `UNKNOWN`.

The scorecard therefore cannot self-promote this pilot. Scientific, Frontier,
training-value, and commercial qualification authority remain false.

## Falsifiers

The owned tests fail if:

- the taskset is not exactly ten cases or the split is not 6/2/2;
- fewer than two evidence modalities remain available;
- later Texas City evidence leaks through the frozen cutoff;
- Chevron Richmond stops being the calibration case;
- arbitrary hypotheses without a canonical target receive positive reward;
- nonsense hypotheses plus a valid factual target can receive positive reward;
- case-specific hypothesis target statements/evidence can drift without hard failure;
- canonical factual-target statements/evidence can drift without hard failure;
- invented or hindsight evidence receives nonzero reward;
- primary and alternative hypothesis roles are not bound to their distinct targets;
- calibration collapses uncertainty without a hard penalty;
- structured meaningless calibration plus a valid target can receive positive reward;
- a submission can encode a `ground_truth` claim kind;
- deterministic task/report identity changes across identical rebuilds;
- the exploit/shortcut gate does not pass;
- the contamination report claims this public corpus is clean;
- the VQ projection omits canonical dimensions or invents a scalar aggregate;
- ROADMAP-001 observations are promoted to VQ PASS evidence;
- the VQ projection grants scientific/Frontier/training/commercial authority;
- E0 MachineExperience capture widens private visibility.

## Remaining qualification work

ROADMAP-001's pilot-level acceptance gates are implemented here. Separate work is
still required before stronger claims: independent verifier qualification,
scientific capability validation, Frontier qualification, training-value evidence,
learning-efficiency evidence, and commercial/release authorization.
