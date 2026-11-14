# Complete-map reliability and measured session cost

`trainlab.reliability_cost` binds the frozen competence panel to the actual
predictions from one bounded Linux CPU session. Offline replay recomputes query
accuracy and complete-map accuracy from those same outputs. A complete map is
correct only when every declared member is correct. In `fresh_replay` mode its
queries run from separately reset state; it is not an uninterrupted interaction.

## Run and replay

```bash
PYTHONPATH=integrations/trainlab/src python \
  integrations/trainlab/examples/diagnose_reliability_cost.py \
  --root /tmp/veritas-reliability-demo
```

Use a new output directory. The example freezes three constructed controls and
their execution order, then rotates arm order over three repeats (nine sessions).
The correct control passes. The snapshot-LINK fault preserves primitive and COPY
competence but fails LINK. The value-deficient control explicitly corrupts all
outputs. These controls test implementation behavior, not learned architectures.

`run_panel_session(command, root, cwd=..., panel=..., panel_sha256=...,
inputs=..., operations=..., limits=...)` accepts a panel from `freeze_panel` and
exact `{inputs}` and `{predictions}` argv placeholders. Input IDs, order and
content must match the frozen request before execution. Expected answers,
map membership, seed/template requirements and thresholds are saved before launch.
The command writes a JSON list of `{id, answer}` rows in input order.

`read_panel_session(root, manifest_sha256)` needs the externally retained SHA256
of `manifest.json`. It verifies the fixed file inventory, raw receipt and output
hashes, panel/request bindings and saved query score, then independently rescores
the complete maps. It launches no command. Preserve the external pin separately
from the directory; recomputing it from untrusted replacement evidence defeats
the integrity check. Paths are fixed and symlinks are rejected. An archive can be
relocated without changing its manifest; update only reference roots on replay.

Each metric has a distinct workload identity including actual input hashes,
expected answers, map memberships, task/state semantics, operation semantics and
thresholds. Methods may have different model/code/configuration identities, but
each arm must retain the same four identities across its repeated executions.
The identity declarations do not prove which model a command actually loaded.

## Compare at a declared reliability requirement

```python
comparison = compare_at_reliability(
    records,  # {arm, repeat, root: absolute_path, manifest_sha256}
    required_arms=["candidate", "control"],
    required_repeats=[0, 1, 2],
    metric="map_accuracy",
    quality_floor=0.95,
)
```

The exact arm-by-repeat panel is required. Missing, duplicate or reused sessions
raise `LabError`. Each eligible arm must meet both the panel's per-seed/template
competence thresholds and the selected overall quality floor in **every** repeat.
This does not permit a high aggregate score to hide one weak template.

| Result | Interpretation |
| --- | --- |
| `TESTED`, eligible arms present | All sessions complete with matching context; descriptive median costs can be compared among eligible arms. |
| `TESTED`, empty eligible list | Complete comparison, but no arm met the declared reliability requirement. |
| `INCONCLUSIVE` | At least one execution/output is incomplete; no lowest-cost arm is reported. |
| `FAILED` | Workload, hardware or cost boundary differs; no lowest-cost arm is reported. |
| `LabError` | Invalid panel/references, missing repeats, reused execution, changed evidence or inconsistent bindings. |

Raw elapsed times and observed totals include failed attempts. Median/min/max
are reported only for arms with all repeats complete. A failed arm blocks the
global ranking; it cannot appear cheap by excluding its failed work. Ties retain
all eligible arms at the exact lowest median. Repeats are separate planned
executions, not retries or independent training seeds. Retry-to-success cost and
whole research campaign cost are not computed here.

## Measurement and evidence limits

The inherited CPU session boundary includes supervisor/worker startup, imports,
the command's loading/encoding/inference/output writing and teardown. Panel/input
preparation, final receipt serialization, scoring, replay and manifest creation
are excluded. The raw receipt records its precise boundary, hardware, applied
limits and usage. Model-only inference latency, GPU synchronization/cost, energy,
aggregate process-tree memory and billing are not measured. Tiny constructed
sessions are dominated by startup and are not a useful architecture speed test.

Commands must be trusted, synchronous CPU programs without remote/detached work;
resource limits are not a security sandbox. Pins protect retained evidence from
changes relative to a trusted external pin, not from a dishonest producer who
rebuilds all evidence and pins. Chronological preregistration, independent groups,
actual reset semantics and truthful source/checkpoint identities are not attested.
Supervisor interruption can leave raw files without a finalized manifest; this
module does not reconstruct an interrupted run or silently assign it a result.

The API reports descriptive costs on this exact panel, no confidence intervals,
causal architectural attribution or general speedup. `TESTED` denotes completion
of the stated computation, not scientific qualification. No CSM/SlotStore quality
or latency claim follows from this implementation's constructed controls.
