# Fluent Environment Authoring

`EnvironmentBuilder` is the simple author-facing façade over the existing Veritas operational model.
It reduces constructor boilerplate without introducing a second runtime, verifier, task format, or
portable contract.

```python
from investigation_world.authoring import EnvironmentBuilder
from investigation_world.operational import ActionKind, WorldDomain

env = (
    EnvironmentBuilder(
        name="supplier-approval",
        domain=WorldDomain.ENTERPRISE_OPERATIONS,
        objective="Approve and activate the supplier without bypassing authority.",
        role="procurement operator",
    )
    .system("procurement")
    .action(
        "request_approval",
        kind=ActionKind.ESCALATE,
        system="procurement",
        description="Request finance approval.",
        parameters=("supplier_id",),
    )
    .initial_state(**{"supplier-42.approved": False})
)

episode = env.build()
contract = env.compile()
```

## Architecture boundary

`build()` creates the canonical existing `OperationalEpisode`. All of its public/private, action,
evidence, invariant, process, and oracle validation still runs. The builder does not bypass or fork
those rules.

`compile()` simply calls the existing `compile_operational_episode()` portable compiler. Unsupported
semantics therefore fail at the same boundary as hand-authored episodes.

The builder intentionally does **not** implement:

- a new transition runtime;
- a new verifier;
- an alternative hidden-state representation;
- exporter-specific behavior;
- sandbox/provider orchestration;
- a second reward model.

## Identity

When world/task/episode IDs are not supplied explicitly, the builder derives them deterministically
from the complete authored semantic specification. Rebuilding the same specification produces the
same identities; changing state, actions, effects, constraints, evidence, budgets, or metadata changes
the derived identity.

Explicit IDs remain available for externally governed environment identities.

## Public/private authoring

Public task metadata, evaluator-private oracle metadata, and episode metadata are separate inputs.
`OperationalEpisode.public_payload()` remains the agent-safe projection; private oracle metadata is
not copied into it.

Required evidence must reference an actual agent-observable `OperationalRecord`. The builder rejects a
private locator or undeclared record as a required evidence ID.

## Typed action schemas

The current native `PublicActionSpec` exposes parameter names rather than parameter value types. The
builder does not invent types. Environments originating in Woyengi may carry the richer public action
schema overlay already supported by the portability path.

A future native operational-model version may add first-class JSON input/output schemas, but that must
be an explicit semantic-version change because the Portable Operational Contract pins the current
runtime/model/verifier source semantics.
