# Exact-head review freshness queue

`ROADMAP-FRESH-002` adds a read-only queue for identifying pull requests whose review evidence is already stale relative to the current PR head or base branch.

## Why this exists

Veritas intentionally requires exact-head evidence. That protects correctness, but high parallelism can create review churn: `main` moves, an otherwise good PR becomes behind its base, the branch synchronizes, and prior exact-head review no longer applies to the new head.

The freshness queue makes that state explicit before another review cycle is spent on an outdated candidate. It is observability, not a merge train.

## States

- `STALE_BASE` — the PR head is one or more commits behind its current base branch. Review history is deliberately not evaluated because synchronization must happen first.
- `DRAFT` — the PR is current with its base but is still a draft. Review history is deliberately not promoted.
- `CHANGES_REQUESTED` — at least one reviewer's latest decisive review on the exact current head requests changes.
- `STALE_REVIEW` — the branch is current with its base and has visible approval history, but no approval is anchored to the exact current head.
- `NEEDS_REVIEW` — the branch is current with its base and has no visible approval history that establishes the current head.
- `CURRENT_REVIEW` — at least one reviewer's latest decisive review on the exact current head is `APPROVED`, with no current-head reviewer still in `CHANGES_REQUESTED` state.
- `UNKNOWN` — GitHub did not provide enough valid comparison/review metadata to classify safely.

`CURRENT_REVIEW` is intentionally narrow. It says only that GitHub exposes an approval object anchored to the exact current commit. It does **not** establish reviewer independence, all required approvals, CI/security success, conflict freedom, work-contract completion, merge authority, release authority, or any scientific/commercial qualification.

## Draft-state boundary

Draft state is fail-closed input. GitHub must provide `draft` as an actual JSON boolean. Missing, `null`, numeric, string, or otherwise malformed draft metadata makes the entry `UNKNOWN`; it is never coerced to non-draft. This prevents malformed metadata plus an exact-head approval from being promoted to `CURRENT_REVIEW`.

## Merge-state metadata

The report also reads GitHub's detailed PR `mergeable` and `mergeable_state` fields and displays them beside freshness. These values are diagnostic metadata only. A `clean` or `mergeable=true` observation never upgrades `CURRENT_REVIEW` into an integration-ready or merge-authorized state, and `null`/unknown mergeability remains visibly unknown.

The detailed PR snapshot must still contain the same base and head SHAs observed in the open-PR listing. If the PR moves between those reads, the reporter fails that entry closed to `UNKNOWN` rather than combining metadata from different candidate heads.

## Workflow

`.github/workflows/review-freshness.yml` runs on demand and after pushes to `main`. It has only:

- `contents: read`;
- `pull-requests: read`.

The workflow does not push, rebase, merge, label, comment, dismiss reviews, update issues, or modify coordination state. It writes a Markdown job summary and retains JSON/Markdown report files as a short-lived workflow artifact.

## Exact-head semantics

The reporter compares each open PR's current base SHA to its current head SHA through GitHub's compare API. A positive `behind_by` always yields `STALE_BASE`.

For a current, non-draft branch, review objects are inspected by exact `commit_id`. Approval on an older commit is never reused as exact-head approval after the branch moves. For each reviewer, the latest decisive current-head review (`APPROVED` or `CHANGES_REQUESTED`) wins; any remaining current-head `CHANGES_REQUESTED` state prevents `CURRENT_REVIEW`.

Every decisive review must carry a full commit SHA, a concrete reviewer login, a positive integer review ID, and a timezone-aware ISO-8601 submission timestamp. Those fields are validated before current-head filtering, so malformed decisive evidence on either the current or an older head makes the PR `UNKNOWN`. The queue never synthesizes reviewer identity, review ID, timestamp, or commit identity.

Every returned review object must also have a recognized GitHub review state (`APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`, `DISMISSED`, or `PENDING`). A missing, non-string, or unknown state makes the entry `UNKNOWN`; it is never silently discarded beside otherwise valid approval evidence.

Missing or malformed comparison state, missing/malformed draft state, malformed candidate identity, or a PR that moves during candidate snapshot collection yields `UNKNOWN` rather than a positive freshness state. Mergeability itself is not a freshness gate; it is reported separately because it is neither review evidence nor merge authority.

## Output stability

The report contains no wall-clock timestamp. Given the same GitHub PR/compare/review snapshot, its content and ordering are deterministic. Entries sort by conservative freshness state and then PR number.

## Evidence boundary

This queue is coordination observability only. It does not modify Veritas's exact-head review policy and does not grant merge, release, sealed/private-data, paid-compute, external-account, scientific, Frontier, training, or commercial authority.
