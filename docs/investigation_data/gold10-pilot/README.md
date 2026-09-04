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
are non-empty. Each must have a matching `hypothesis` claim with public evidence
available at the temporal cut.

Positive reward also requires at least one canonical public verifier target.
Supported canonical targets are:

- `evidence:<fragment-id>` for a `fact` claim whose statement and evidence ID
  exactly match the deterministic evidence-availability target; or
- `finding:<finding-id>` for an `institutional_finding` claim whose statement
  and evidence IDs exactly match an available canonical institutional finding.

Institutional findings remain institutional evidence. Matching one does not
promote it to private or omniscient truth.

## Deterministic verifier and reward ceiling

The verifier does not call an LLM. It scores:

- evidence coverage;
- hypothesis/evidence binding;
- canonical target fidelity;
- calibration integrity;
- rights and temporal integrity.

Hindsight or invented evidence is a zero-reward hard failure. Missing hypothesis
bindings, missing canonical targets, unknown canonical targets, target-kind drift,
target-statement drift, and target-evidence drift are also fail-closed conditions.

Because this deterministic verifier does not establish open-ended semantic
correctness of arbitrary prose, the pilot contract applies a `0.75` multiplicative
reward ceiling. A structurally perfect scripted reference therefore scores `0.75`,
not `1.0`. The ceiling is a pilot safety boundary, not a scientific threshold.

For the calibration case, residual probability mass alone is insufficient.
Calibration credit also requires an explicit `uncertainty` claim whose statement
matches an unresolved question and whose evidence is available at the cut.

## Native trajectory and MachineExperience

`traceable_experience()` records task reset, evidence inspection, and structured
submission as native `TrajectoryV2`, then wraps the result in native
`MachineExperience` at exactly `E0_TRACEABLE`.

No E1+ readiness flag is fabricated. Public experiences contain no private
evaluator reference, private event payload, trajectory private metadata, or
experience private metadata. The trajectory records the unqualified verifier
ceiling explicitly in public metadata.

Reference episodes are deterministic protocol-solvability fixtures only. They
are not expert trajectories and are not model-capability evidence.

## Mandatory pilot-level gate report

`build_pilot_gate_report()` is the executable ROADMAP-001 gate report. It binds
its own SHA-256 identity and covers every required pilot-level gate:

1. deterministic taskset rebuild identity;
2. exact-duplicate and near-duplicate objective analysis;
3. contamination assessment;
4. case/source/causal/task-structure coverage;
5. reference/scripted solvability;
6. exploit/shortcut probes;
7. a multidimensional VQ scorecard.

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
- supported task/claim structure.

Single-source USCSB coverage is visible rather than scored as broad source
diversity.

### Exploit and shortcut policy

The report executes adversarial probes and fails its exploit gate unless all pass:

- arbitrary hypotheses with valid public evidence but no canonical target must
  receive zero reward;
- canonical target statement mismatch must receive zero reward;
- hindsight evidence must receive zero reward;
- calibration boilerplate without structured uncertainty must score below the
  valid calibration reference.

Residual risks are retained in the report. In particular, canonical target
binding is not open-ended semantic-verifier qualification.

### VQ multidimensional scorecard

The pilot-level VQ scorecard reports separate dimensions for:

- task integrity;
- provenance/rights integrity;
- temporal integrity;
- replay/scripted solvability;
- coverage diversity;
- verifier robustness;
- contamination resilience.

Verifier robustness is capped by the unqualified reward ceiling. Contamination
resilience is explicitly discounted for public historical material. Coverage
diversity exposes the single-source limitation. The overall value is diagnostic
only and carries no scientific, Frontier, training-value, or commercial authority.

## Falsifiers

The owned tests fail if:

- the taskset is not exactly ten cases or the split is not 6/2/2;
- fewer than two evidence modalities remain available;
- later Texas City evidence leaks through the frozen cutoff;
- Chevron Richmond stops being the calibration case;
- arbitrary hypotheses without a canonical target receive positive reward;
- canonical target statements/evidence can drift without hard failure;
- invented or hindsight evidence receives nonzero reward;
- hypothesis strings are not structurally bound to evidence claims;
- calibration collapses uncertainty without penalty;
- a submission can encode a `ground_truth` claim kind;
- deterministic task/report identity changes across identical rebuilds;
- the exploit/shortcut gate does not pass;
- the contamination report claims this public corpus is clean;
- the VQ scorecard grants qualification authority;
- E0 MachineExperience capture widens private visibility.

## Remaining qualification work

ROADMAP-001's pilot-level acceptance gates are implemented here. Separate work is
still required before stronger claims: independent verifier qualification,
scientific capability validation, Frontier qualification, training-value evidence,
learning-efficiency evidence, and commercial/release authorization.
