# Roadmap completion synchronization

`ROADMAP-CLEAN-001` adds a narrow terminal-state reconciler for roadmap work
whose completion is proved by an exact owner-authored coordination record.

The first implementation supports one completion rule only:

```text
OWNER_EVIDENCE + COORDINATION_OPERATION -> DONE
```

It is not a general merge-to-DONE engine. It cannot infer scientific,
Frontier, training, commercial, release, private-data, paid-compute, or
external-account completion from a merged PR, green CI, labels, issue closure,
or assistant prose.

## Why this exists

Ordinary `/done` correctly requires a merged implementation PR. Some roadmap
items are one-time GitHub coordination operations rather than source changes.
Forcing those items to fabricate a PR leaves completed work permanently
BLOCKED or weakens the ordinary completion rule.

The completion sync preserves `/done` and adds a separate fail-closed path for
an explicitly typed owner-evidence operation.

## Work Contract fields

An eligible issue must declare all of these exact fields:

```text
- **Completion rule:** `OWNER_EVIDENCE`
- **Completion class:** `COORDINATION_OPERATION`
- **Completion evidence comment:** `<positive integer comment ID>`
- **Terminal state:** `DONE`
```

Its Positive ownership must also exactly match one coordinator allow-listed
no-source form, such as:

```text
issue labels/comments for roadmap tickets only
```

Repository-editing ownership, unsupported prose, missing metadata, or another
completion class remains ineligible.

## Evidence and trusted-state checks

Before publishing `DONE`, the reconciler requires:

1. an enrolled open issue with the exact supported Work Contract fields;
2. a trusted bot-authored status whose issue and Work ID match the contract;
3. unowned trusted `BLOCKED` or `READY` state;
4. no actor, agent, branch, linked PR/head, frozen source paths, or prior
   completion event;
5. a non-negative integer transition sequence;
6. the exact evidence-comment ID named by the contract;
7. GitHub `OWNER` author association;
8. a concrete evidence actor and timestamp; and
9. a non-empty comment beginning exactly with `Completion evidence:`.

Missing or malformed decisive metadata fails closed. MEMBER/COLLABORATOR prose,
a different comment ID, an active holder, a mismatched Work ID, or a synthetic
label/closure/PR signal cannot complete the item.

## Publication order and audit

The transition order is:

1. update the existing trusted status to `DONE`;
2. embed `veritas.owner-evidence-completion.v1` with the exact evidence ID,
   owner identity, timestamp, completion class, and transition sequence;
3. reconcile the discovery label to `work:done`;
4. post one deterministic completion audit comment; and
5. close the issue as completed.

Trusted status is therefore visible before labels or closure. If a later step
fails, reopening or rerunning the workflow validates the embedded completion
event against the original evidence comment, repairs labels/audit/closure, and
does not repeat the terminal transition.

## Triggers, serialization, and permissions

`.github/workflows/roadmap-completion-sync.yml` runs after:

- pushes to `main`;
- enrolled issue creation, edit, or reopening;
- a newly posted `Completion evidence:` comment;
- successful completion of the canonical `Agent Work Claims` workflow; and
- explicit `workflow_dispatch`.

It shares the non-cancelling `agent-work-coordination` concurrency group with
claim and dependency reconciliation. This prevents intentional overlap with a
claim/release/handoff transition and closes the event-ordering gap where
completion reconciliation could run before automatic enrollment publishes
trusted state.

Permissions are limited to:

```text
contents: read
issues: write
```

There is no contents write, Actions write, pull-request write, deployment,
package, release, secret, payment, external-account, or training authority.

## Live acceptance case

`ROADMAP-CLAIM-BOOTSTRAP` / #216 is the initial acceptance case. Its Work
Contract names owner-authored evidence comment `5465338154`, and its trusted
state is unowned `BLOCKED` with no source reservation or linked PR.

After this implementation is merged and triggered, #216 must become trusted
evidence-backed `DONE`, retain an auditable reference to comment `5465338154`,
receive `work:done`, and close without a fabricated PR. If any of those checks
fail, `ROADMAP-CLEAN-001` is not complete.

## Evidence boundary

This path records completion of an explicitly typed coordination operation
only. It grants no merge, release, qualification, sealed/private-data,
paid-compute, deployment, external-account, scientific, Frontier, training, or
commercial authority.
