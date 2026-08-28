# Cross-runtime semantic conformance

This lane is an independent checker for the generic operational exporters. It does not repair or
special-case exporter behavior. The reference authority is the merged
`PortableOperationalContract` plus `PortableOperationalRuntime` semantics.

## Default policy

A report passes **only** when `semantic_losses` is empty. A required semantic that an SDK cannot
represent is recorded in `unsupported_fields` and also creates an `unsupported_required` semantic
loss. SDK limitations therefore cannot be converted into a passing result.

`AdapterConformanceReport` serializes exactly these fields:

- `mapped_fields`
- `preserved_fields`
- `generated_fields`
- `excluded_private_fields`
- `unsupported_fields`
- `semantic_losses`
- `test_vector_hash`

`passed` is a derived property and is never adapter-configurable.

## Canonical vector

`tests/conformance/fixtures/canonical_vector.json` is a deterministic, synthetic, public-safe test
vector. It performs one retrieval, two state-changing actions, and terminal submission under a
fixed seed. The fixture contains no hidden state, target truth, evaluator weights, private budgets,
or benchmark-derived rows. Its SHA-256 is computed over canonical JSON, so dictionary insertion
order cannot change vector identity.

The checker compares the following normalized dimensions:

1. observations;
2. semantic/public state digests;
3. evidence declarations and retrieval observations;
4. typed action parameters and private transition parameter requirements;
5. executed action outcomes and declared transition observable results;
6. termination contract and per-step termination;
7. truncation;
8. private budget contract and per-step budget status;
9. invariants;
10. target assertions;
11. process requirements;
12. evidence requirements;
13. reward weights and aggregation contract;
14. verifier component vector; and
15. aggregate reward.

The integration test executes the same vector through NeMo, OpenEnv, HUD, Harbor, and Prime. Native
transport envelopes are normalized, while evaluator-private semantics are read only from each
adapter's operator/runtime path. This distinction is intentional: private semantics must be absent
from the evaluated agent's surface but still preserved by the adapter for execution and scoring.

OpenEnv's operator replay takes observations, rewards, termination, truncation and state digests
from the actual OpenEnv envelopes, then attaches budget/verifier fields from the same server-side
results. Prime's evaluator replay returns the complete ordered result trace used by its terminal
reward helper. These are production adapter capabilities; the conformance suite no longer replaces
either runtime with a recording test double.

## Private-field accounting

`excluded_private_fields` means "intentionally excluded from the agent-facing surface", not
"ignored by conformance". The checker still compares operator-side target assertions, invariants,
transition rules, process requirements, evidence requirements, budgets, and evaluator/reward
semantics. Loss diagnostics contain semantic paths only; they do not serialize differing values.

The common private exclusions are:

- `private.semantic_state.initial_state`
- `private.semantic_state.target_assertions`
- `private.semantic_state.invariants`
- `private.transitions`
- `private.process`
- `private.required_evidence_ids`
- `private.budgets`
- `private.evaluator`
- `private.oracle_metadata`

## Required falsifiers

`tests/conformance/test_falsifiers.py` perturbs one semantic at a time and requires a failing report
for each of:

- reward weight;
- action parameter;
- observable/action result;
- termination;
- invariant;
- budget; and
- evidence requirement.

It also verifies that a missing required field and a missing field mapping fail closed, and that the
test-vector hash is deterministic but change-sensitive.

## Interpreting a failure

A conformance failure is evidence about an exporter; it is not authorization for this lane to edit
that exporter. Report the semantic path and hand the mismatch to the owning exporter lane. Do not
weaken the required field set, copy evaluator-private values into public fixtures, or add an adapter
exception merely to obtain a green result.
