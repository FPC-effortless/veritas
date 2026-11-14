# Replay a minimized state answer mismatch

TrainLab can reduce an observed scalar or structured answer mismatch by
deleting events and top-level fixture fields. Supply one bounded finite
JSON case with `fixture`, `events` and `query`. Supply distinct trusted
candidate and reference functions. Each receives a fresh copy of the case
and starts from its own initial state. Register both with externally
retained source identities.

```python
from trainlab.failure_replay import reduce_failure, replay

implementations = {
    "candidate": {"sha256": candidate_sha256, "simulate": candidate_simulator},
    "reference": {"sha256": reference_sha256, "simulate": reference_simulator},
}
reduction = reduce_failure("new-reproducer", case, implementations, max_calls=80)
pin = reduction["reproducer_sha256"]
if pin is not None:
    observation = replay("new-reproducer", pin, implementations)
```

`reproducer.json` stores data and two observed output hashes. It contains
no executable callback paths, commands or plugins. Keep its returned
SHA-256 outside the directory. To replay after copying it to a fresh
directory, provide the expected pin and register the local implementations
again. Changed bytes, unsupported schema and mismatched implementation
identities are rejected before callbacks run. A different mismatch stays
inconclusive. `FAILED` with `exact_witness=true` reproduces the original pair.

The reducer preserves the exact candidate and reference output hashes.
It reports one-deletion minimality when no single event or top-level
fixture field can be removed with that witness under fully observed
trials. This is a greedy search. A smaller joint deletion can still exist.
The budget counts paired simulator probes. Time limits are cooperative.
When the budget expires, the last observed failing case still exports.

Initialization, execution and output behavior depend on the trusted local
callbacks. Source identity is an operator declaration. This workflow
expects reproducible simulators. Bundle cases may contain task data, so
export only examples you are authorized to share.

The focused acceptance controls execute a stale-delete model, reduce its
failure from two events and two fixture fields to one of each, and verify
the exported case with a fresh callback invocation.
