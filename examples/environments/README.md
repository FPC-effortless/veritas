# Executable environment templates

These examples are small, deterministic references for the merged public environment-authoring and
operational-runtime APIs. They are deliberately examples, not production environment conversions.

Install from this directory after installing Veritas:

```bash
python -m pip install .
```

Then import `veritas_environment_examples` and call the relevant `run_*` function. Every environment
is authored with the public `investigation_world.authoring.EnvironmentBuilder`, executes through the
canonical operational runtime, and uses the canonical verifier rather than a template-specific
runtime or grading shortcut.

| Example | What it demonstrates |
| --- | --- |
| `minimal_typed_tool` | Pydantic-validated tool input before a typed runtime action |
| `file_backed` | JSON file evidence read from a real filesystem |
| `sql_backed` | deterministic SQLite-backed evidence |
| `network_api_backed` | a real localhost HTTP API with no external-network dependency |
| `native_artifact_backed` | a real XLSX workbook read with OpenPyXL |
| `hierarchical_observation` | nested public observation fields preserved through runtime payloads |
| `structured_grader` | targets, invariants, required action order, forbidden actions, and evidence |
| `authority_sensitive` | delegated authority, hidden preconditions, and a forbidden bypass path |
| `long_horizon_budgeted` | ordered multi-step work with explicit cost/tool-call budgets and headroom |
| `sealed_private_evaluator` | caller-supplied evaluator material that remains absent from the public payload |
| `machine_experience_ready` | a verified episode converted to canonical `TrajectoryV2` and then `MachineExperience` |

## Negative boundaries are part of the examples

The templates intentionally include falsifiers rather than only happy paths. In particular:

- the authority-sensitive task blocks `apply_change` before delegated authority and marks the
  explicit override action forbidden;
- the budgeted task completes its required four-stage path at half of its eight-call/eight-cost
  allowance, then a falsifier consumes the remaining headroom and proves the next probe is rejected;
- the sealed-evaluator task rejects a wrong choice and never checks an evaluator answer into the
  example package; and
- the MachineExperience example emits only public action results into its trajectory, derives its
  public-semantic initial-state digest only from explicitly public task metadata, and remains at
  `E0_TRACEABLE` rather than manufacturing higher learning-readiness evidence.

## Sealed private evaluator

`sealed_private_evaluator.run_demo(private_expected_choice=...)` requires evaluator material to be
provided by the caller. The example package contains no canonical answer. Only a digest is retained
inside private episode metadata, and the demonstration explicitly verifies that the supplied value is
absent from `OperationalRuntime.public_payload()`.

This is a teaching example of the disclosure boundary, not a substitute for Veritas sealed-panel
release or qualification workflows.

## MachineExperience-ready example

The canonical Machine Experience foundation merged in PR #149. The template therefore consumes the
public `machine_experience_from_trajectory()` adapter instead of copying its schema. The environment
executes and verifies first, then a canonical `TrajectoryV2` is constructed from public action
results and wrapped as `MachineExperience` at `E0_TRACEABLE`.

`StateDigest` defaults to public-semantic scope, so this example declares the agent-visible initial
semantic state in public task metadata and hashes that public value. It never derives the public state
digest from `HiddenOracle.initial_state`. A regression varies evaluator-private initial state while
holding the public initial state fixed and requires the public state digest, trajectory ID, and
Experience ID to remain unchanged.

The example does not claim reverification, diagnostics, counterfactual, curriculum, training, or
continual-learning readiness merely because a trace exists.

## Deliberate safety and qualification boundary

A passing example proves only that the example's declared deterministic contract executes against the
current public runtime and verifier. It does **not** prove scientific qualification, Frontier
usefulness, safety, realism/fidelity, training value, commercial readiness, or release authority.

The examples use synthetic data and local resources. They do not endorse the illustrated domain
actions as real-world procedures. The HTTP example binds only to loopback and does not call an
external service. Evaluated agents must not be given direct access to `HiddenOracle`, runtime
`state_snapshot()`, or verifier-only `trace()` data simply because those surfaces exist for harness
and evaluation infrastructure.
