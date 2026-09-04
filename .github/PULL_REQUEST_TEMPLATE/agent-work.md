---
name: Agent roadmap work
description: Pull request completion contract for agent-owned roadmap work
title: "[WORK-ID] "
---

## Work contract

- **Work ID / issue:** <!-- e.g. ROADMAP-003 / #197 -->
- **Claim holder:** <!-- agent ID from canonical issue status -->
- **Exact base SHA:** <!-- full SHA -->
- **Branch / worktree:** <!-- branch and isolated worktree/clone identifier -->
- **Positive ownership:** <!-- allowed paths -->
- **Negative ownership:** <!-- explicitly forbidden paths -->
- **Dependency state:** <!-- dependency issues and live state -->

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
- **Security/privacy checks:** <!-- exact-head status or N/A -->
- **Quality/static checks:** <!-- exact-head status or N/A -->
- **Build/package/container checks:** <!-- exact-head status or N/A -->
- **Scientific / Frontier / training qualification:** NOT RUN unless separately required and evidenced

## Evidence boundary

<!-- State exactly what this PR establishes and what it does not establish. Green implementation checks do not imply scientific, Frontier, training, buyer, commercial, release, or sealed-workflow qualification. -->

## Next authority action

<!-- Usually: independent exact-head review. Do not claim merge/release authority unless separately granted. -->

## Handoff

After the PR exists and the implementation head is ready for review, record on the linked roadmap issue:

`/handoff <agent-id> <pr-number>`

See `docs/agents/handoff-contract.md` for the complete handoff, review, branch-discipline, and completion rules.
