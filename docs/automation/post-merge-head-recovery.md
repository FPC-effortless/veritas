# Post-merge exact-head completion recovery

`/done` is intentionally strict: a REVIEW lane may complete only when the merged PR head is exactly the head recorded by `/handoff`. If the PR head changes after handoff, `/done` rejects rather than silently rewriting trusted review identity.

That invariant creates one narrow recovery case. A PR can require current-main synchronization after handoff, receive fresh independent review and all required gates on the synchronized final head, and then merge before trusted coordination has recorded that final head. Because `/handoff` accepts only an open PR, ordinary commands cannot repair the stale handoff after merge.

## Command

```text
/recover-merged <agent-id> <pr-number> <reason>
```

This command is implemented as a separate default-branch `issue_comment` job in `Agent Work Claims`. It is not parsed by the ordinary coordinator. GitHub therefore executes recovery authority from the workflow already merged on the default branch; candidate PR code cannot introduce or exercise new recovery authority before integration.

## Authority and preconditions

Recovery is accepted only when all of the following are proven from GitHub and trusted coordination state:

- the comment author has repository `OWNER` association;
- trusted state is `REVIEW` and the supplied agent ID plus GitHub actor are the recorded holder;
- the supplied PR is exactly the PR recorded at handoff;
- the trusted branch is concrete and still matches the merged PR head branch;
- frozen `ownership_paths` are present and well formed;
- the trusted handoff contains a full 40-character SHA;
- the PR is closed and merged;
- the final PR head and merge commit are full 40-character SHAs;
- the final PR head differs from the stale handed-off head; if it does not differ, ordinary `/done` remains the only completion path;
- the PR body still references both the roadmap issue and the primary trusted Work ID;
- exact-final-head review provenance satisfies the canonical `tools/review_provenance.py check` authority, including either a distinct-identity exact-head `APPROVED` review or a canonical clean exact-head agent-session `COMMENTED` review, with blocking evidence still fail-closed;
- `Security`, `Python Quality Ratchet`, and `CI` have completed successfully for the exact final head on `pull_request` runs;
- the merge commit is contained in the repository's current default branch.

Missing, malformed, stale, pending, failing, blocking, wrong-PR, wrong-branch, or off-main evidence fails closed.

## Review semantics

The recovery job does not maintain a second review-policy implementation. It invokes the already-canonical `tools/review_provenance.py check` against the merged PR's exact final head and consumes its machine-readable PASS output for reviewer identity and review ID.

This keeps recovery aligned with normal Security review provenance:

- exact-head current `CHANGES_REQUESTED` blocks;
- a canonical exact-head blocking agent review blocks;
- malformed or stale review identity fails closed;
- inline findings attached to an agent review block that review;
- a distinct-identity exact-head approval is accepted;
- a canonical clean exact-head agent-session COMMENTED review is accepted under the same operational-independence boundary documented by `docs/automation/review-provenance.md`.

The canonical checker remains authoritative. This recovery path does not modify or widen it.

## State mutation and failure ordering

On success, recovery changes trusted coordination state from `REVIEW` to `DONE`, replaces `linked_pr_head` with the canonically reviewed final PR head, preserves frozen ownership, and records `completion_recovery` with:

- previous handed-off head;
- final PR head;
- merge commit;
- canonical reviewer identity and review ID;
- exact required workflow run identities;
- default branch;
- transition sequence.

The trusted local DONE record and `work:done` label are published **before** the global reservation is removed. If later registry cleanup fails, the stale global reservation remains conservative and continues to block overlapping work instead of falsely making the paths free.

Rejections are written to the roadmap issue and the workflow fails.

## Production cases

The original ROADMAP-POSTMERGE-RECOVERY-001 path was motivated by ROADMAP-REVIEW-PROVENANCE-002/#322 and PR #323, where a stale handed-off head had to be reconciled to a later independently approved merged head.

After the canonical review-provenance policy was generalized by ROADMAP-REVIEW-PROVENANCE-004 / PR #361, ROADMAP-001/#152 exposed a policy-drift regression in that recovery path. PR #354 was handed off before its final synchronization, then reached final exact head `0f2ff2930887f2a9669f166bf98867f139379b69`, received a canonical clean exact-head agent-session review, passed exact-head Security, Python Quality Ratchet, and CI, and merged. Ordinary `/done` correctly rejected the stale handoff and ordinary `/handoff` correctly rejected the already-merged PR, but `/recover-merged` still required the obsolete distinct-identity approval-only rule.

This repair makes `/recover-merged` consume the same canonical provenance authority as Security while preserving every other recovery precondition.

After this repair is itself reviewed, gated, and merged to `main`, the intended audited reconciliation command for #152 is:

```text
/recover-merged chatgpt-sol-gold10-pilot 354 reconcile stale pre-sync handoff to canonically reviewed merged final head
```

That command repairs coordination bookkeeping only. It does not create new merge, release, sealed/private-data, paid-compute, scientific, Frontier, training, qualification, deployment, external-account, or commercial authority.