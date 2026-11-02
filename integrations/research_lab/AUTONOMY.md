# Bounded autonomous execution

Outcome contract: a reviewed result must produce one durable decision, then
at most one next frozen experiment, without an operator copying a plan into the
queue. Missing replay/review, failed work, changed inputs and depleted budgets
must remain visible. Two experiment processes must actually execute in parallel;
an idle worker restart must preserve queued work and produce a new heartbeat
session. A false scientific claim is a failure even if the software runs.

The new POSIX `activate`, `dispatch` and `supervise` commands reuse the existing
protocol registry, TrainLab execution, resource reservations, replay, independent
review and research graph. No additional database or scheduler service is needed.
`status` and the observatory report lane state/reason and recent worker heartbeat,
PID, hostname and session. A heartbeat is a process observation, not independent
proof of computation or remote-host identity.

## Freeze and activate a lane

The explicit `research_lab.autonomy.v1` contract contains:

- `id`, `program`, `initial` profile and integer `max_rounds` (1–100).
- `profiles`: names mapped to `protocol` JSON paths and `transitions`.
- Each transition must specify `BOUNDED_CONTRAST_SUPPORTED` and
  `BOUNDED_CONTRAST_NOT_SUPPORTED`, each targeting another admitted profile or
  `null` to stop. A negative result is retained and can select a repair experiment.
- `director`: `null` for preregistered evidence branching, or a trusted director
  work-order JSON path for model-authored proposals.

`activate` freezes the full admitted input closure and protocols; it starts no
processes. `dispatch` advances every registered lane once. `supervise` calls it
repeatedly and supervises explicit workers with restart backoff and logs. Duplicate
supervisors and duplicate local worker IDs are excluded by process-held locks.
The root must be a local POSIX filesystem with working SQLite and advisory locks.
Use separately configured roots/hosts for remote runners; shared-network filesystem
or cross-host lock coordination is not established by these tests.

```bash
export PYTHONPATH="$PWD/integrations/research_lab/src:$PWD/integrations/trainlab/src:$PWD/integrations/forge/src"
python -m research_lab --root "$LAB" activate path/to/lane.json --recipes path/to/recipes
python -m research_lab --root "$LAB" supervise path/to/workers.json
```

A workers JSON is an array of objects with exactly `id`, `role`, `principal` and
`resource`. Worker registration never establishes genuine session independence.
Use actual separate sessions for replication and review, and declare their true
principals. Review is deliberately excluded from automatic worker execution:
reviewers must submit their own analysis bound to the exact current evidence.

Round decisions persist before enqueueing. IDs are deterministic per lane/round,
so a restart after enqueueing cannot duplicate a generation. Changed policy or
recipe inputs require a new lane identity. Whole-round primary/replay/review
bounds are checked against the program envelope before admission. Native resource
claim accounting remains authoritative when lanes compete. Failed/lost execution
blocks the lane with its task/error; unknown live work is never auto-recovered.
An operator can recover only after proving the previous trainer stopped.

## Connect an actual director provider

Supply an existing trusted provider command through the normal agent work order
and TrainLab recipe. The dispatcher freezes the reviewed synthesis, its exact
`evidence_pin`, and a menu of admitted profiles in `lab_context.json`. The command
must consume that context and write the existing `agent_result.json` contract.
It returns zero proposals to stop or one valid proposal extended with:

```json
{"execution": {"profile": "one-admitted-profile"}}
```

Only the admitted profile supplies code, command, data, resources, seeds, metric,
replay and stopping rules. A provider may refine the question, hypothesis,
predictions and next test, add controls/limitations, and strengthen the minimum
effect. It cannot substitute commands or weaken those gates. Derived authorship
is bound to the actual director task owner's frozen principal, preventing that
principal from replicating/reviewing its own proposal under another alias.
The execution receipt remains agent-authored and unverified until checked.

The provider-path tests use a labelled constructed command. They establish the
proposal bridge, not a live LLM call. No model-provider credential or persistent
host is invented. The native director is a bounded adaptive controller; open-ended
scientific invention, novel architecture design and continuous literature discovery
remain separate provider/deployment capabilities.

## Explicit neural operating acceptance

This is opt-in and excluded from ordinary CI. It needs installed PyTorch; the
package does not add PyTorch as a required dependency. Commit the exact trainer
source first; bootstrap refuses source bytes absent from the named commit.

```bash
python integrations/research_lab/examples/neural_loop_bootstrap.py --root "$LAB"
python -m research_lab --root "$LAB" supervise "$LAB/workers.json"
```

Two primary workers train a standard 96,208-parameter GRU with carried versus reset
state across three fixed seeds. After a genuine separate replay and another
session's exact-evidence review, support selects a longer delay; lack of support
selects a longer training budget. Both branches were frozen before training, and
a two-round bound stops the campaign. Checkpoints contain weights, optimizer and
RNG states; deterministic predictions include a logical tensor hash. Optimizer
resume is not claimed; completed evidence and the queue survive process restart.

The generated copy assay has only 15 possible examples per delay, and train/DEV
examples overlap. These are real optimizer updates and checkpoints, not evidence
of held-out generalization, a TAC-OSM research result or a frontier architecture.
TAC-OSM's own source, parity, reward-verifier, PNDS and compute gates still apply
to every actual TAC lane. A registered frontier backlog is not activated by this
acceptance driver.

## Persistent hosting

`deploy/research-lab.service` is a concrete systemd example. Install the environment,
checked-out source, service account, durable `/var/lib/research-lab` root and
`/etc/research-lab/workers.json` on an authorized persistent host; adjust the explicit
paths, then enable/start the unit there. It uses group termination and restarts
the supervisor. It provisions no host, GPU or provider. The transient interactive
workspace is sufficient to verify operation but cannot establish an always-on
service. Preserve its database, snapshots, runs and logs before leaving it.

Training and provider budgets are bounded by their registered programs. A process
supervisor may poll indefinitely while waiting for genuine review; that does not
authorize new paid compute. No publication, scientific promotion or repository
merge is performed by the dispatcher.
