# Ponytail Fusion Record

## Provenance

Upstream: `DietrichGebert/ponytail`
Pinned source commit reviewed for this fusion: `2ed6c52c9d7e5e56942508591085fd45dea277d3` (2026-08-07).
License: MIT, Copyright (c) 2026 DietrichGebert. See `.agents/skills/LICENSE-PONYTAIL`.

This file records the semantics retained from all six upstream skills so future edits can be checked for information loss. The repository-local adaptations remain subordinate to `AGENTS.md`, the universal contract, and any repository overlay.

## 1. `ponytail`

Retained semantics:
- coding-only minimality discipline; lazy means efficient, not careless;
- active-by-default `full` intensity, with `lite`, `full`, and `ultra` compatibility and stop/off/normal-mode phrases;
- understand the real code path before simplifying;
- ordered ladder: need at all -> existing codebase -> stdlib -> native platform -> installed dependency -> one-line/direct form -> minimum new code;
- root-cause bug placement: inspect sibling callers and prefer one fix at their common seam over repeated symptom guards;
- no speculative abstractions, factories, config, scaffolding, boilerplate, or extra dependencies;
- deletion/reuse, boring solutions, few files, and short correct diffs are preferred only after comprehension;
- explicit requested behavior is honored even when a larger implementation is necessary;
- never cut trust-boundary validation, data-loss handling, security, accessibility, or necessary physical/hardware calibration;
- non-trivial logic leaves a runnable check; trivial direct substitutions need no ceremonial new test;
- deliberate shortcuts with real ceilings use `ponytail: <ceiling>, <upgrade trigger/path>` comments;
- when explicitly invoked as the Ponytail compatibility skill, keep the response implementation-first and concise unless the user requested a report/walkthrough.

## 2. `ponytail-review`

Retained as a complexity-only review pass, separate from correctness/security/performance review.

Finding tags and meaning:
- `delete:` dead code, speculative feature, unused flexibility; replacement may be nothing;
- `stdlib:` hand-rolled behavior replaced by a named standard-library primitive;
- `native:` code/dependency replaced by a platform-native capability;
- `yagni:` premature abstraction/config/layer with insufficient real multiplicity;
- `shrink:` same behavior expressible materially more directly.

Findings identify file/line, the cut, and replacement. If useful, estimate `net: -N lines possible`; never treat that estimate as measured historical savings. A minimal smoke check is not bloat. If nothing material is cuttable: `Lean already. Ship.`

## 3. `ponytail-audit`

Retained as the repo-wide version of the complexity-only review. Hunt especially for:
- dependencies duplicating stdlib/native platform capabilities;
- one-implementation interfaces;
- one-product factories;
- wrappers that only delegate;
- files/layers that add no semantic boundary;
- dead flags/config;
- hand-rolled standard-library behavior.

Rank largest credible cuts first. Do not mix correctness, security, or performance defects into the complexity report; route those to normal review. Audit reports only unless the user separately authorizes fixes.

## 4. `ponytail-debt`

Retained as a read-only ledger pass over language-appropriate comment markers containing `ponytail:`. Each marker should expose:
- file and line;
- deliberate simplification;
- stated ceiling/limit;
- upgrade trigger/path.

Markers without an upgrade trigger are tagged `no-trigger`. Optional ownership may be derived from blame/history. The ledger can be persisted only when requested. Default report ends with marker count and no-trigger count.

## 5. `ponytail-gain`

The honesty boundary is mandatory: Ponytail benchmark results are upstream benchmark results, not savings measured in the current repository. Never say “this repo saved X” without a real controlled baseline.

The upstream skill at the pinned source preserves a legacy isolated-generation card (5 everyday tasks, three models) reporting:
- 80–94% fewer generated lines;
- 47–77% lower cost;
- 3–6x faster.

The upstream README now foregrounds a later agentic benchmark on 12 feature tasks, n=4, Haiku 4.5, reporting approximately:
- 54% fewer changed lines on average;
- 22% fewer tokens;
- 20% lower cost;
- 27% less time;
- 100% safety on the stated benchmark.

These methodologies must remain labeled separately; never blend them into one number or extrapolate them to a live project. `ponytail-gain` is one-shot and changes no mode/state.

## 6. `ponytail-help`

Retained compatibility surface:
- `ponytail`, `ponytail lite`, `ponytail full`, `ponytail ultra`;
- `ponytail-review`, `ponytail-audit`, `ponytail-debt`, `ponytail-gain`, `ponytail-help`;
- stop/off/normal-mode deactivation phrases affect Ponytail minimality only.

Upstream plugin configuration information is preserved as provenance, not required by this repo-local universal system: upstream supports `PONYTAIL_DEFAULT_MODE`, a `~/.config/ponytail/config.json` (Windows `%APPDATA%\ponytail\config.json`) defaultMode setting, with environment variable taking priority over config and `full` as upstream fallback. Host-specific slash/@ command and plugin-update flows belong to the upstream plugin; our repo-local aliases remain tool/mode independent.

## Fusion map into the existing universal skills

- `ask-matt`: routes simplify/over-engineering requests to the Ponytail passes.
- `implement`: applies the ladder after context reconstruction and before new code.
- `diagnosing-bugs`: enforces common-root caller tracing.
- `tdd`: reconciles falsifier-first development with Ponytail's minimum runnable-check rule.
- `code-review`: adds an independent unnecessary-complexity axis and Ponytail tags.
- `improve-codebase-architecture`: incorporates the repo-wide audit hunt list.
- `codebase-design`: blocks premature interfaces/factories/config while preserving real deep-module boundaries.
- `to-spec` / `to-tickets`: make reuse/native/stdlib and non-goals explicit before generating work.
- `prototype`: uses the smallest experiment that answers the question and avoids production abstractions.
- `wizard`: prefers existing platform/stdlib/installed official capabilities before new automation.
- `handoff`: reports deliberate simplification ceilings and unresolved `ponytail:` debt.
- all other skills inherit the minimality discipline through `.agents/universal/CONTRACT.md`.
