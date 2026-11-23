# Native latent diagnostics

The latent suite uses the existing `trainlab.research_diagnostics.Adapter` and
`Workbench`. An adapter exposes actual callable capabilities; a model name alone
does not establish them. Missing state/position/readout capabilities remain
`UNSUPPORTED`. These are frozen-model diagnostics, not model-training recipes or
scientific qualification.

## Load a source-compatible research model

The example
[`latent_native_factory.py`](../../integrations/trainlab/examples/latent_native_factory.py)
constructs adapters for the inspected CSM, learned-position Transformer,
scalar-decay gated-delta reference and COG source interfaces. It distributes no
model source, corpus, checkpoint or private data. Place your authorized source
files and checkpoint beside a manifest, declare them as `opaque` artifacts, and
copy the factory into that same input directory. Freeze the manifest before
execution.

```json
{
  "adapter": {
    "path": "latent_native_factory.py",
    "sha256": "<factory SHA256>",
    "factory": "build_adapter"
  },
  "provenance": {
    "native": {
      "architecture": "csm",
      "model_source": "models_source",
      "native_source": "csm_source",
      "checkpoint": "parent_checkpoint",
      "cpu_threads": 1,
      "torch_version": "<exact approved installed version>"
    }
  }
}
```

The three source/checkpoint values refer to **artifact names** in the plan:

```json
{
  "artifacts": {
    "models_source": {"path": "models.py", "kind": "opaque", "sha256": "<SHA256>"},
    "csm_source": {"path": "native_csm.py", "kind": "opaque", "sha256": "<SHA256>"},
    "parent_checkpoint": {"path": "checkpoint.pt", "kind": "opaque", "sha256": "<SHA256>"}
  }
}
```

For CSM/Transformer/gated-delta the model source provides `make(architecture)` and
the checkpoint contains `state_dict`. For COG the model source provides
`LM`, `Config`, `successor_ids`, and `mix`; `native_source` points to its inspected
`vendor/mamba2.py`, and the checkpoint contains `config` and `state`. COG's source
imports `einops`, which must already be available in the approved environment.
The plan's `identities.model` must equal the checkpoint's byte hash.

The factory reads and hashes bytes **before** importing temporary source
snapshots. It loads weights with `torch.load(weights_only=True)`, requires a
finite tensor state dictionary, loads it strictly, puts the model in evaluation
mode and disables parameter gradients. It restores temporary module names after
construction. CPU threads are explicitly bounded to 1–8. There is no optimizer,
implicit download, recursive source discovery, unsafe pickle allowlist or model
code execution during offline reanalysis. Source Python is trusted local code;
hashing does not sandbox it. Native execution requires the suite's explicit
`--allow-native` option and the ordinary trusted-recipe authority boundary.

## Minimal runnable native jobs

A `native.forward` capture returns `logits`, `hidden`, additional `views`, decoder
`context`, the native input digest, and `readout_kind`. COG returns log
probabilities after its successor mixture. The other supplied interfaces return
raw logits. Declare the correct readout kind in calibration/compression jobs.

```json
{
  "jobs": [
    {
      "id": "native-parity",
      "operation": "interventions.native_parity",
      "role": "control",
      "kwargs": {"input_ids": {"artifact": "probe", "key": "input_ids"}}
    },
    {
      "id": "capture",
      "operation": "native.forward",
      "args": [{"artifact": "probe", "key": "input_ids"}]
    },
    {
      "id": "retrieval",
      "operation": "interventions.retrieval_sweep",
      "kwargs": {
        "input_ids": {"artifact": "probe", "key": "input_ids"},
        "anchor": 16,
        "horizon": 8,
        "donor_indices": [1, 0],
        "trained_horizon": 64
      }
    }
  ]
}
```

This fragment assumes exactly two input rows at least 24 tokens long and a CSM
adapter. `anchor=16` means 16 input tokens are consumed before intervention.
The eight subsequent input tokens are the shared true continuation. Supply
`donor_input_ids` instead of `donor_indices` to reconstruct a donor from a frozen
edited history. Donor assignment, input selection and thresholds must be fixed
before inspecting outcomes. Recipe process timeouts supervise the cooperative
Workbench call/time budget.

## Capabilities and diagnostic semantics

| Entry point | Native capabilities | What it measures or controls |
| --- | --- | --- |
| `native_parity` | `native_forward`, `forward`, `readout`; optionally `weights_digest` | Bitwise original/instrumented/decoder replay and unchanged model tensors; missing weights evidence is explicitly null |
| `history_sweep` | `forward` | Fixed donor-prefix or prefix-order interventions, preserving current token, retained suffix, future bytes and absolute positions; hidden response differences remain available for CKA |
| `component_lesions` | `initial_state`, `clone_state`, `step`; state edits additionally `edit_state`, `select_state` | One-step lesions from cached native prestates or persistent edited trajectories; controller-active, proposal-values, history and prior-values removal; donor persistent memory |
| `retrieval_sweep` | `initial_state`, `clone_state`, `step`, `select_state`, `edit_state`, `state_arrays` | Array-only native state reconstruction, state retention, unread-value transplant/zero, self-copy sham, persistent reset and counterfactual state swaps |
| `unread_future` | `clone_state`, `step`, `edit_state`, `state_arrays` | Lower-level in-memory state version of the unread-row future experiment |
| `state_interventions` | `clone_state`, `step`, `select_state`, `edit_state`, `state_arrays` | Frozen-anchor values-only/full-persistent swaps with full-vocabulary output metrics and counterpart replay checks |
| `native_component_sweep` | `native_forward`, `forward_condition` | COG native bank removal, foreign-bank read, successor removal and combined-memory removal |
| `position_sweep` | `forward`, `position_info`, `position_forward` | Explicit learned-position lookup replacements with physical attention order unchanged; recurrent models produce identity aliases using the same native capture |
| `latency_sweep` | `native_forward`, `timed_native_forward`, `weights_digest` | Bounded warmups and repeated actual native forwards, raw durations/median/IQR, repeat-output parity and unchanged tensors; quality qualification stays separate |

