# Stateful evaluation evidence slice (STATEFUL-EVAL-001)

This bounded extension implements part of [MODEL-INSPECT-001 (#421)](https://github.com/FPC-effortless/veritas/issues/421),
with intervention-design overlap to [DIAG-002 (#193)](https://github.com/FPC-effortless/veritas/issues/193).
Neither parent is completed or promoted by this slice. The executable work is
[#466](https://github.com/FPC-effortless/veritas/issues/466).

## What exists and what this adds

Veritas already owns canonical trajectories/reverification, evidence/privacy,
capability measurements, operational counterfactuals, selection, curriculum,
training qualification, continual-learning protocols and learning-efficiency
reports. This is **not** a second trainer, dashboard, benchmark or qualification
engine. It adds a small adapter for externally supplied stateful-study receipts:

- an independently expected arm × initialization seed × condition matrix;
- complete canonical CAP evaluation populations and outcomes;
- separate exact-answer and component scores, native and policy acceptance;
- typed state ownership, declared intervention and resource evidence;
- complete missing/failed cells and content-bound descriptive summaries.

The implementation is `investigation_world.observatory.stateful`; it has no root
export, dynamic plugin loader, family-specific dependency, checkpoint loader or
network behavior. Inputs are in-memory typed records. There is no implicit NPZ,
pickle or arbitrary-path ingestion.

Use `ScienceRecord`, `EvaluationPopulation`, `EvaluationPoint`, `CaseOutcome` and
`ExperienceReference` from their existing modules. `StatefulStudy.expected` is an
independently retained commitment, not a plan reconstructed from surviving runs.
Each expected manifest pins its actual metric populations. Actual imported points
must match them, including their complete case identities, source digests, metric
definition and model/checkpoint identity. `assess_stateful(study)` produces a
`StatefulReport`; parsing its saved form must revalidate its aggregates.
`complete_matrix` means every planned cell has a completed receipt, not that every
case was scored or any study was qualified. Per-row unknown-outcome counts and
the complete original CAP points preserve those missing observations.

## Evidence and qualification boundaries

An archive can establish arithmetic consistency with saved outcomes. It cannot
establish that a model ran, a memory was erased, a checkpoint replayed, a stream
was isolated or a protocol was prospectively registered. References and hashes
are content commitments, not authentication. Constructed fixtures, imported
observations and externally reported measurements retain their different origins.

Do not fabricate a `TrainingBundle`, `TrainingRunManifest`, `TrainingReport` or
`AcquisitionCurve` merely to fit archived inference predictions into CL-001 or
LE-002. Those providers remain authoritative when a genuine training study fits
their contracts. Do not turn neural erasure into a CompanyWorld action mutation
or synthesize a `TrajectoryV2` from final prediction arrays.

The shared-evidence adapter emits **OBSERVED**, not a maturity-gate PASS. Scientific,
causal, frontier, commercial and execution-attestation claims remain unavailable.
An explicit incomplete-budget or failed preflight is not a scientific falsifier.
No actual portfolio model is loaded or evaluated by this package.

## Exactness, acceptance and missingness

Whole-answer correctness uses a `success_fraction` population with binary case
outcomes. A component score uses a separately defined `criterion_score` population.
For eight-bit recall, exactness means all eight bits match; mean bit accuracy is
not its substitute. For a regression endpoint without a meaningful exact-answer
criterion, retain exactness as not applicable with an explicit reason. Do not
arbitrarily threshold MSE or cross-entropy into a success score.
CAP `criterion_score` is bounded in `[0, 1]`; raw MSE or cross-entropy outside that
range remains in its referenced original artifact, not silently normalized into
this interface. No common loss leaderboard or arbitrary scalar loader is added.

Native and independently selected policy acceptance are different masks. Each
mask covers the complete expected member set. An unavailable mask element or
outcome remains unknown. With no accepted cases, coverage is zero and accepted
quality/risk is **undefined (`None`)**, not perfect. A numerical accepted error is
descriptive; it is not a calibrated risk guarantee. Any calibration target must
name its loss (whole answer versus component), calibration splits and policy.

Keep every planned initialization, condition and baseline; do not silently use a
matched intersection. Preserve raw per-fit results and report initialization
variation separately from query uncertainty. This first slice provides arithmetic,
not a generic confidence-interval or causal-estimation engine.

## State and interventions

Declare transient state, adaptive weights, shared buffers, optimizer and RNG state
separately, with an owner and scope. State bytes are not process peak memory.
Inference may mutate recurrent state without learning parameters; feedback-driven
plasticity and parameter updates need separately declared event boundaries.

Keep these experiments distinct:

| Intervention | What it can address | What it cannot establish alone |
| --- | --- | --- |
| Reset/restart and snapshot restoration | Reproducibility of the stated state boundary | Recovery of undeclared optimizer/RNG/shared state |
| Stream isolation | Independence of declared stream-owned state | General tenant security |
| Query-time component erasure | Dependence of a fitted predictor on stored state | Benefit of training with that component |
| Retrained component removal | Result of a separately trained control | Pure inference-state causal effect |
| Frozen plasticity/topology | Dependence on the declared update mechanism | Effect of any simultaneously changed router or capacity |

Each result needs the exact component, timing, protocol and observation references.
Unsupported capabilities remain NOT_RUN/UNKNOWN; they are not successful no-ops.
An imported `OBSERVED` check describes a supplied receipt, not locally verified
execution. Whole-system or biological claims do not follow from state telemetry.

## Public deterministic replay example

Run `examples/stateful_evaluation.py` against the intended package installation.
It never modifies `sys.path`, imports a portfolio architecture, trains, loads a
checkpoint, or calls a network service. Its two-stream dictionary is explicitly a
**constructed conformance fixture**, not a learned model or proposed product.

`replay_fixture()` predicts using only the stream and key before feedback is
applied. The evaluator scores afterward. A second arm erases only stream A's
dictionary before the final query. `check_fixture_lifecycle()` actually checks
prediction-before-feedback, stream isolation, targeted erasure, snapshot/restore,
snapshot ownership and stream-specific reset for this fixture. It does not claim
those checks passed for PSN or any other architecture.
The restart check constructs a fresh fixture instance and restores its snapshot;
it does not establish process/OS restart, durable storage or crash consistency.

The example's local import diagnostics retain the resolved source path, SHA256,
Python and platform separately from any public report projection. A source run
and a clean installed-wheel run must record different actual import locations;
both must match their independently expected source bytes. CPU timing is NOT_RUN:
fixture correctness is not a model latency benchmark.

## Resource provenance

Retain the original measurement artifact, metric, unit, scope and method. Latency
requires the actual imported source/wheel, checkpoint, runtime/dependencies,
hardware, threads, warmups/repetitions, batch and stream shape, timed boundary and
any synchronization. p50/p95, peak memory, tensor-state bytes, total/shared/active
parameters, training/tuning/inference costs and energy are distinct quantities.
Do not derive p95 from p90, turn logical bytes into peak RAM, or use equal optimizer
steps as evidence of equal FLOPs. Missing values remain unknown, not zero.
Version one supports fixed units for p50/p95 latency, state/peak-memory bytes,
parameter counts, CPU-core-seconds, FLOPs and joules. It does not add observations
or infer billing: repeated metric/scope/content observations are rejected, while
one source measurement bundle may support distinct p50 and p95 values. One artifact
ID cannot name inconsistent content. Cost
normalization, shared-charge allocation and genuine training-resource reports
remain with LE-002, not this inference-oriented adapter.
Known timing additionally requires the retained import-observation reference,
actual imported implementation path and source reference, which must bind the
run's **source**, not merely its receipt-conversion adapter. These are declared
external observations unless separately executed and checked; no path, receipt
or hash grants authenticated execution. Missing timing provenance stays unknown.

The historical CAP006 diagnostics used Python 3.12.14, Torch 2.5.1+cpu, NumPy 2.3.5,
one thread on an AMD EPYC 9V74, batch one, 21 steps, eight warmups and 50 repetitions.
The archive reports medians and p10/p90, **not p95**, and excludes some operator
work, Python heap overhead, energy and peak RAM. Importing those values would be
historical externally reported evidence, never a new local benchmark. This slice
does not import or redistribute that private archive.

## Seven-family integration plan (not executed here)

| Family | State/component boundaries | Decisive comparisons and reporting |
| --- | --- | --- |
| PSN Lite/Full | Trace, prototype memory, admission, native veto | Query erasure versus retrained no-memory; supplied eligibility equalized; forced overwrites; exact answers, coverage and GRU/exact-store controls |
| Bounded field | Recurrent field, graph, leak and readout | Diagonal/leaky/GRU controls; delay, quantization/noise and whole-answer margins; bounded state is not safety |
| USEF-X | Router, specialist population, optimizer ownership, memory | Fixed stream independent of model RNG; fixed pool/frozen ecology/random growth; post-shift error, forgetting and active/total cost |
| ATLAS-CASSA | Geometry, particles/swarm, engrams, RNG | Matched Euclidean/hyperbolic-only/no-memory/no-swarm; held-out subtrees and relation families; no unsupported stability certificate |
| PSN2 | Node bank, pulse/replay, decoder/copy path | Same decoder and matched capacity; node/pulse/replay controls; exact transformed-grid completion |
| DPSL | Embedding owner, prototypes, graph/eviction, persisted state | Fixed encoder/bytes; flat index/LRU/LFU controls; exact retrieval, stale replacement/deletion and restart |
| NSF-v8/NFD | Field, plasticity/topology, readout, RNG | Predict before feedback; frozen/no-plasticity/random-rewiring/history controls; external error and recovery, not intrinsic telemetry |

The first integration acceptance is that independently retained receipts for each
family can be represented without inventing training, exactness, execution or
resource evidence. Real adapter execution and scientific comparisons remain
separately authorized research. No common leaderboard should combine incompatible
tasks. A useful internal tool does not establish customer demand or willingness to
pay; those require a separately authorized user-workflow study.

## Privacy and verification

Raw `model_dump()` and local import paths are evaluator material, not public export.
This initial adapter is unconditionally evaluator-private, including constructed
reports. Public/buyer-safe projection withholds the complete record and its IDs;
the shared envelope is operator-private OBSERVED. Do not publish private archive
names, targets or IDs. A future public projection would require its own contract.

Verification expands from constructed focused tests to the full repository suite,
changed-file Ruff/Mypy, the existing quality ratchet, package build/metadata and a
clean external-wheel check with actual import provenance. Independent exact-head
review, CI/security and formal approval are separate. No changes to #465, protected
panels, existing provider gates or global roadmap bootstrap are part of this work.
