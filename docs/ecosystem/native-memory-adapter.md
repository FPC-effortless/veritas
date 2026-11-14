# Native token state diagnostics

A trusted synchronous backend supplies an initial-state factory, a token
runner and, when necessary, an explicit state-cloning function.
`TokenMemory` exposes backend state through TrainLab's existing Adapter and
Workbench. The base library imports no model framework.

A token runner receives a tuple of input token IDs and a working state. It
returns one finite JSON answer and the new state. Each update accepts
`{"op":"tokens","tokens":[...]}` and changes live state only after the
callback and output validation finish. Queries operate on copied state.
A same-identity peer can restore an in-memory snapshot and continue from its
own copy. The backend must clone all mutable storage, including native
tensor backing. The adapter rejects a callback that returns the original
object as a clone. Behavioral isolation probes can detect observed aliasing.
This interface trusts the callback to avoid external state or weight mutation.

Independent prediction rows use
`{"id":"example","input":{"history":[[1,2],[3]],"query":[4]}}`.
Every row starts from fresh initialized state, returns the same ID in order
and leaves the live session alone. Calls have bounded token and row limits.
The optional peer must be independently constructed with the same backend
identity. Snapshot ownership is local and in memory. Serialization and
cross-process checkpoint recovery remain separate.

## Run the historical SlotStore checkpoint

Use the previously authorized source directory prepared by the
[changing-state replay](changing-state-replay.md). The example checks the
exact source and checkpoint against their historical SHA256 pins and
loads weights with `weights_only=True`. Install Forge and TrainLab in the
CPU PyTorch environment used for the admitted replay.

```bash
python integrations/trainlab/examples/diagnose_native_memory.py   --source /path/to/extracted-native-replay-source   --root /tmp/veritas-native-memory
```

The example checks token boundaries against the existing replay encoder,
constructs independent source and peer models, and runs the already
implemented lifecycle, restore and prediction conformance checks. It reuses
the model's trained SET and query vocabulary. Source and peer implement two
overwrites, preserve untouched answers, and restore without sharing
observable changes. Separate reset histories check all eight predictions,
and saved predictions are read back and rescored. Both models' state dicts
are compared with their starting tensors.

The report covers a single CPU model and an example SET history. Other
operations need a backend and a frozen protocol that support them. The
example performs no training and does not redistribute model source or
weights.
