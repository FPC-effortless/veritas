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
- the PR body still references both the roadmap issue and the trusted Work ID;
- exact-final-head decisive review state contains no current `CHANGES_REQUESTED` and contains an `APPROVED` review from a GitHub identity different from the PR author;
- `Security`, `Python Quality Ratchet`, and `CI` have completed successfully for the exact final head on `pull_request` runs;
- the merge commit is contained in the repository's current default branch.

Missing, malformed, stale, pending, failing, same-account, wrong-PR, wrong-branch, or off-main evidence fails closed.

## Review semantics

The recovery job mirrors the canonical `tools/review_provenance.py` decision boundary for decisive reviews:

- only `APPROVED` and `CHANGES_REQUESTED` are decisive;
- decisive records require exact commit SHA, concrete reviewer login, positive review ID, and timezone-aware timestamp;
- only decisive reviews bound to the exact final PR head participate;
- the latest exact-head decisive state per reviewer wins by timestamp then review ID;
- any current exact-head `CHANGES_REQUESTED` blocks recovery;
- at least one current exact-head `APPROVED` reviewer must differ from the PR author.

## State mutation and failure ordering

On success, recovery changes trusted coordination state from `REVIEW` to `DONE`, replaces `linked_pr_head` with the independently reviewed final PR head, preserves frozen ownership, and records `completion_recovery` with:

- previous handed-off head;
- final PR head;
- merge commit;
- reviewer identity, review ID and timestamp;
- exact required workflow run identities;
- default branch;
- transition sequence.

The trusted local DONE record and `work:done` label are published **before** the global reservation is removed. If later registry cleanup fails, the stale global reservation remains conservative and continues to block overlapping work instead of falsely making the paths free.

Rejections are written to the roadmap issue and the workflow fails.

## Production recovery that motivated this path

ROADMAP-REVIEW-PROVENANCE-002 issue #322 handed off PR #323 at:

`b99ddb78699fbff6b90fe5b05af7f89746c75ab0`

Required synchronization advanced the PR to independently approved exact final head:

`efdc1e40f04dad9477a496bf3c4112455d01e0ff`

GitHub review `5063950731` is `APPROVED` on that exact final head. The PR merged as:

`55812db400bb7614500e9b3e5607a15acf7986b7`

After this recovery implementation is itself reviewed, gated, and merged to `main`, the intended audited reconciliation command on #322 is:

```text
/recover-merged review-provenance-a1 323 reconcile stale handoff to independently reviewed merged final head
```

That command repairs coordination bookkeeping only. It does not create new merge, release, sealed/private-data, paid-compute, scientific, Frontier, training, qualification, deployment, external-account, or commercial authority.
