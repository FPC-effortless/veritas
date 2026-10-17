## Work contract

- **Work ID / issue:** <!-- e.g. ROADMAP-003 / #197 -->
- **Claim holder:** <!-- agent ID from canonical issue status -->
- **Exact base SHA:** <!-- full SHA -->
- **Branch / worktree:** <!-- branch and isolated worktree/clone identifier -->
- **Positive ownership:** <!-- allowed paths -->
- **Negative ownership:** <!-- explicitly forbidden paths -->
- **Dependency state:** <!-- dependency issues, latest trusted status source, and timestamp -->

## Change inventory

- **Files changed:**
  - <!-- complete list -->
- **Unowned files changed:** none
  <!-- If not none, identify explicit authorization and rationale. -->
- **Unresolved interface requests:** none

## Verification on this exact head

- **Head SHA:** <!-- full SHA -->
- **Targeted tests / falsifiers:** <!-- command/check + result; use NOT RUN when absent -->
- **Broader CI:** <!-- exact-head status -->
- **Exact-head Security / Dependency Review:** <!-- status for each required check -->
- **Security/privacy checks:** <!-- exact-head status or N/A -->
- **Quality/static checks:** <!-- exact-head status or N/A -->
- **Build/package/container checks:** <!-- exact-head status or N/A -->
- **Scientific / Frontier / training qualification:** NOT RUN unless separately required and evidenced

## Evidence boundary

<!-- State exactly what this PR establishes and what it does not establish. Green implementation checks do not imply scientific, Frontier, training, buyer, commercial, release, or sealed-workflow qualification. -->

## Next authority action

<!-- Usually: independent exact-head review. Do not claim merge/release authority unless separately granted. -->

## Latest trusted coordination status

- **Issue status comment:** <!-- link and timestamp -->
- **Current holder / branch / ownership_paths:** <!-- from github-actions[bot] status -->
- **Linked PR / exact head / return_state:** <!-- from github-actions[bot] status -->

## Handoff

After the PR exists and the implementation head is ready for review, record on the linked roadmap issue:

`/handoff <agent-id> <pr-number>`

See `docs/agents/handoff-contract.md` for the complete handoff, review, branch-discipline, and completion rules.
