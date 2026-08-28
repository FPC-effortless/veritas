# Executable environment templates

These examples are small, deterministic references for the merged public environment-authoring and
operational-runtime APIs. They are deliberately examples, not production environment conversions.

Install from this directory after installing Veritas:

```bash
python -m pip install .
```

Then import `veritas_environment_examples` and call any `run_*` function. Every example constructs a
canonical episode with `investigation_world.authoring.EnvironmentBuilder`, executes actions through
the public `investigation_world.operational.OperationalRuntime`, and submits to the canonical
structured verifier.

| Example | What it demonstrates |
| --- | --- |
| `minimal_typed_tool` | Pydantic-validated tool input before a typed runtime action |
| `file_backed` | JSON file evidence read from a real filesystem |
| `sql_backed` | deterministic SQLite-backed evidence |
| `network_api_backed` | a real localhost HTTP API with no external-network dependency |
| `native_artifact_backed` | a real XLSX workbook read with OpenPyXL |
| `hierarchical_observation` | nested public observation fields preserved through runtime payloads |
| `structured_grader` | targets, invariants, required action order, forbidden actions, and evidence |

## Deliberate safety and qualification boundary

A passing example proves only that the example's declared deterministic contract executes against the
current public runtime and verifier. It does **not** prove scientific qualification, Frontier
usefulness, safety, realism/fidelity, training value, commercial readiness, or release authority.

The examples use synthetic data and local resources. They do not endorse the illustrated domain
actions as real-world procedures. The HTTP example binds only to loopback and does not call an
external service.

## MachineExperience example

DX-003 requires a MachineExperience-ready example only after the canonical MachineExperience API is
merged. That dependency is still under review in PR #149 at the time of this template release, so no
example here imports or copies its unmerged contract. Add that example in a follow-up after the
dependency lands rather than creating a parallel schema.
