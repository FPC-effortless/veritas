# Expert Roles and Gold-Standard Task QA

This protocol implements the VQ-006 expert-independence boundary and the VQ-005 task-level QA
process. It is intentionally separate from Frontier Qualification and Training-Value Qualification.
A task may pass expert/task QA and still remain scientifically, frontier, or training unqualified.

## Expert panel

Flagship task QA requires four independent content-bound expert identities:

- `author` — constructs the task and intended capability contract;
- `blind_executor` — attempts the task without the author's preferred trajectory;
- `adjudicator` — resolves disagreements and ambiguity findings;
- `verifier_reviewer` — attacks and replays the reward mechanism independently.

An optional `domain_authority` may be added. Every assigned role uses a distinct opaque expert ID and
a content-bound qualification profile. Unresolved conflicts are rejected before a panel can be
created. The shared models do not store names, contact details, or other unnecessary personal data.

This is deliberately stricter than allowing one subject-matter expert to author, execute, adjudicate,
and qualify the same task.

## Required task-QA stages

The v1 protocol requires evidence for:

1. authoring review;
2. blind expert execution;
3. alternative valid strategy review;
4. disagreement adjudication;
5. verifier attack;
6. ambiguity adjudication;
7. deterministic replay.

Each stage points to a shared content-addressed `EvidenceDependencyRef`. Missing stages remain
`UNKNOWN`; a failed stage forces task-QA failure. Stage reviewer roles are constrained by the
protocol, so for example the task author cannot self-certify the verifier attack stage.

Frontier-model transcript review is intentionally **not** a VQ-005 requirement. That evidence belongs
to VQ-004 Frontier Qualification. Likewise, training improvement belongs to TRAIN-001. This preserves
the distinction between task integrity, frontier usefulness, and training usefulness.

## Metrics and fail-closed gates

`TaskQAMetrics` records:

- blind-execution success;
- disagreements found/resolved;
- alternative strategies reviewed/accepted;
- verifier exploits found/resolved;
- ambiguities found/resolved;
- deterministic replay count and exact-match status.

Qualification requires all required stages, successful blind execution, complete disagreement,
verifier-exploit and ambiguity resolution, an explicit alternative-strategy review, and at least two
matching deterministic replays. Missing measurements are `UNKNOWN`; unresolved findings are `FAIL`.

Finding zero valid alternatives is permitted if the alternative-strategy review itself was performed.
The verifier must accept valid alternatives that are found; VQ-002 remains the authority for verifier
false-positive/false-negative and reward-hack qualification.

## Shared evidence output

A `TaskQAReport` is content-addressed. `task_qa_evidence_record()` wraps the report into the shared
`EvidenceRecord` contract with content-bound environment, verifier, and task subjects plus all stage
evidence dependencies.

This allows VQ-003 scorecards, the staged GOLD-001 program, procurement packaging, and later
qualification layers to consume one evidence identity instead of inventing task-QA-specific evidence
envelopes.

## Gold-program use

The intended staged use is:

```text
10-task protocol pilot
    -> repair QA-process defects
    -> 25-task qualified candidate
    -> 50-100-task flagship only after pilot/candidate gates pass
```

The existence of the protocol does not qualify existing tasks retroactively. Every task needs its own
independent panel, stage artifacts, findings, replay evidence, and content-addressed report.
