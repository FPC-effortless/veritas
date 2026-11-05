# Research Departments and Heads Council

Status: **18 departmental head ROLE seats + asynchronous council ledger**.
This is not 18 independently running agents, an authenticated meeting of
18 peers, a persistent host, or a scientific qualification. Independent head
sessions must be established and verified separately.

The direction identities, hypotheses and scientific gates remain in
[frontier_unified_program.json](examples/frontier_unified_program.json).
The 18 council role IDs are checked against that canonical list in tests.

## Departments and head responsibilities

| Head role | Department | Main sharing responsibility |
|---|---|---|
| head.TAC_CORE | Persistent backbone | Matched model, state and training contracts |
| head.PSN | Selective persistent memory | Retrieval and edit controls |
| head.PSN2 | Neural population communication | Compositionality and routing checks |
| head.DPSL | Graph and editable memory | Deletion and supersession tests |
| head.BOUNDED_FIELD | Recurrent neural dynamics | Long-delay stability and addressing |
| head.ATLAS_CASSA | Geometric transport | Transport, geometry, OOD ablations |
| head.USEF_X | Specialist computation | Routing and interference studies |
| head.NSF_V8_NFD | Plasticity and neural fields | Adaptation/retention contrasts |
| head.FLOCK_COLLECT | Corrective and collective memory | Load-length/overwrite/wrong-key failures |
| head.SSA | Sparse structure selection | Selection controls, tested kernels |
| head.PRS | Persistent role-state routing | Causal routing and bounded compute |
| head.SCM_SIE | Executable structures | Blind composition and repair checks |
| head.GEOMETRIC_KAKEYA | Geometric representation | Geometric inductive-bias evidence |
| head.TOKENIZATION | Tokenization and representation | Byte/latent input interfaces and failures |
| head.LEARNING_OBJECTIVES | Objectives and optimization | Equal-backbone/data objective comparisons |
| head.GPU_KERNELS | Runtime and acceleration | Kernel/throughput/gradient correctness |
| head.MEMORY_GOVERNANCE | State provenance | Temporal integrity and retraction |
| head.TAC_OCR | Document and OCR transfer | Real-image grounding and multilingual tests |

Each head owns its exact source/evidence pins, falsifiable next tests, negative
results, resource request, blockers, and concrete offers/requests to peers.
No head may claim another department's work or revise protected evaluations.

## Recurring coordination

**Daily asynchronous council**: weekdays, approximately 18:00 Africa/Lagos.
The existing Research Lab director remains the execution/research scheduler;
the separate council automation coordinates cross-department information.

1. Collect the latest note from each department. Missing notes are
   NO_SUBMISSION; a coordinator synthesis is NOT a message from a head.
2. Share only changed, evidence-linked findings and failures, plus at most
   three consequential help requests. Do not manufacture new department reports.
3. Route a request to its named target head. Responses reference the
   request ID and are RESPONSE_REPORTED_UNVERIFIED until separately reviewed.
4. Identify duplicate work, source/compute conflicts, reusable benchmarks,
   missing controls, and potential new *preregistered* integration tests.
5. Record dated safe-to-share minutes in issue #482 only when substantive.
   Private source, keys, protected TEST and private identities stay private.

**Friday extended technical council**: compare failures, rejected hypotheses,
credible baselines, shared tools, cross-lane connections, and integration tests.
Decide on any proposal for extra coordination only after #493 demonstrates
independently accepted throughput improvement at comparable cost.

**Meeting output**: report coverage, exact source pins, requests and recipient,
answer evidence, unverified vs reviewed status, accountable role, blockers,
decisions (proposals only), and next authorized action. The scheduler must
not treat the meeting digest as a live multi-agent conversation.

## Local council commands

    research-lab --root .trainlab/labos council roster
    research-lab --root .trainlab/labos council post /private/department-note.json
    research-lab --root .trainlab/labos council meet 20261105.council
    research-lab --root .trainlab/labos council latest

The post operation is append-only: mutated IDs fail. Each meet freezes the
latest submitted note per department; repeated meeting IDs return the original
snapshot, even if newer notes arrive. Reports older than seven days are
marked STALE_NOTE_NOT_CURRENT_SUBMISSION rather than current head activity.
It writes SQLite and event-chain entries
but creates no jobs, workers, paid reservations, or approved scientific claims.
The local event chain is not an external tamper-proof receipt. Do not publish
the raw DB or unsanitized council notes.

### Example note (illustration only, not authentic evidence)

~~~json
{
  "schema": "research_lab.department_note.v1",
  "id": "PSN.20261105.01",
  "department": "PSN",
  "head_role": "head.PSN",
  "reporter_principal": "psn.operator",
  "source_pin": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "stage": "SOURCE_RECOVERY",
  "summary": "Source-only method comparison; no trained-model claim.",
  "negative_results": ["No independent acceptance recorded."],
  "blocker": "Needs an exact-source reviewer.",
  "help_requests": [{
    "id": "PSN.binding-review",
    "target": "FLOCK_COLLECT",
    "question": "Are the wrong-value binding fixtures reusable?",
    "expected_artifact": "Source-pinned fixture mapping",
    "evidence_ref": "EXAMPLE_ONLY"
  }],
  "shares": [{
    "target": "DPSL",
    "finding": "Potential revision/rollback acceptance criterion.",
    "evidence_ref": "EXAMPLE_ONLY"
  }],
  "responses": [],
  "next_action": "Review the frozen source.",
  "observed_execution_id": "NONE",
  "review_receipt": "NONE"
}
~~~

The source hash, finding and evidence references in this example are
placeholders; the example MUST NOT be registered as a scientific result.

## Actual-live-head qualification

A live head requires a distinct operating model/session and audited role
identity, scoped work authority, durable private communication, evidence
and source pins, real process/host liveness, reviewer separation and
restart/restore proof. A ChatGPT scheduled council review only produces
asynchronous notes and is not such proof. Existing author/reviewer scientific
and protected-benchmark gates remain mandatory. The single-owner default
and #493 coordination scaling gate remain in force.
