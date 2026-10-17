# Roadmap path-ownership semantics

Status: coordination policy. This document defines repository path ownership for parallel roadmap work. It does not grant GitHub permissions, review authority, merge authority, release authority, scientific qualification, Frontier qualification, training qualification, sealed/private evidence authority, paid-compute authority, or external-account authority.

## Purpose

Parallel agents need a deterministic answer to a narrow question:

> May this work item write this repository path while the currently active reservations exist?

Read access, dependency use, code review, interface consumption, and implementation ownership are separate concepts. A work item may depend on or inspect another lane without gaining permission to edit that lane.

The policy is intentionally narrower than a generic filesystem ACL. It governs planned repository writes made through roadmap work items and is designed so ROADMAP-004 (#198) and claim-time locking can implement it mechanically.

## Ownership modes

Each declared repository relationship has one mode. Modes are not interchangeable.

### `exclusive_write`

One active work item may write the declared path set.

Rules:

- CLAIMED, REVIEW, and owner-held BLOCKED work retain the reservation until an audited release, transfer, completion, or supersession action removes it.
- A second write-capable reservation that intersects the path set is rejected.
- Dependency on the owner does not confer write authority.
- Reviewers may request changes but must not patch the owned path from a separate lane unless ownership is explicitly transferred.

Use `exclusive_write` for feature-local implementation, tests, and narrow documentation whose complete edit responsibility belongs to one lane.

### `read_only`

The work item may inspect or consume the path but may not commit changes to it.

Rules:

- any number of work items may hold `read_only` relationships simultaneously;
- `read_only` does not reserve the path against its legitimate writer;
- a consumer that discovers a missing provider capability must use `interface_request` rather than silently upgrading itself to a writer;
- generated local build/test copies outside committed repository state do not count as repository writes.

A `read_only` declaration must never satisfy a validator check that requires write authority.

### `shared_generated`

A generated repository artifact has one designated canonical generator/owner even when many consumers can reproduce or validate it.

A declaration must identify:

- the generated output path;
- the canonical generator Work ID or generator-owned source path;
- the source-of-truth inputs;
- whether committed regeneration is permitted only in the generator lane or in a designated convergence lane.

Rules:

- consumers may regenerate into ephemeral/local validation locations and compare results;
- consumers may not commit regenerated output merely because generation is deterministic;
- a committed generated output remains write-reserved to its designated generator or convergence owner;
- changes to generator inputs follow the ownership of those source inputs, not the generated file's apparent location;
- if two generators can produce the same committed path, the ownership declaration is invalid.

This prevents generated files from becoming an informal shared-write escape hatch.

### `convergence_only`

A path is intentionally shared across feature boundaries and may be changed only by a designated serialized convergence work item.

Typical examples are root/shared integration surfaces such as package metadata, root CLI registration, shared export aggregators, or cross-cutting workflows.

Rules:

- feature/provider lanes consume the path read-only;
- a feature lane may request a required integration but may not edit the convergence path directly;
- only the named convergence Work ID may acquire write authority while convergence is active;
- multiple convergence writers for the same intersecting path are invalid;
- convergence ownership does not permit semantic redesign of provider-owned implementation paths.

### `interface_request`

The work item has discovered that a provider-owned surface lacks an interface it needs.

`interface_request` is coordination metadata, not write permission.

A request should identify:

- requesting Work ID;
- provider Work ID or provider-owned path;
- the minimal missing capability/contract;
- why existing public/provider interfaces are insufficient;
- whether the requester is blocked or can continue independently.

The provider owner may implement the request in its own lane, reject it with rationale, or create/authorize a narrow interface subtask. The requesting consumer must not patch provider-owned code directly unless an explicit ownership transfer occurs.

## Path grammar

Ownership paths must be repository-relative, normalized with `/`, and must not contain `..` traversal.

Validators must support at least:

- exact file: `pyproject.toml`;
- exact directory/subtree: `src/investigation_world/foo/**`;
- nested subtree: `src/investigation_world/foo/bar/**`;
- exact generated file or fixture path;
- explicitly enumerated files when a broad ancestor would block useful parallelism.

Issue authors should prefer the narrowest complete write set. Broad claims such as `src/**`, `docs/**`, or `tests/**` are invalid practice unless the work genuinely requires serialized repository-wide convergence.

### Ancestor/descendant intersection

Ownership is not exact-string locking.

Two write-capable path declarations intersect when either can select a repository path selectable by the other.

At minimum, validators must reject these pairs when both are write-capable:

```text
src/foo/**              vs src/foo/bar/**
src/foo/**              vs src/foo/bar.py
src/foo/bar/**          vs src/foo/bar/baz.json
docs/roadmap/**         vs docs/roadmap/path-ownership.md
.github/workflows/**    vs .github/workflows/ci.yml
```

Disjoint siblings do not intersect:

```text
src/foo/a/**            vs src/foo/b/**
docs/foo.md             vs docs/bar.md
```

For wildcard forms that the validator cannot prove disjoint, it must fail closed rather than assume safety.

### Exact file under broader subtree

An exact file reservation always conflicts with an active write-capable ancestor reservation that covers it. A narrower file diff in the broader lane does not silently waive the declared ancestor reservation.

That is why ownership must be narrowed or transferred explicitly before another agent starts work; observed current diffs are evidence of what changed, not authority to ignore the Work Contract.

## Active reservation semantics

For collision purposes, a write-capable reservation remains active while the work item is:

- CLAIMED;
- REVIEW;
- owner-held BLOCKED.

An unowned BLOCKED item does not reserve a writer merely because it is blocked. READY advertises claim eligibility but must still be checked against active reservations and open-PR changed-file protection at claim time.

DONE and SUPERSEDED historical reservations do not permanently lock paths, but their history remains auditable.

Staleness alone does not transfer ownership. Recovery must be explicit and audited.

## Proposed machine-readable representation

The current Work Contract prose is the migration/source format. Validators should converge on an explicit structure equivalent to:

```yaml
ownership:
  - mode: exclusive_write
    paths:
      - src/investigation_world/example/**
  - mode: read_only
    paths:
      - src/investigation_world/runtime/**
  - mode: convergence_only
    paths:
      - pyproject.toml
    convergence_work_id: PORTABLE-CONVERGENCE-001
  - mode: shared_generated
    paths:
      - generated/schema.json
    generator_work_id: SCHEMA-GEN-001
    source_paths:
      - schema/source/**
  - mode: interface_request
    provider_work_id: RUNTIME-001
    provider_paths:
      - src/investigation_world/runtime/**
    request: expose deterministic capability metadata
```

The exact serialization may evolve under ROADMAP-004, but the semantic distinctions above must not be collapsed into one flat list of strings.

## Claim-time decision procedure

For a candidate claim:

1. Parse and normalize all write-capable candidate paths.
2. Reject malformed, empty, traversal-bearing, or unbounded paths that cannot be interpreted safely.
3. Resolve current trusted active reservations.
4. Reject any `exclusive_write`, `shared_generated` committed-output, or `convergence_only` write that intersects another active writer without an explicit transfer.
5. Reject a candidate that attempts a `convergence_only` path unless its Work ID is the designated convergence owner.
6. Reject a candidate that attempts a `shared_generated` committed output unless it is the designated generator/convergence owner.
7. Ignore `read_only` and `interface_request` relationships for write-lock acquisition; they grant no writes.
8. Check open PR changed files as a conservative legacy reservation source for work not yet represented by trusted roadmap ownership.
9. Check branch uniqueness for independent active Work IDs; branch identity is not ownership, but two unrelated active Work IDs must not silently share one branch.
10. Accept the claim only after the reservation is recorded atomically enough that a competing claim cannot observe the path as free.

Partial coordination failure must err toward a stale reservation/non-claimable path, not accidental double ownership.

## Temporary ownership transfer

Temporary transfer is exceptional. It must never be inferred from branch ancestry, PR authorship, issue comments that do not declare a transfer, inactivity, or a consumer's need for convenience.

An auditable transfer record must include:

- source Work ID and current holder;
- destination Work ID and intended holder;
- exact transferred path set;
- prior ownership mode and temporary mode;
- reason/interface request being satisfied;
- timestamp and authenticated actor authorizing the transfer;
- whether the source lane is blocked, released, or retains disjoint paths;
- expiration/return condition when temporary;
- resulting reservation-registry transition identity.

Safety rules:

- a transfer cannot broaden beyond paths the source lane actually owns;
- overlapping source/destination write authority must not exist during transfer;
- partial-path transfer must leave the source with an explicitly narrowed remaining reservation;
- return of ownership is another audited transition, not automatic branch activity;
- if current automation cannot represent the transfer atomically, use release/narrow/reclaim or a serialized convergence ticket rather than informal simultaneous editing.

## Repository examples

### Nested feature package

```text
FEATURE-A
  exclusive_write: src/investigation_world/feature_a/**

FEATURE-B
  exclusive_write: src/investigation_world/feature_b/**
```

These are safely parallel.

A separate ticket claiming `src/investigation_world/**` would collide with both and should be narrowed or serialized.

### `src/**/__init__.py`

A package-local `__init__.py` entirely inside one feature's owned subtree may remain `exclusive_write` for that feature.

An `__init__.py` that aggregates exports across independently owned feature packages is a shared integration surface and should normally be `convergence_only`. Provider lanes should expose their implementation locally and request the convergence owner to add shared exports.

### Root CLI

A root CLI/router that registers many independent packages is `convergence_only` unless a dedicated CLI lane exclusively owns the complete file for the relevant wave. Feature lanes should provide callable entry points inside their own packages and request registration.

### `pyproject.toml`

Root package/build metadata is `convergence_only` for parallel feature programs. A feature that needs a dependency or entry point records an interface/integration request; it does not opportunistically modify `pyproject.toml`.

### Workflows

A feature-specific workflow file such as `.github/workflows/foo-validation.yml` may be `exclusive_write` to one lane when no other work owns it.

Shared workflows such as central CI/security/release orchestration should be `convergence_only` or have a dedicated exclusive workflow owner. A claim on `.github/workflows/**` conflicts with every nested workflow writer and should be avoided unless global workflow convergence is the actual mission.

### Documentation

Documentation should be assigned narrowly, for example:

```text
exclusive_write: docs/roadmap/path-ownership.md
```

rather than:

```text
exclusive_write: docs/roadmap/**
```

unless a ticket genuinely owns every roadmap document. A documentation subtree reservation is not harmless: it blocks nested policy work exactly like a source-code subtree reservation.

### Fixtures

A static fixture authored specifically for one feature is usually `exclusive_write` with that feature or its dedicated test lane.

A committed fixture generated from canonical inputs should be `shared_generated`: the designated generator owns committed regeneration, while consumers may reproduce it ephemerally and compare hashes/results.

A shared hand-authored fixture consumed across many subsystems should have one explicit owner or a serialized convergence ticket. “Used by everyone” is not “editable by everyone.”

## Interface and dependency behavior

Dependencies answer execution order/availability questions; ownership answers write authority. They must remain orthogonal.

Therefore:

- `A depends on B` does not authorize A to edit B;
- a hard-merge dependency can require B to merge before A proceeds without sharing B's paths;
- a read-only consumer may start when dependency policy permits while the provider retains exclusive writes;
- a missing interface creates an `interface_request`, not a path claim;
- convergence work may integrate already-reviewed provider interfaces without becoming the provider owner.

## Relationship to review and merge

Path ownership answers who may edit a path during coordinated work. It does not answer whether the resulting change is correct or may merge.

In particular:

- ownership does not waive independent review;
- ownership does not turn green CI into merge authority;
- a reviewer does not acquire write ownership by finding a defect;
- a convergence owner does not gain authority to change provider semantics merely because it owns the shared integration file;
- release, sealed/private, paid-compute, external-account, and qualification authorities remain separate.

## Validator falsifiers

The ownership implementation is incorrect if any of these are possible:

1. `src/foo/**` and `src/foo/bar/**` are accepted as simultaneous independent writers;
2. an exact nested file is considered free while an active ancestor subtree owns it;
3. a `read_only` dependency is treated as permission to commit edits;
4. multiple arbitrary consumers can commit the same `shared_generated` artifact;
5. a feature lane can directly edit a `convergence_only` root/shared path because it depends on the convergence owner;
6. an `interface_request` silently becomes provider write ownership;
7. current PR diff narrowness silently overrides a broader declared reservation;
8. an ownership transfer occurs without source, destination, exact paths, actor, reason, and audit history;
9. stale heartbeat alone frees a reservation;
10. ownership is treated as approval, merge authority, qualification, or release authority;
11. a wildcard the validator cannot reason about is assumed disjoint;
12. two unrelated active Work IDs can intentionally share one implementation branch without an explicit stacked-work contract.

## Current automation boundary

This document defines the policy target. Current claim automation and ROADMAP-002 may implement only subsets at any given head.

ROADMAP-LOCK-001 (#228) owns live claim-time reservation enforcement. ROADMAP-004 (#198) owns static roadmap validation hardening. Implementations must cite the exact subset they enforce and must not describe the remaining rules as already automated.

Until the complete machine-readable mode schema exists, issue authors should use narrow explicit Positive ownership paths and narrative read-only/interface/convergence metadata conservatively. Ambiguity fails closed.
