# Independent review provenance

Veritas uses exact-head independent review as an implementation acceptance boundary.
This document defines the identity rule that the repository can actually verify.

## Canonical rule

Merge-authoritative independent review requires an `APPROVED` GitHub pull-request
review that:

- is attached to the exact current PR head SHA;
- has a concrete reviewer GitHub login;
- comes from a GitHub identity different from the PR author;
- has valid review identity and timezone-aware submission metadata; and
- is not superseded by a later exact-head `CHANGES_REQUESTED` review from that
  reviewer.

Any current exact-head `CHANGES_REQUESTED` state blocks the provenance gate until
it is superseded or dismissed.

`tools/review_provenance.py` is the machine implementation of this rule.

## Same-account agent reviews

A separate agent or fresh session operating through the same GitHub account may
still provide useful semantic review evidence. That evidence is not
merge-authoritative independent review.

GitHub does not expose a trustworthy session or agent-lineage identity behind a
shared account. An implementation session could claim a different lineage string
in prose or JSON. The repository therefore cannot turn phrases such as
"independent session", "fresh reviewer", or a self-asserted agent ID into
independent-review authority.

This is an epistemic boundary, not a judgment about the quality of a same-account
review. Such reviews can find blockers and should be retained, but they do not
satisfy the independent-review gate.

## Exact-head behavior

An approval on an older head is stale immediately after the PR head changes.
The checker never carries approval forward to a new commit.

For each reviewer, the latest decisive exact-head review wins. Review ordering is
based only on validated timezone-aware submission time and positive integer
review ID. Missing or malformed decisive metadata fails closed rather than being
reconstructed or defaulted.

## Security enforcement

The repository's required `Python source security` and `Node dependency audit`
checks run their existing security scans first. On pull requests they then run the
review-provenance checker. A missing or invalid independent review therefore makes
the required context fail; it does not skip the underlying security scan.

A submitted or dismissed PR review triggers the default-branch Security workflow.
That event cannot itself create a useful required check on the PR head, so the
workflow uses its `actions: write` permission only to re-run the latest completed
Security run already associated with that exact PR head. The re-run queries the
current review state and updates the existing PR-head required contexts.

Push, schedule, and manual Security runs do not require PR review provenance.

## Operational consequence

Repositories operated through one author account need a distinct GitHub reviewer
identity or review-capable GitHub App before merge-authoritative independent
review can be satisfied. Until such an identity is available, a clean same-account
agent review is evidence but the merge remains blocked.

PR #315 is the motivating historical case: its same-account review records remain
part of the audit trail, but the wording of those records is not reusable as
canonical independent-review authority under this policy.
