# Agent roadmap manifest

`ROADMAP-002` establishes `.github/agent-roadmap.yml` as the checked-in coordination
snapshot for executable `agent-work` issues.

The manifest is **not** a qualification authority. Scientific qualification, Frontier
qualification, training value, commercial readiness, release state, sealed evidence,
and other assurance states remain governed by their existing contracts and evidence.
A roadmap item being `DONE` means only that its work contract reached the repository
coordination completion state.

## Source of truth

Execution state is synchronized from GitHub:

1. the issue must carry `agent-work`;
2. exactly one `work:ready|blocked|claimed|review|done|superseded` label is required;
3. for `CLAIMED` and `REVIEW`, the synchronizer reads the latest trusted
   `<!-- veritas-agent-work-status:v1 -->` comment authored by `github-actions[bot]`
   and requires its Work ID, issue number, and state to agree with the label;
4. the issue Work Contract supplies Work ID, branch convention, dependency prose,
   positive/negative ownership, and fallback PR linkage.

This prevents stale issue-body text from overriding live coordination labels. It also
means the checked-in file is a **snapshot**: run the explicit sync command before using
it as a current planning view.

## Format

The file has a `.yml` name but intentionally uses JSON syntax. JSON is valid YAML 1.2,
and this lets validation run with the Python standard library rather than adding
PyYAML or changing shared package metadata.

Each work entry records:

- canonical Work ID plus optional aliases;
- issue number and canonical title;
- execution state;
- dependency Work IDs and external issue references;
- a separately classified `hard_dependencies` subset;
- branch and linked PR;
- positive/negative ownership summaries;
- machine-checkable exact exclusive paths when the issue contract exposes them;
- program, wave, strategic rank, and critical-path metadata.

`strategic_rank` is deliberately independent of `state`. Rank never makes blocked work
claimable. `wave` is currently `UNASSIGNED` unless explicitly curated; automatic
parallel-wave construction belongs to `ROADMAP-WAVES-001` (#219).

Dependency kinds are conservative until `ROADMAP-DEPS-001` (#218) lands.
`dependencies` preserves the DAG relation; `hard_dependencies` contains only edges
already classified strongly enough to drive the baseline readiness check. The
synchronizer preserves that curated subset instead of guessing from prose.

## Commands

Validate the checked-in snapshot without network access:

```bash
python tools/roadmap/agent_roadmap.py validate
```

Refresh live coordination metadata from GitHub, then validate before writing:

```bash
GITHUB_TOKEN=... python tools/roadmap/agent_roadmap.py sync
```

A token is optional for the public repository but avoids unauthenticated API limits.
The sync command is the only networked path.

## Baseline validation

`ROADMAP-002` fails closed on:

- duplicate Work IDs, aliases, or issue numbers;
- dependencies that point to missing roadmap Work IDs;
- dependency cycles;
- a `READY`, `CLAIMED`, or `REVIEW` item whose explicitly classified hard dependency
  is not `DONE` or `SUPERSEDED`;
- exact duplicate exclusive-path claims among `READY`, `CLAIMED`, and `REVIEW` work;
- malformed state, ownership, branch, program, wave, or PR metadata.

Historical `DONE` work remains valid even if later roadmap reconstruction reveals an
old dependency that is no longer satisfied; validation does not reopen completed
implementation tickets.

The exact-path check is intentionally narrow. Ancestor/descendant glob collisions,
negative-ownership enforcement, open-PR changed-file reservations, convergence-only
surfaces, and branch duplication are owned by `ROADMAP-004` (#198) and the live
`ROADMAP-LOCK-001` (#228) lane. Duplicating those semantics here would create two
competing lock authorities.

## Updating strategy metadata

The sync operation refreshes issue-derived and coordination-derived fields while
preserving manually curated:

- `program`
- `wave`
- `strategic_rank`
- `critical_path`
- `hard_dependencies`

This keeps strategic planning separate from mutable GitHub execution state. Future
policy tickets may tighten those fields without changing the manifest's role as a
coordination index.
