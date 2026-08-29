# Semantic MachineExperience annotations

TRACE-002 derives semantic annotations from canonical `TrajectoryV2` evidence plus an exact `PortableOperationalContract` without changing execution, verifier, or trajectory semantics.

## Boundary

The compiler consumes two authorities:

1. the canonical trajectory, which preserves event ordering, structured event payloads, state digests, evidence/resource references, costs, visibility, model/harness/runtime/verifier identity, and provenance where producers recorded them;
2. the exact portable operational contract, which preserves public actions/runtime operations and evaluator-private transitions, process requirements, invariants, budgets, evidence requirements, and verifier component semantics.

Because TRACE-002 derives evaluator-private semantics, the trajectory must bind the **full** portable contract identity. A missing contract reference or a reference containing only `public_id` fails closed rather than authorizing process, transition, invariant, budget, or verifier derivation from private evaluator state. A public contract identity proves only the public task/runtime surface and is not interchangeable with `contract_id`. This invariant is enforced in the core compiler itself, not only by the package-level binding wrapper.

The compiler does **not** inspect natural-language transcript text to infer an action, subgoal, permission, cause, or evidence flow. Structured facts that are not represented remain `UNKNOWN` or `NOT_APPLICABLE`.

## Produced semantics

For each canonical trajectory event the compiler may derive:

- semantic action or runtime-operation identity;
- state-digest transition relation, including digest algorithm and scope;
- evaluator-private process requirement relevance;
- candidate invariant effects from transition/state-key overlap;
- evidence created/consumed/referenced when direction is structurally represented;
- public static system-permission compatibility, without inventing dynamic actor authority;
- declared resource charges and observed event cost;
- evaluator-private verifier-component relevance candidates grounded in contract structure;
- capability and subgoal span candidates.

A state transition is `DERIVED` only when both state digests use the same algorithm and scope. Different digest domains are not comparable and remain `UNKNOWN`, even when their digest strings happen to match.

Derived visibility is provenance-sensitive. A semantic fact derived from a resource call or nested reference inherits at least the visibility of that source, and downstream spans/records preserve that classification rather than widening it through a more-public containing event.

The resulting `SemanticAnnotationBundle` is content-derived and binds:

- canonical trajectory identity;
- full portable-contract identity;
- public portable-contract identity;
- trajectory verifier identity/version;
- evaluator semantics identity.

Changing material trajectory or contract semantics therefore changes or invalidates the annotation bundle.

## MachineExperience composition

`apply_semantic_annotations()` returns a new `MachineExperience` containing the bundle's `ExperienceSpan` and `StructuralRecord` outputs. It never mutates the source `TrajectoryV2` or source `MachineExperience`, and the underlying `experience_id` remains derived only from the canonical trajectory identity.

Composition revalidates the bundle's authority before accepting its outputs: the exact trajectory identity, full portable-contract digest, verifier identity/version, and every annotation's event index/step/type must match the embedded trajectory. The enriched experience records the full bundle identity as an evaluator-private derivation reference so trusted lineage remains inspectable without widening it into public output.

Private process, invariant, transition, and verifier facts are emitted with evaluator-private visibility. Public and buyer-safe bundle projections omit the full contract/evaluator identity, the private-bound `bundle_id`, and the private-bound canonical `trajectory_id`. Safe event/span/record identities are recomputed from the visibility-filtered projection instead of reusing full identities that commit to evaluator-private semantics. The safe projection therefore exposes only the independently content-bound public contract identity plus facts whose source visibility permits disclosure. The internal bundle retains its full content-derived identities for trusted lineage and reverification.

## What UNKNOWN means

`UNKNOWN` is not failure. It means the current canonical evidence does not establish the requested semantic fact. Examples include:

- an event mentions an action name only in prose;
- only one of the two state digests is present;
- state digests use different algorithms or scopes;
- an evidence reference exists but the trace does not say whether it was created or consumed;
- a runtime operation declares permission failure behavior but the trajectory does not preserve the actor's dynamic permission state;
- a private transition could affect an invariant, but digest-only state evidence cannot prove field-level invariant satisfaction.

The compiler intentionally prefers incomplete truthful annotations to fabricated semantic completeness.

## Harness/runtime independence

The compiler does not assume a `system prompt + tools` agent loop. It uses canonical trajectory and portable-contract evidence, so terminal agents, custom Python agents, MCP-based agents, recursive/subagent harnesses, and future harness architectures can share the same annotation contract when they emit equivalent canonical evidence.

Harness identity remains trajectory metadata; the annotation layer does not implement or control the harness.

## Current trace-graph limitation

`TrajectoryV2` is currently an ordered event sequence. TRACE-002 can preserve semantic spans over that sequence, but it cannot faithfully manufacture structures the source schema does not contain, including:

- parent/child subagent traces;
- parallel branches;
- abandoned branches;
- explicit join/dependency edges;
- actor-to-actor communication edges;
- branch-local state lineage.

Those require a separate trace-graph evolution with compatibility back to canonical trajectories. They are deliberately not encoded as ad hoc annotation metadata here.

## Actor limitation

The current operational contract represents role, permitted systems, tools/actions, state, and evaluator semantics, but it does not yet define first-class simulated world actors with independent private state, knowledge, goals, memory, policy, deception/error behavior, or communication channels.

TRACE-002 therefore reports only the authority facts actually represented by the current contract. First-class environment actors belong in the executable-world/portable-semantic layer, not in semantic annotation inference.

## Training boundary

Semantic annotation is not a tokenizer, renderer, trainer, optimizer, RL algorithm, or model-serving layer. A downstream training projection may later bind renderer/tokenizer identity, token spans, masks, trainable spans, or log probabilities to semantic MachineExperience, but those representations must remain downstream projections with lineage back to the canonical semantic experience.

TRACE-002 establishes semantic trace enrichment only. It does not establish failure diagnosis, causal attribution, learning readiness, training qualification, learning efficiency, Frontier usefulness, commercial readiness, or release authority.