`component_lesions` condition values are component-name lists or objects such as
`{"components": [], "state_operation": "foreign_record_memory", "donor_indices": [1, 0]}`.
One-step lesions reset to the cached native prestate at every token. Persistent
lesions instead propagate the edited state. CSM snapshots clone every mutable
values/links/cursor/history tensor. A persistent reset preserves local history
and absolute position while resetting values, links and cursor.

The unread mask is the complement of the **union of cursor, first read, second
read and destination read**. Edits record rows that actually changed, not merely
eligible rows. Both native and edited trajectories are checked for future access
to those initial edit locations. Exact output changes before first access fail
the necessary causal invariant. Access without a useful output change does not
prove successful retrieval. Traces retain first exact change, first KL-threshold
crossing, first access, full KL/total variation curves and primary within-training
horizon flags. Unseen access or change is represented by `-1`, never time zero.

State retention reports values, links, cursor and history separately. Output
sensitivity and stored-state differences remain different observations. Correct
to alternate-answer flip rates use the entire paired panel denominator. NLL and
accuracy always use full native vocabulary; restricted-candidate competence is
handled by the independent scoring module.

CSM `views.full_state` includes the values, links, cursor, local-history tensors
and the absolute integer position, exported as a final float64 scalar per row.
The integer is exact under the adapter's bounded sequence sizes. The earlier
atlas's tensor-only full-state array can still be analyzed as an explicitly
named saved representation; it is not silently treated as position-complete.

`latency_sweep` performs a reference native forward, the explicit warmups, and
the measured repetitions. It times native forward **inside** the adapter, after
input preparation and before numerical output export. Workbench ledger writes
and weight hashing are outside those individual intervals but inside its full
session measurement. CPU completion is declared synchronous; CUDA devices are
synchronized before/after the timed native call. Other backends need an explicit
synchronizer and are refused by this convenience implementation. Median/IQR are
descriptive variability for this exact runtime/workload. A separately evaluated
boolean quality gate is required for `quality_cost_eligible`; absent quality
evidence remains `UNASSESSED`, even when parity and timing succeed.

Position conditions replace only the actual native embedding lookup vector.
They fail if the source stops using its declared monotonic lookup or if IDs
exceed the table. CSM and the supplied gated-delta interface have no learned
position table; their position-only conditions are identity aliases, with no
additional native forward. A stale native input capture cannot be reused as an
alias. Prefix/filler **content** variants still require actual native forwards.

## Other architectures and all historical atlas stages

Use `torch_hook_adapter` for an inspected architecture with an explicit native
forward, readout module, embedding accessor and exact decoder:

```python
from trainlab.latent.native import torch_hook_adapter

adapter = torch_hook_adapter(
    model,
    name="inspected-model",
    forward=lambda x: original_forward_logits(model, x),
    head=model.lm_head,
    embedding=lambda: model.transformer.wte.weight[:2048],
    readout=lambda hidden: 15 * (model.lm_head(hidden)[..., :2048] / 15).tanh(),
    stages={f"block_{i + 1:02d}": block for i, block in enumerate(model.transformer.h)},
)
```

The readout shown is the historical Nanochat vocabulary slice and softcap
pattern. Use it only with the inspected source that actually implements those
semantics. Other models may use biases, additional norms or a different softcap.
The original seven-model extraction's native `forward_logits` callback can be
passed directly. No source-name heuristic substitutes for native parity.

Stages may be modules (tensor output), or a declaration such as
`{"module": model.final_norm, "capture": "input"}` to capture a residual stream,
or `{"module": block, "capture": "output", "select": lambda result: result[0]}`
for a block returning `(hidden, state)`. Repeated decoder-module calls become
separate `_call_01`, `_call_02` views; they are never concatenated onto the token
axis. Stage captures temporarily wrap forward callables and restore their exact
instance state in `finally`. This preserves PyTorch fused Transformer evaluation
dispatch, which ordinary registered stage hooks can disable. Head capture hooks
are removed even after exceptions.

The adapters are synchronous and single-threaded, like the Workbench. They do
not attest arbitrary backend reset behavior, external mutable state, hidden
dependencies, parameter honesty, or data rights. Exact parity is scoped to the
actual input/runtime/batch shape checked; adapter implementation tests do not
establish scientific model competence.
