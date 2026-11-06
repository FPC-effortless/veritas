# Manager-thread coordination for Research Lab OS

Status: **implemented read-only manager brief + proposed operating policy**.
This is not a deployed multi-agent scientist, live coordinator service, full-lane
activation, or qualified model-training result.

## Why this exists

The November 2026 "What Comes After Loops" commentary describes a ladder:
single accountable agent -> genuinely independent fan-out -> adaptive effort ->
builder/reviewer pairs -> manager thread -> long-lived leads -> swarms. Its
performance anecdotes are not evidence about *this* lab. Anthropic's
"Patterns and problems in emerging multiagent systems" (2026-08-13) reports
coordination failure modes in autonomous peers, including stalled collaboration.
We will **test** these patterns rather than adopt swarms as a default.

Sources:
- https://www.anthropic.com/research/multiagent-systems
- https://openai.com/devday/2026/
- User-provided third-party transcript, "OpenAI Revealed What Comes After Loops"

## Operating contract

1. **A measurable outcome precedes delegation.** Every scientific lane needs
   exact source and dataset, a falsifiable hypothesis, strong controls, finite
   resources, expected effect, failure criteria and permitted authority.
2. **Start with one accountable builder/researcher.** Do not spawn 18 personas
   merely because 18 lanes are indexed. Prefer source recovery, independent
   no-fit checks, and one bounded admitted next experiment over new committees.
3. **Fan out only genuinely independent work.** Valid examples: read-only
   comparison of different papers, separate source-recovery closures, or
   independent disjoint-file diagnostics. Before fan-out, confirm frozen inputs,
   distinct write scopes, no unresolved dependencies and bounded output
   contracts. Shared mutable code, conflicting branches, protected evaluators
   and one GPU allocation are *not* automatically independent. Existing claim,
   lease and resource mechanisms remain authoritative.
4. **Use a builder -> adversarial reviewer -> independent verifier for risky
   work.** Return review findings to the owning builder when context continuity
   helps; cap repair iterations and stop on unchanged failures. Reviewer/verifier
   must inspect exact source and evidence, and must not self-attest independence.
   A separate scientific replicator and the repository's exact-head approval
   remain mandatory wherever their contracts require them. Never replace
   rigorous scientific controls with a model's self-confidence.
5. **Use stronger reasoning only where justified.** Schedule deterministic
   checks and formatting with lower effort; reserve expensive model inference
   for difficult theory, ambiguous failures and consequential evidence review.
   Compare cost per accepted result; do not prescribe an unmeasured fixed model.
6. **Use a short shared log, not long-lived peer bureaucracy.** Track ownership,
   admitted scope, exact pin, state, blocker, observed job/process, evidence
   and next action. Share discoveries as *evidence*, not as consensus.
7. **Do not auto-escalate to swarms.** An apparent parallel throughput gain is
   invalid if quality, duplication, resource accounting or review completeness
   worsens. Conflicting edits, stalled messaging, runaway retries and large
   queues trigger simplification rather than more managers.

## Implemented: read-only manager snapshot

With an initialized local lab:

    research-lab --root .trainlab/labos manager

Or without installation from repository root:

    PYTHONPATH=integrations/research_lab/src:integrations/trainlab/src:integrations/forge/src \
      python -m research_lab --root .trainlab/labos manager

This returns the versioned research_lab.manager_brief.v1 JSON projection. It
includes the most recent registered round per lane, current task status counts,
a conservative next-action category, declared remaining slot-wall seconds and
micro-USD, and worker heartbeat *observations*. It deliberately excludes raw
errors, task results, artifact paths and private evidence. It does **not**
schedule experiments, create workers, modify claims, inspect real GPU quotas,
verify external bills, prove host persistence or count actual model fits.
REGISTERED_ONLY and HEARTBEAT_RECENT are not proof of live training.

A controller on the user's interactive machine is not a permanent host.
Prove persistence separately with process liveness, durable storage and a
restart/restore exercise; a recurring ChatGPT automation is not a substitute.

## Falsifiable coordination experiment (proposed, not yet run)

Use identical **approved** work packets, source commits, fixed seeds, review
criteria and resource ceilings. Randomize or counterbalance packet order.
Evaluate at least three task classes: independent source inspections, tangled
same-code repairs, and a genuinely admitted research experiment. Do not launch
new costly fits merely to exercise the coordinator.

Compare:
- **A: Single owner**: one competent agent, deterministic tests and required
  external scientific verification.
- **B: Fan-out**: parallel agents only for independently owned tasks; same
  scientific verification and budgets.
- **C: Bounded pair**: owning builder plus separate reviewer/verifier, capped
  repair rounds; same scientific verification and budgets.

Pre-register the primary outcome: number of independently accepted,
evidence-complete work packets / actual end-to-end wall hour. Report secondary
quality, number of genuine failures detected, duplicated work, merge conflicts,
provider/model tokens, *observed* dollars, GPU slot-seconds, repair cycles and
stale work. Do not divide by a fabricated denominator or infer hosting from
queue records. Where a quantity is not metered, report UNKNOWN.

Adopt a more complex coordination pattern only if it increases accepted
evidence-complete throughput without violating hard safety, data, budget,
review or scientific gates. Negative and no-effect results remain in the index.

## Status boundary

The current 18-lane frontier bootstrap is a *research registry*, not 18 active
trained workers. The durable issue is
https://github.com/FPC-effortless/veritas/issues/482. This manager command
is a software increment only. It does not change that issue's hosting,
scientific-qualification or training-execution status.
