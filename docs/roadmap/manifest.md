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
3. for `CLAIMED` and `REVIEW`, the synchronizer requires the latest trusted
   `<!-- veritas-agent-work-status:v1 -->` comment authored by `github-actions[bot]`
   and requires its Work ID, issue number, state, holder, branch, and state-specific PR
   linkage to agree with the canonical coordination state;
4. trusted status lookup paginates the complete issue-comment history rather than
   assuming the authoritative status is present on the first 100-comment page;
5. bot-authored status with malformed JSON, an unexpected schema, or an invalid
   transition sequence fails closed rather than being ignored;
6. if trusted status is missing for `CLAIMED`/`REVIEW`, synchronization fails closed
   instead of falling back to issue-body or stale manifest claimant/PR metadata;
7. `BLOCKED` may be either unowned dependency-blocked work or work still held by an
   active agent. When a blocked issue has comments, synchronization requires a trusted
   bot status rather than guessing that the lane is unowned. Owner-held BLOCKED status
   preserves holder/branch/PR and the corresponding path reservation; a released
   BLOCKED status must clear active holder/branch/PR metadata;
8. a pristine BLOCKED issue with no comments can remain unowned without a status
   lookup, because it cannot yet contain a coordination transition record;
9. the issue Work Contract supplies Work ID, branch convention, dependency prose,
   positive/negative ownership, and fallback PR linkage only where trusted live
   status is not authoritative.

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
- active claimant when trusted coordination status establishes one;
- positive/negative ownership summaries;
- machine-checkable exact exclusive paths when the issue contract exposes them;
- program, wave, strategic rank, and critical-path metadata.

`strategic_rank` is deliberately independent of `state`. Rank never makes blocked work
claimable. `wave` is currently `UNASSIGNED` unless explicitly curated; automatic
parallel-wave construction belongs to `ROADMAP-WAVES-001` (#219).

Dependency kinds are conservative until `ROADMAP-DEPS-001` (#218) lands. On every
sync, `dependencies` is re-derived from the **current** Work Contract, using both
`#issue` references and explicit live Work IDs/aliases. Previous general dependency
edges are never unioned back in, so removing a dependency from the Work Contract
removes it from the synchronized DAG. `hard_dependencies` remains a curated subset,
but a hard edge survives synchronization only while the same edge is still present in
the freshly derived dependency set.

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
The sync command is the only networked path. BLOCKED issues with no comments require
no status-comment request because they cannot contain a coordination transition
record. Once a BLOCKED issue has comments, trusted-status lookup follows all comment
pages and synchronization fails closed if no authoritative bot status can establish
whether the lane is held or released.

## Baseline validation

`ROADMAP-002` fails closed on:

- duplicate Work IDs, aliases, or issue numbers;
- dependencies that point to missing roadmap Work IDs;
- dependency cycles;
- missing trusted coordination status for live `CLAIMED`/`REVIEW` work;
- ambiguous commented `BLOCKED` work with no trusted coordination status;
- malformed/wrong-schema trusted status or invalid transition sequence;
- `CLAIMED`/`REVIEW` trusted status with no active holder/branch;
- `REVIEW` trusted status with no linked PR, or `CLAIMED` status carrying one;
- inconsistent owner-held/released BLOCKED active metadata;
- a `READY`, `CLAIMED`, or `REVIEW` item whose explicitly classified hard dependency
  is not `DONE` or `SUPERSEDED`;
- exact duplicate exclusive-path claims among `READY`, `CLAIMED`, `REVIEW`, and
  owner-held `BLOCKED` work;
- malformed state, ownership, branch, program, wave, or PR metadata.

A dependency-blocked item with no holder does not reserve an implementation path merely
because its state is `BLOCKED`. By contrast, a lane transitioned to `BLOCKED` by its
current holder remains reserved until the coordination workflow records an explicit
release.

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

`hard_dependencies` is preserved only as the intersection of the prior curated hard
set and the dependencies freshly derived from the current Work Contract. This prevents
obsolete hard edges from surviving a dependency correction.

This keeps strategic planning separate from mutable GitHub execution state. Future
policy tickets may tighten those fields without changing the manifest's role as a
coordination index.
