# Portable Operational Contract

`investigation_world.portable_contract` is Veritas's canonical executable portable operational IR.
It is an additive projection of the existing `OperationalEpisode` semantics; it does not replace
`OperationalEpisode`, `HiddenOracle`, `OperationalRuntime`, or the operational verifier.

The contract is intended to be the semantic input to later runtime compilers. NeMo Gym, OpenEnv,
HUD, Prime Verifiers, Harbor, and other runtime-specific formats are deliberately outside this
package.

## Source semantics pin

Version `1.0.0` of this contract compiler is pinned to Veritas commit
`98500d7e081e48f8e291be51ba360ff851aa88fe` and to the exact Git blobs for:

- `operational/models.py`: `69877f041a74826a480e7d8d6ab6f459eee1ddcb`
- `operational/runtime.py`: `c82dfd6845a6f33f9bc636874d5cc23b59c37d3f`
- `operational/verifier.py`: `37c344287cb19b8e22bd705235bcfab67989065e`

Compilation fails closed if those source semantics change. A future operational-runtime change must
therefore be reviewed and represented explicitly by a new portable compiler version rather than
silently inheriting old assumptions.

## Contract structure

The top-level `PortableOperationalContract` has two structural partitions:

```text
PortableOperationalContract
├── public: PortablePublicContract
│   ├── identity + provenance
│   ├── objective + role + public task constraints
│   ├── public observation/state schema
│   ├── typed action definitions and JSON input/output schemas
│   ├── public evidence records
│   └── public runtime interaction contract
└── private: PortablePrivateContract
    ├── initial hidden state
    ├── target assertions
    ├── final and trajectory-wide invariants
    ├── ordered hidden transitions, preconditions and effects
    ├── required/forbidden/order/count process rules
    ├── required evidence IDs
    ├── separate cost and tool-call budgets
    ├── deterministic reset identity
    ├── evaluator binding
    └── seven-component reward contract
```

All models use Pydantic's frozen/extra-forbid contract configuration. Ordered operational semantics
such as action lists, transition declaration order, prior-action order, and invariants are retained as
tuples. Arbitrary semantic values must be JSON-compatible; values that would require coercion fail
closed.

## Public/private boundary

Use only `serialize_public_contract(contract)` for an agent-visible artifact. It serializes the
`PortablePublicContract` directly and cannot traverse the evaluator-private partition.

The public serialization contains no:

- hidden initial state;
- target assertions or target truth;
- hidden transition preconditions/effects;
- required evidence locators;
- forbidden-action labels from the oracle;
- evaluator binding or evaluator bytes;
- oracle metadata;
- full private-sensitive `contract_id`.

The compiler also rejects reserved evaluator-private semantic keys if they are placed inside a
nominally public source payload. This prevents metadata from being used to smuggle an oracle field
through the public projection.

`serialize_portable_contract(contract)` is the complete evaluator-bearing serialization. Treat it as
private benchmark/runtime material.

## Content identity

Serialization is canonical UTF-8 JSON with sorted object keys and no insignificant whitespace.
Content addresses are SHA-256 based:

- `public.public_id` binds only the agent-visible projection;
- `contract.contract_id` binds the complete public + evaluator-private contract;
- `private.reset_identity` binds task/world/episode identity plus the hidden initial state.

Changing a hidden transition, budget, verifier binding, target, invariant, or reset state changes the
full contract ID without changing the public ID when the public semantics are unchanged. Equivalent
mapping insertion order produces identical bytes and IDs.

The complete contract deliberately does **not** expose its full content ID through the public
serialization. That avoids turning a digest of private low-entropy semantics into an agent-visible
oracle side channel.

## Action semantics

`PublicActionSpec` currently provides parameter names, not parameter value types. The portable
compiler does not invent types. Each declared parameter is therefore represented as a required JSON
property accepting any JSON value, while additional parameters remain allowed because
`OperationalRuntime.act()` currently accepts them. The public output schema guarantees only the base
result object shape; exact transition-dependent observable values remain in the private transition
contract so they are not leaked before execution.

Each `PortableTransitionContract` preserves:

- declaration index and first-match selection order;
- required parameter values;
- state assertion preconditions;
- ordered successful-prior-action preconditions;
- hidden state mutations;
- system-observable success and blocked results;
- hidden side effects;
- transition-local forbidden status;
- consequence severity;
- default blocked and no-matching-transition behavior.

An action with no declared transition retains the current runtime's successful no-op/effect-applied
behavior.

## Public runtime contract

The IR represents the existing retrieval/action/submission interaction modes rather than reducing an
episode to a prompt/answer row.

Built-in operations preserve current behavior for:

