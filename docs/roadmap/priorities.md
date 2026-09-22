# Roadmap priority and execution semantics

Veritas roadmap metadata has two independent questions:

1. **How strategically valuable is this work?**
2. **Can an agent execute it now without violating dependencies, ownership, or coordination state?**

These dimensions must never be collapsed into one rank. A flagship item may be strategically first and operationally blocked, while a lower-ranked enabling item may be the correct next task because it is READY and lies on the critical path.

This document defines the canonical metadata semantics for ROADMAP-PRIORITY-001. It does not redefine which GitHub source is authoritative for live coordination state; that remains governed by the repository's work-state/status-state-machine policy.

## Canonical metadata

Each roadmap item should expose the following fields when represented in a generated roadmap view or machine-readable snapshot.

| Field | Meaning | Allowed / recommended values |
| --- | --- | --- |
| `strategic_priority` | Relative business/product/research importance, independent of executability | `P0`, `P1`, `P2`, `P3`, or another explicitly documented ordinal scale |
| `execution_state` | Current coordination/execution state | `BLOCKED`, `READY`, `CLAIMED`, `REVIEW`, `DONE`, `SUPERSEDED` |
| `critical_path` | Whether delaying this item delays a declared program dependency chain | boolean |
| `parallel_wave` | Program/wave grouping used to identify work that may be considered together | stable string or `null` |
| `estimated_effort` | Optional coarse planning signal, not a delivery promise | e.g. `small`, `medium`, `large`, or `null` |
| `risk` | Optional coarse implementation/coordination risk | e.g. `low`, `medium`, `high`, or `null` |

`strategic_rank` may be used instead of `strategic_priority` when an existing representation requires a numeric ordering, but it has exactly the same semantics: value ordering only, never readiness.

## Strategic priority

Strategic priority expresses expected leverage or importance if the work is successfully completed. It may reflect product value, scientific leverage, buyer value, risk reduction, dependency leverage, or another explicitly documented strategic criterion.

Strategic priority:

- may remain stable while execution state changes repeatedly;
- may place a blocked flagship above all executable work;
- does not satisfy dependencies;
- does not grant path ownership;
- does not create a claim;
- does not authorize merge, release, sealed/manual actions, paid compute, or qualification;
- must not be used as a substitute for evidence that a work item is READY.

Changing strategic priority is a planning decision. It is not a work-state transition.

## Execution state

Execution state answers whether and where the item is in the repository coordination lifecycle.

| State | Execution meaning |
| --- | --- |
| `BLOCKED` | A declared dependency, interface, authority, or other blocker prevents execution/continuation |
| `READY` | Eligible to be selected for a new claim, subject to live ownership/concurrency checks |
| `CLAIMED` | Actively owned by a recorded agent; another implementation agent must not take the same lane |
| `REVIEW` | Implementation has been handed off for independent review/follow-up; not a fresh implementation slot |
| `DONE` | Integration/evidence boundary for the work item has been satisfied under the coordination policy |
| `SUPERSEDED` | Replaced by another work item or design; not executable as the canonical lane |

Only `READY` items are candidates for a **new implementation claim**. Selection must still verify dependencies, path ownership, branch state, and concurrency against live GitHub state.

A priority renderer or generator must not infer `READY` from strategic rank, wording such as "highest priority", issue ordering, milestone position, or business importance.

## Critical path

`critical_path=true` means an item currently lies on a declared dependency chain whose delay holds back a program outcome. It is orthogonal to strategic priority.

Consequences:

- a modestly ranked enabling task can be `critical_path=true`;
- a strategically dominant flagship can be `critical_path=false` for the current wave if it is waiting on prerequisites;
- critical-path status does not override `BLOCKED`;
- critical-path status does not bypass exclusive ownership or review requirements.

When choosing among multiple READY items of similar strategic value, critical-path status is a legitimate scheduling signal. It is not an authorization signal.

## Parallel wave / program

`parallel_wave` groups work that belongs to the same execution or program wave. It helps render independent lanes and identify possible concurrency, but it does not prove that two items can run in parallel.

Before concurrent execution, the normal repository checks still apply: no dependency edge between the lanes, disjoint positive ownership, no negative-ownership conflict, no shared/root integration conflict, and provider/schema work preceding dependent consumers where required.

## Effort and risk

Effort and risk are deliberately coarse unless backed by measured data.

- `estimated_effort` is a planning band, not a promised duration or completion date.
- `risk` records implementation, verification, dependency, or coordination uncertainty.
- neither field changes execution state;
- neither field should be converted into a guaranteed timeline.

If evidence is insufficient, use `null`/`UNKNOWN` rather than fabricated precision.

## Selection rule for agents

The executable queue is derived from readiness first, then planning signals are used to order eligible work.

A conforming selector behaves conceptually as:

```text
candidates = items where execution_state == READY
candidates = candidates that still pass live dependency + ownership + concurrency checks
order candidates using strategic_priority, critical_path, wave/program context, risk/effort, and task-specific policy
claim exactly one lane through the coordination protocol before editing
```

The inverse is forbidden:

```text
highest_strategic_priority -> assume READY -> start editing
```

Strategic importance can influence which READY item is chosen; it cannot manufacture readiness.

## Generator and roadmap-view contract

Any dependency/wave generator or roadmap view consuming this metadata must preserve both dimensions separately.

It must:

1. emit `strategic_priority`/`strategic_rank` without rewriting `execution_state`;
2. emit live `execution_state` without deriving it from priority;
3. preserve `critical_path` and `parallel_wave` as separate fields;
4. keep blocked high-priority items visible rather than dropping or silently demoting them;
5. keep READY enabling work visible even when its strategic rank is lower;
6. label effort/risk as estimates, never guaranteed schedules;
7. expose enough information for an agent or reviewer to distinguish "important" from "executable now".

A generator that sorts the display by strategic priority may do so, provided the execution state remains explicit and the READY queue is not computed from that sort order.

## Example

| Work item | Strategic priority | Execution state | Critical path | Parallel wave | Interpretation |
| --- | --- | --- | --- | --- | --- |
| GOLD flagship | `P0` | `BLOCKED` | true | `gold` | Highest value, but not claimable until dependencies clear |
| Semantic trace prerequisite | `P1` | `REVIEW` | true | `experience` | Important enabling work awaiting independent review |
| Coordination policy | `P2` | `READY` | true | `roadmap` | Lower strategic rank but valid next executable work |
| Optional dashboard polish | `P3` | `READY` | false | `ux` | Executable, but generally behind critical-path READY work |

The example intentionally demonstrates that `P0` does not mean READY and `P2` can be the correct next implementation lane.

## Falsifiers

The semantics are violated if any of the following occurs:

- rank `#1` or `P0` automatically transitions an item to READY;
- a blocked flagship is presented as executable merely because it is strategically first;
- a lower-ranked READY enabling task disappears from the executable queue despite being on the critical path;
- a dependency/wave generator stores only one combined priority/readiness field;
- `parallel_wave` is treated as proof of non-overlapping ownership;
- effort estimates are presented as guaranteed timelines;
- a planning metadata edit silently mutates claim/review/done coordination state.

## Evidence boundary

These semantics define planning and rendering metadata. They do not themselves implement the coordination state machine, dependency synchronizer, claim workflow, scheduler, merge policy, release workflow, or qualification system. Those systems may consume this metadata, but must preserve the separation defined here.
