# Veritas Agent Operating Contract

This repository uses the Universal Coding Agent System in `.agents/universal/` plus the Veritas scientific overlay in `.agents/veritas/`.

## Authority order

When instructions conflict, use this order:

1. explicit user task instructions and strict file/branch ownership for the active task;
2. repository security/privacy constraints and sealed/private-data boundaries;
3. this repository's canonical product/scientific docs, especially `BUILD_STATUS.md` and qualification/release contracts;
4. approved issue/spec/acceptance criteria;
5. `.agents/veritas/OVERLAY.md`;
6. `.agents/universal/CONTRACT.md` and `docs/agents/*`;
7. individual `.agents/skills/*` instructions.

Lower layers may operationalize higher layers but may not weaken them.

## Mandatory work loop

`request -> reconstruct repo/task context -> classify task -> define outcome + falsifier -> isolate branch/worktree -> implement/experiment minimally -> targeted verification -> broader verification -> domain/scientific gates -> independent review -> PR/proposal -> merge/release only when authorized`

Merge-authoritative independent review is defined by
`docs/automation/review-provenance.md` and enforced by
`tools/review_provenance.py`. Same-account agent/session review may provide useful
semantic evidence, but prose or a self-asserted lineage does not satisfy the
independent-review gate. The authoritative review must be an exact-head GitHub
approval from an identity different from the PR author.

## Hard stops

- Never assume a PASS from missing evidence.
- Implementation correctness is not scientific qualification.
- Scientific qualification is not frontier qualification.
- Do not expose, reconstruct, log, persist, or publish sealed/private benchmark rows or hidden labels outside their authorized boundary.
- Do not weaken qualification, contamination, leakage, exploit-resistance, calibration, or privacy gates to make a candidate pass.
- Do not run expensive/manual model workflows as ordinary CI unless the active contract explicitly requires it.
- Do not write directly to `main` for coding work.
- Respect strict file ownership when parallel agents/branches are active.
- Do not claim a release is complete because code merged; release gates, exact candidate identity, required CI/security, evidence, and external administration requirements remain separate.

## Mode independence

These rules apply equally in ordinary Chat and ChatGPT Work. Mode changes the available execution surface, not the engineering standard. Resolve available tools at runtime; do not make the workflow depend on a mode-specific tool name.
