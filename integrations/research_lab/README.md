# Research Lab OS 0.1 — local operating path

Research Lab OS connects the existing TrainLab runner, Forge dataset reader and
Veritas evidence boundaries to a durable program queue. It is an incubated package,
not a Veritas release or a demonstrated autonomous scientist.

## What is implemented

| Requested capability | Executable implementation | Qualification boundary |
| --- | --- | --- |
| Research director | Objective/program records; transparent proposal prioritization; bounded director-provider work orders | Default ranking measures design completeness, not autonomous scientific insight |
| Persistent specialists | Role-specific work orders for director, literature, theory, design, engineering and synthesis; dependency queue; isolated attempt directories | An operator must supply an actual trusted agent command; the package invents no provider or credentials |
| Literature intelligence | Versioned source catalog, retrieval provenance, immutable paper nodes and research links | Catalog import and provider work orders are implemented; continuous live discovery is not demonstrated |
| Experimental design | Falsifiable hypotheses, alternatives, predictions, controls, ablations, fixed seeds, stopping rules and immutable protocol/source snapshots | Structural completeness does not establish good scientific design |
| Compute management | Atomic CPU/GPU slot reservations, program caps, declared rates, measured local GPU observations when available, heartbeat/cancellation and conservative lost-worker recovery | Logical reservations are not cloud provisioning, device isolation or actual provider invoices |
| Research memory | Immutable hypotheses, experiments, papers, evidence, failures and next tests with support/contradiction/supersession links | Literal retrieval is bounded; imported findings retain their source and trust level |
| Replication | Separate-principal replay from clean declared-input directories; all seeds/arms required; preregistered metric tolerances and deterministic artifact checks | Replay shares host/interpreter; clean-environment or external scientific replication is not inferred |
| Live observatory | Read-only polling dashboard, queue, programs, budgets, workers, knowledge and synthesis; existing TrainLab and Forge views | Loopback local deployment uses TrainLab's Host/Origin/CSP boundary |
| Scientific synthesis | Per-seed effects, descriptive range, negative/incomplete/invalid conclusions, exact-evidence review and next discriminating test | Scientific qualification always remains `NOT_QUALIFIED` |
| Publication preparation | Verified allowlisted artifacts, all saved attempts/checkpoints, manuscript draft and SHA256 manifest; atomic local packet creation | No submission, public sharing, source-rights attestation or release authorization |

The seven ARCHPAR architecture groups are imported as a **report-grounded backlog**.
They are not seven newly trained models. The current reports identify specific
unresolved capability gates; those questions remain visible in the dashboard.

## Install and run

From the repository root:

```bash
python -m pip install ./integrations/trainlab ./integrations/forge ./integrations/research_lab
research-lab --root .trainlab/labos init --program memory-research \
  --objective "Distinguish carried memory from addressing shortcuts" --seconds 1800 --cpu-slots 2
research-lab --root .trainlab/labos register path/to/protocol.json
research-lab --root .trainlab/labos worker cpu-session --role experiment --watch
```

Use a second terminal for the observatory:

```bash
research-lab --root .trainlab/labos serve --port 8770 --forge-workspace .trainlab/forge
```

Open `http://127.0.0.1:8770` on the same machine. The research view is read-only;
registered commands run through the operator CLI. It also serves the existing
TrainLab run viewer and, when configured, the existing Forge workspace.

No installation is required for repository development:

```bash
export PYTHONPATH="$PWD/integrations/research_lab/src:$PWD/integrations/trainlab/src:$PWD/integrations/forge/src"
python -m research_lab --help
python -m unittest discover -s integrations/research_lab/tests -v
python integrations/research_lab/examples/run_acceptance.py --root .trainlab/labos001 --run
```

The acceptance driver ingests three proposals written by distinct design-agent
sessions. It freezes each derived engineering protocol before execution, completes
one task, reopens the controller and dispatches the remaining candidate/control
tasks under the same durable queue and budget. It does not silently run review or
claim scientific success.

## Replay, independent review and a packet

```bash
research-lab --root .trainlab/labos001 worker replica-session --role replication
research-lab --root .trainlab/labos001 synthesize LABOS001-causal
research-lab --root .trainlab/labos001 review LABOS001-causal \
  --worker reviewer-session --receipt /private/review.json
research-lab --root .trainlab/labos001 package LABOS001-causal /private/new-packet
```

