# Independent review provenance

Veritas uses exact-head semantic review as an implementation acceptance boundary.
The repository supports both multi-identity and single-owner operating models.

## Canonical rule

Merge-authoritative review evidence must be bound to the exact current PR head and
must be free of unresolved blocking findings.

Two evidence paths are accepted:

1. **Distinct GitHub approval** — an exact-head `APPROVED` pull-request review from
   a GitHub identity different from the PR author.
2. **Single-owner agent review** — an exact-head `COMMENTED` pull-request review
   carrying the canonical machine marker as a standalone Markdown line:

   `<!-- veritas-agent-review:v1 head=<40-char-sha> verdict=clean -->`

   The review must have valid GitHub review identity/timestamp metadata, the marker
   SHA must equal the review's exact commit, the summary must not contain a
   `BLOCKING:` finding, and that review may not have inline review comments.

Quoted, inline-code, fenced-code, and indented-code examples of the marker are
non-authoritative and are ignored. Fenced examples remain ignored until a matching
closing fence of the same marker character and at least the opening fence length.
A malformed standalone marker attempt still fails closed.

The distinct-identity path is stronger machine-verifiable identity provenance when
such an identity exists. The single-owner path exists because Veritas is also
operated by multiple coding/review agents through one GitHub owner account.

## What the single-owner marker proves

The repository can verify:

- a concrete GitHub review object exists;
- the review is attached to the exact current head;
- its timestamp and review ID are well formed;
- the reviewer explicitly recorded a clean or blocking semantic verdict;
- a clean verdict has no attached inline finding; and
- the evidence becomes stale immediately when the PR head changes.

GitHub cannot prove that two AI sessions behind the same account are different
processes. Fresh-agent/session independence is therefore an operational assertion,
not a cryptographic identity claim. The marker makes that limitation explicit
instead of pretending a second GitHub login is required for code quality.

Free-form phrases such as "fresh reviewer", "independent session", or "CLEAN"
do not satisfy the gate. The canonical marker is required.

## Blocking behavior

Any current exact-head `CHANGES_REQUESTED` review blocks the gate.

A canonical agent review with
`verdict=blocking` also blocks the gate. A clean canonical agent review containing
`BLOCKING:` in its body is internally inconsistent and fails closed. Any inline
review comment attached to a canonical clean agent review is treated as a finding
and blocks authorization.

A blocking agent review cannot be overridden by another clean review on the same
head. A code correction must produce a new head and therefore a new review.

## Exact-head behavior

Approvals and canonical agent reviews on older heads are stale immediately after
the PR head changes. The checker never carries authority forward to a new commit.

For decisive GitHub approvals/changes-requested state, the latest exact-head state
per reviewer wins. Review ordering uses validated timezone-aware submission time
and positive integer review ID. Missing or malformed review metadata fails closed.

## Security enforcement

The required `Python source security` and `Node dependency audit` checks run their
normal scans before invoking `tools/review_provenance.py` on pull requests.
A missing or invalid exact-head review therefore makes the required context fail;
it does not skip Bandit, dependency auditing, dependency review, or other
substantive checks.

When `review-provenance-semantic` is present, Security applies the same canonical
exact-head review authority. The label does not create a second vendor-specific
merge gate. Copilot, Codex, or another external reviewer may add stronger identity
or semantic evidence when available, but no named external provider is required
for ordinary repository integration.

A submitted or dismissed PR review triggers the default-branch Security workflow.
That event re-runs the latest completed Security run associated with the exact PR
head so newly recorded review evidence can refresh the existing required contexts.

Push, schedule, and manual Security runs do not require PR review provenance.

## Engineering acceptance versus external qualification

Repository integration must remain continuously available using GitHub, Veritas's
own tests and CI, and canonical exact-head review provenance. Third-party accounts,
credits, hardware, services, or reviewer identities are not universal merge
authorities.

Provider-specific evidence belongs to the claim it supports. HUD, Prime, NeMo Gym,
OpenEnv, Harbor, Copilot, Codex, paid compute, or another external system may be a
required qualification gate only when the work item or release claim specifically
asserts compatibility, validation, or authority from that system. If such evidence
is unavailable, the implementation may still be mergeable while the stronger claim
remains pending or false.

Scientific, Frontier, training-value, release, deployment, and commercial claims
remain subject to their own stricter evidence boundaries. Removing an unavailable
provider from ordinary merge authority does not weaken those qualification gates.

## Agent review procedure

For a same-account review, use a genuinely fresh review agent/session that did not
implement the candidate. Review the complete exact-head diff and relevant tests.

If clean, submit a GitHub `COMMENTED` review containing exactly one canonical clean
marker for the current head. If a blocker exists, use `verdict=blocking` and state
`BLOCKING:` findings in the review body. Do not call a same-account review a
separate GitHub identity.

The authority ceiling remains repository integration only. Review provenance is
not scientific qualification, frontier qualification, release authorization,
deployment authorization, private-data authorization, paid-compute authorization,
or commercial release authority.
