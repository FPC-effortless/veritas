# Execute paired benchmark controls

TrainLab can run two stateless reference functions and a declared shortcut
against paired original and intervened inputs. A frozen panel binds exact
case IDs, declared groups, inputs, expected outputs, coverage requirements,
the shortcut-accuracy ceiling and three declared implementation digests.
Keep the panel hash alongside its source evidence.

```bash
python integrations/trainlab/examples/diagnose_benchmark_execution.py +  --root /tmp/veritas-executed-benchmark-controls
```

The public replay runs a forward-state reference, a backward-history
reference and a latest-SET shortcut. It checks snapshots and single-hop
live references following source deletion and recreation. Two declared
groups provide changing and invariant answers. A separate control exposes
the expected answer to a shortcut. The clean panel omits that value.

| Control | Expected result |
| --- | --- |
| Two matching reference implementations | 24 observations, no findings |
| Wrong reference response | Reference expectation and parity findings |
| Too few changed and invariant groups | Insufficient group coverage |
| Shortcut can read expected answers | Shortcut accuracy exceeds its ceiling |
| Two-call budget | Inconclusive, two of 24 calls observed |

`freeze_panel` accepts up to 64 finite-JSON paired cases. `execute` checks
the pin and runs trusted callbacks through the existing Workbench. Each
function sees only an isolated copy of one input. The report stores output
hashes rather than output values and preserves invocation and coverage
status. Callback failure, malformed output and detected input mutation
leave an invocation unobserved. An observed disagreement remains a finding
even when a later call budget leaves the panel incomplete.

The Workbench enforces cooperative budgets between operations. A hung
callback needs outer process supervision. The callbacks are trusted code
and can access whatever the process can access. Supplied implementation
digests, declared statelessness and group independence need separate
evidence. The two public references implement the same small scope and the
test checks only its declared expected values and shortcut.