The reviewer writes a JSON receipt containing `evidence_pin`, `verdict` (`clean` or
`blocking`), `findings`, `summary` and
`independence: "SEPARATE_SESSION_OPERATOR_ASSERTED"`. `evidence_pin()` in
`research_lab.execution` supplies the content identity to inspect. Any current
blocking finding, missing replay, changed snapshot, altered run, stale receipt or
missing seed prevents the supported-contrast state. An unsupported contrast is
retained as a valid negative outcome. Review receipts do not confer publication
authority.

Worker IDs and principals are operator assertions, not cryptographic identities.
Author aliases resolve to an immutable principal at protocol registration. The
same principal cannot author/execute and then replicate or review the same work.
A fresh real session must conduct the independent activity; creating a new string
is not independent review.

## Connect an actual research agent

An agent work order uses `research_lab.work_order.v1` (see `agents.ORDER_FIELDS`).
It names an objective, acceptance conditions, role, resource, recipe and previously
stored context nodes. `order` freezes the selected nodes and pins into
`lab_context.json`; the configured command reads that file in its working directory.
Use your existing model-provider CLI or reviewed Python client as the trusted
TrainLab recipe. No particular provider, browser session or API is assumed.

The command writes finite `metrics.json` values declared by its recipe and
`agent_result.json` with this contract:

```json
{
  "schema": "research_lab.agent_result.v1",
  "role": "design",
  "summary": "Proposed discriminating experiment",
  "findings": [],
  "proposals": [],
  "source_nodes": ["registered-source-node"],
  "next_actions": ["Test the frozen causal intervention"]
}
```

Nested proposals must pass the proposal contract. Completion, indexing and graph
links commit in one transaction. Outputs remain `AGENT_AUTHORED_UNVERIFIED`.
Specialists can run persistently with `worker --watch`; configure a process
supervisor to restart that command on an actual persistent host. The example
role-worker tests use a constructed command, not a live model-provider call.

## Source and infrastructure integration

`import-trainlab` verifies an existing run receipt. `import-forge` uses the real
Forge `Dataset` validator and requires the frozen manifest SHA256. `catalog`
imports primary-source metadata and researcher summaries with explicit limits.
Paper revisions append to the graph rather than erasing prior interpretations.
`woyengi-handoff` creates unverified claim proposals for a separately authenticated
Woyengi host; it does not write to Woyengi or invent host permission.

Register logical GPU inventory with `resource GPU_ID --kind gpu --slots N` and an
explicit declared rate. Paid resources require both an authorized program and a
sufficient micro-USD cap. A reviewed recipe can submit to an existing external
runner, but remote GPU allocation, process termination and checkpoint restore
must be evidenced by that runner. This package does not create cloud accounts,
spend credentials or Kaggle sessions.

## Recovery and accounting

Workers heartbeat during real execution. An expired lease cannot be revived.
Persistent workers reap expired work into `lost`, retaining its slot and full
reservation because liveness is unknown. After proving the previous process has
stopped, `recover TASK --confirmed-stopped` records a conservative full charge and
requeues only if its frozen retry allowance permits it. An unknown worker is never
silently duplicated. Queued work and checkpoints survive controller restart.

Checkpoints are research context and linked artifact references. Actual optimizer,
RNG and model-state resumption requires a trainer that implements and tests it.
The system makes no arbitrary mid-update resume claim.

Program accounting distinguishes reserved slot-wall seconds, charged envelope
seconds, observed duration and overshoot. Rates are declared, not observed
invoices. Trusted recipes enforce their process timeout through TrainLab; filesystem
quota, actual CPU/GPU isolation and external billing require the deployment host.

The runner executes trusted code with the local account's permissions and inherited
environment. It is not an untrusted-code sandbox. Frozen snapshots pin declared
files, not the entire OS or installed dependency graph. Local hashes and an event
chain do not protect against an operator rewriting both database and files. Keep
private/sealed data inside its established boundary; operator packets are not
buyer-safe public releases.

## Remaining qualification work

The local operating path can be verified with constructed diagnostics. Sustained
model-backed scientific planning, recurring literature discovery, live remote GPU
recovery, authenticated Woyengi ingestion, external clean-environment replication
and the seven-lane trained research campaign require their own actual execution
evidence. None is promoted by passing the local implementation tests.
