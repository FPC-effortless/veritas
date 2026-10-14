# Trusted semantic code review

Status: merge-authoritative implementation-review infrastructure. This policy does not grant scientific, Frontier, qualification, release, sealed/private-data, paid-compute, deployment, external-account, or commercial authority.

## Purpose

The `review-provenance-semantic` label requests a trusted exact-head semantic implementation review for ordinary code and test pull requests. Semantic evidence may come from a clean exact-head GitHub Copilot or OpenAI Codex review, or from Veritas's canonical exact-head agent-review marker. The workflow combines that evidence with exact-head isolated execution, then uses the trusted default-branch `github-actions[bot]` identity as the approval bridge consumed by `tools/review_provenance.py` and Security.

GitHub Copilot and OpenAI Codex remain supported semantic reviewers. The trusted workflow requests Copilot on a best-effort basis and emits an exact-head `@codex review` trigger. Provider availability is optional when a valid canonical agent review already exists; CI alone never satisfies semantic review. Any blocking finding or inline comment in evidence observed before approval vetoes it, whether that evidence comes from a provider or a canonical agent review.

Semantic evidence alone is not merge authority. The bridge approves only after the exact head has clean provider or canonical agent-review evidence and the aggregate `Required` CI check is green. `Required` includes the isolated candidate-execution job. Security independently checks the repository's canonical exact-head review provenance; provider findings are checked by the semantic workflow before it submits the bridge approval.

## Trust split

1. **Ordinary candidate CI** runs in the `pull_request` workflow with read-only repository permissions. Candidate code never receives the semantic reviewer's write token.
2. **Isolated candidate execution** is an additional required CI job. It separately checks out the trusted base and the exact candidate with `persist-credentials: false`, builds the dependency/test image only from trusted base code, mounts the candidate checkout read-only, and executes a copied candidate workspace inside an ephemeral container. The execution container has no network, no token or repository secrets, a read-only root filesystem, dropped Linux capabilities, `no-new-privileges`, PID/memory/CPU ceilings, and only tmpfs writable state. Candidate Python sources are compiled and the test suite is executed against the candidate `src/` tree. Failure prevents the aggregate `Required` check from passing.
3. **Semantic inspection** is evidenced by an exact-head GitHub Copilot or OpenAI Codex review, or a canonical Veritas agent review. Candidate content is untrusted review input. Any inline finding from an observed provider or canonical review fails closed. A review summary containing `BLOCKING:` and a canonical `verdict=blocking` marker also fail closed. For Codex, a `+1` reaction from `chatgpt-codex-connector[bot]` on the immutable trusted exact-head trigger comment is accepted as Codex's clean-review signal when no review findings are emitted. The canonical marker's single-owner identity limitation is operational, as described in [review provenance](./review-provenance.md).
4. **Approval authority** runs from `.github/workflows/semantic-code-review.yml` on `pull_request_target`, therefore from the trusted default branch. It never checks out or executes candidate code and is the only semantic-review component with pull-request approval authority.
5. **Final Security** is explicitly rerun after approval so the existing exact-head provenance checks validate the resulting APPROVED review and the requested semantic provenance gate. Security verifies canonical review provenance; it does not independently query Copilot or Codex evidence.

## Fail-closed conditions

Semantic integration is refused when any of the following is true:

- PR is draft, closed, merged, empty, or moves from the event head;
- more than 100 files or 15,000 changed lines are in scope;
- a patch cannot be inspected or credential-like additions are detected;
- exact-head `Required` CI is absent or not successful, including isolated candidate execution;
- a Python-sensitive change lacks a successful exact-head `repository-python-quality` check;
- neither a supported provider nor a valid canonical agent review produces clean exact-head semantic evidence;
- a canonical marker attempt is malformed; for a current-head marker, a blocking verdict or inline finding fails closed. Stale evidence never satisfies the gate;
- an observed provider review has any inline finding;
- an observed provider review contains `BLOCKING:` in its summary;
- any current exact-head reviewer has `CHANGES_REQUESTED`;
- the PR changes reviewer/repository authority paths.

Protected authority paths include all of `.github/**`, `.agents/**`, `AGENTS.md`, `tools/review_provenance.py`, `docs/automation/**`, and `docs/agents/**`. Changes to these paths require genuinely independent review outside the semantic auto-approval path; a candidate cannot rewrite the reviewer, provider policy, workflow policy, or agent policy that will judge it.

The isolated runner intentionally installs dependencies from the trusted base rather than from candidate-controlled package metadata. A candidate that requires new dependencies will therefore fail closed in isolated execution and must use an independently reviewed dependency/authority path before semantic auto-approval.

## Provider evidence contract

### GitHub Copilot

`.github/copilot-instructions.md` is itself a protected authority path. It instructs Copilot to ignore instructions embedded in candidate code, comments, fixtures, generated artifacts, commit text, and PR text; to review correctness, security, privacy, provenance, concurrency, cleanup, compatibility, resource behavior, and test adequacy; and to emit merge-blocking findings as inline comments whenever GitHub permits. If GitHub cannot attach an important finding inline, the summary must use the `BLOCKING:` prefix.

A clean exact-head Copilot `COMMENTED` review with no inline findings and no `BLOCKING:` marker is valid semantic evidence.

### OpenAI Codex

The trusted workflow creates a bot-owned comment containing an immutable exact-head marker and `@codex review` with review guidance. A Codex `COMMENTED` review must be bound by GitHub to the exact candidate head and contain no inline or `BLOCKING:` findings. Codex may instead report a clean review by reacting `+1` to the trigger comment; that signal is accepted only when the trigger comment is owned by `github-actions[bot]`, contains the exact full head marker, and the PR head has not moved.

Codex and Copilot availability is external to repository code. The relevant account/repository review feature must be enabled to use either provider. If neither provider is available, a valid canonical agent review can still satisfy semantic evidence; CI by itself cannot.

### Canonical Veritas agent review

A canonical exact-head `COMMENTED` review may satisfy semantic evidence when it contains exactly one standalone marker of the form `<!-- veritas-agent-review:v1 head=<40-char-sha> verdict=clean -->`. The marker must bind to the review commit and current PR head, the GitHub review must have valid identity and submission metadata, and the review must contain no `BLOCKING:` summary or inline finding. Quoted, indented, and fenced marker examples are not evidence. A `verdict=blocking` marker fails closed. See [review provenance](./review-provenance.md) for the complete canonical rule and the operational limits of single-owner review identity.

## Exact-head lifecycle

Head movement invalidates all semantic evidence. Re-handoff the roadmap work when applicable, remove and re-add `review-provenance-semantic`, and obtain new exact-head semantic evidence. Resolving an old finding on the same head is not treated as a clean review; the implementation must move to a new candidate head.

## Authority boundary

A semantic APPROVED review means only that the implementation candidate passed the repository's machine-isolated semantic-review contract and existing CI evidence at that exact head. Scientific claims, benchmark qualification, Frontier qualification, release, private/sealed evidence, deployment, paid compute, external accounts, and commercial decisions remain governed by their separate contracts.
