# LABOS001 outcome contract

Primary class: feature / research operations integration.

Requested outcome: connect the existing incubated TrainLab and Forge packages to
a persistent, recoverable research-program controller covering direction, role
dispatch, frozen experiments, resource accounting, evidence, independent review,
replication, literature, synthesis, observability and publication preparation.

Owned surfaces: `integrations/research_lab/**`, its additive CI workflow, and a
README link. Existing Veritas qualification and release semantics are unchanged.

Acceptance:

1. Three separately authored falsifiable proposals are ingested without manually
   copying their scientific context between workers.
2. A frozen bounded CPU program executes candidate/control pairs through the real
   TrainLab runner, preserves all attempts, and resumes its queue after restart.
3. Atomic resource reservations prevent oversubscription and budget overcommit;
   unknown worker liveness never silently authorizes duplicate execution.
4. A separate worker replays the exact input closure in a clean directory.
   Self-review, missing seeds, altered evidence and stale review are rejected.
5. The knowledge graph preserves negative/conflicting findings and their sources;
   synthesis reports uncertainty, limitations and the next discriminating test.
6. A read-only live dashboard and an inspectable publication bundle expose the
   same durable state. Publication requires an explicit operator action.
7. Seven architecture groups from ARCHPAR001/002 enter a research backlog with
   their actual unresolved questions; no fabricated training result is added.

Falsifiers: concurrent claims of one job, a cap exceeded by reservations, mutable
inputs accepted, unknown execution retried, missing controls/seeds accepted,
self-review accepted, or a constructed run promoted to scientific qualification.

Reuse: TrainLab executes and verifies trusted local recipes; Forge validates its
own dataset format. SQLite supplies queue transactions. The controller owns only
the missing cross-program state and evidence relationships. No new trainer,
model-serving stack, cloud provisioning or general-purpose agent framework.

Evidence boundary: engineering demonstrations use explicitly constructed symbolic
fixtures. Separate agent sessions are operational identity assertions, not distinct
cryptographic identities. Clean replay is not external scientific replication.
Paid compute, deployed workers, source rights and external publication remain
separate observed capabilities, never inferred from local tests.