- `search(system, query, limit=10)`;
- `search_all(query, limit=10)`;
- `open_record(record_id)`;
- `submit(EpisodeSubmission)`.

Search tokenization, all-term matching, occurrence-count scoring, deterministic tie-breaking, and the
`1..100` result-limit clamp are explicit. The `search` permission failure is also explicit: an
unpermitted system returns an empty result before charging or checking the closed state.
`open_record` preserves the current charge-before-missing-record error behavior.

## Budgets

Cost and tool calls are different resources and cannot be merged:

```text
cost       unit=cost_units  reject if post-charge usage > maximum
tool_calls unit=calls       reject if current usage >= maximum before charge
```

Every retrieval and domain action declares both charges. A zero-cost domain action still consumes one
tool call, matching `InvestigationBudget.charge()`.

Budget exhaustion raises the existing error and does not itself close the episode. Submission closes
the episode after evaluation.

## State, invariants, and process

`SemanticStateProjection` retains evaluator-private initial state and structural
`PortableStateAssertion` values. Invariants cannot degrade into descriptions: every invariant
contains an assertion, severity, scope, and an explicit `trajectory_wide` marker that must agree with
`scope == "always"`.

The process contract separately retains:

- required actions;
- forbidden actions;
- ordered-action subsequence requirements;
- minimum action counts;
- the rule that only applied, unblocked events count as effective events.

This distinction is required because the verifier combines single required actions and count
requirements while separately penalizing ordering failures and forbidden actions.

## Evaluator and reward

The evaluator binding points to:

```text
investigation_world.operational.verifier:verify_operational_episode
```

and pins its source Git blob. The reward vector is represented structurally with the current weights:

```text
0.30 outcome
0.20 state
0.15 constraints
0.10 side_effects
0.10 process
0.05 efficiency
0.10 evidence
```

The binding is private. It identifies the existing verifier; this package does not replace or fork the
verifier.

## Fail-closed compilation

`compile_operational_episode()` raises `UnsupportedOperationalSemanticError` instead of guessing when
semantics cannot be preserved. Current failure classes include:

- changed pinned operational model/runtime/verifier source semantics;
- changed source model field shape;
- a source episode that no longer satisfies `OperationalEpisode` validation;
- non-finite numbers;
- non-string JSON object keys;
- tuples, sets, bytes, or other arbitrary values in `Any` fields that would need lossy JSON coercion;
- duplicate action parameter names that cannot be represented by a valid JSON Schema `required`
  array while preserving current error behavior;
- evaluator-private structural keys embedded in public metadata/records.

No unsupported condition is replaced by a default value or prose note.

## Semantic falsifier

`assert_operational_semantic_equivalence(episode, contract)` independently recreates the canonical
projection and reports the first structural difference with `SemanticRoundTripError`. It catches
losses in source semantics as well as derived runtime semantics, including dropped transitions,
invariants, budget details, schemas, or evaluator bindings.

Runtime/exporter code should invoke this check when transforming or caching a contract if it has any
reason to suspect the contract was modified after compilation.

## Public API for later agents

Later runtime/compiler agents should import only from `investigation_world.portable_contract`.
The supported API is:

```python
from investigation_world.portable_contract import (
    CONTRACT_SCHEMA_VERSION,
    InteractionMode,
    PortableActionDefinition,
    PortableBudgetContract,
    PortableContractError,
    PortableEvaluatorBinding,
    PortableEvidenceContract,
    PortableEvidenceRecord,
    PortableInvariant,
    PortableOperationalContract,
    PortablePrivateContract,
    PortableProcessContract,
    PortableProvenance,
    PortablePublicContract,
    PortableResourceCharge,
    PortableResourceLimit,
    PortableRewardComponent,
    PortableRewardContract,
    PortableRuntimeContract,
    PortableRuntimeOperation,
    PortableSearchContract,
    PortableStateAssertion,
    PortableStateContract,
    PortableTaskIdentity,
    PortableTerminationContract,
    PortableTransitionContract,
    PortableVisibility,
    SemanticRoundTripError,
    SemanticStateProjection,
    UnsupportedOperationalSemanticError,
    assert_operational_semantic_equivalence,
    compile_operational_episode,
    serialize_portable_contract,
    serialize_public_contract,
)
```

The primary consumption path is:

```python
contract = compile_operational_episode(episode)
full_private_bytes = serialize_portable_contract(contract)
agent_visible_bytes = serialize_public_contract(contract)
```

External-runtime exporters should consume `PortableOperationalContract`; they should not reinterpret
`HiddenOracle` or reach into the operational runtime to create a second semantic mapping.
