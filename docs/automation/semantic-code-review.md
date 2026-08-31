# Trusted semantic code review

Status: merge-authoritative implementation-review infrastructure. This policy does not grant scientific, Frontier, qualification, release, sealed/private-data, paid-compute, deployment, external-account, or commercial authority.

## Purpose

The `review-provenance-semantic` label requests a trusted exact-head semantic implementation review for ordinary code and test pull requests. The reviewer combines independent semantic analysis from GitHub Copilot code review with existing isolated CI execution, then uses the trusted default-branch `github-actions[bot]` identity as the exact-head approval bridge consumed by `tools/review_provenance.py` and Security.

Copilot semantic evidence alone is not merge authority because Copilot code review submits COMMENT reviews rather than APPROVED reviews. The bridge approves only after the exact head has a completed clean Copilot review and the aggregate `Required` CI check is green.

## Trust split

1. **Candidate execution** runs in the existing `pull_request` CI workflow with read-only repository permissions. Candidate code does not receive the semantic reviewer's write token.
2. **Semantic inspection** is performed by Copilot code review on the exact candidate head. Any inline Copilot finding fails the semantic gate. Findings must be addressed on a new head and reviewed again.
3. **Approval authority** runs from `.github/workflows/semantic-code-review.yml` on `pull_request_target`, therefore from the trusted default branch. It never checks out or executes candidate code.
4. **Final Security** is rerun after approval so the existing exact-head provenance checks validate the resulting APPROVED review.

## Fail-closed conditions

Semantic approval is refused when any of the following is true:

- PR is draft, closed, merged, empty, or moves from the event head;
- more than 100 files or 15,000 changed lines are in scope;
- a patch cannot be inspected or credential-like additions are detected;
- exact-head `Required` CI is absent or not successful;
- no exact-head Copilot COMMENT review exists;
- that Copilot review has any inline findings;
- any current exact-head reviewer has `CHANGES_REQUESTED`;
- the PR changes reviewer/repository authority paths.

Protected authority paths include all GitHub workflows, Copilot instructions/skills/agents, `.agents/**`, `AGENTS.md`, `tools/review_provenance.py`, `docs/automation/**`, and `docs/agents/**`. Changes to these paths require genuinely independent review outside the semantic auto-approval path; a candidate cannot rewrite the reviewer that will approve it.

## Exact-head lifecycle

Head movement invalidates the semantic evidence. Re-handoff the roadmap work when applicable, remove and re-add `review-provenance-semantic`, and obtain a new exact-head Copilot review. Resolving an old finding on the same head is not treated as a clean review; the implementation must move to a new candidate head.

## Authority boundary

A semantic APPROVED review means only that the implementation candidate passed the repository's machine-isolated semantic-review contract and existing CI evidence at that exact head. Scientific claims, benchmark qualification, Frontier qualification, release, private/sealed evidence, deployment, paid compute, external accounts, and commercial decisions remain governed by their separate contracts.
