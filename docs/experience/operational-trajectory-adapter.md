# Operational Runtime to TrajectoryV2 Adapter

Work ID: `G-03` (issue #395). Ordered by `docs/experience/canonical-ontology-gap-audit.md`
§7 (row G-03) and §10 (item 3.4), which place it immediately after G-01 (capability contract
content identity) and G-02 (operational capability binding).

Status: **identity and record conversion only.** This document specifies the adapter that
projects an already-executed `OperationalRuntime` onto the canonical `TrajectoryV2`. It does
not implement, specify, or pre-implement any downstream binding. G-04, G-09, and G-10 remain
their own lanes.

Owning Work ID: `G-03` / #395 — branch `feat/operational-trajectory-adapter`. Positive
ownership, per the Work Contract: `src/investigation_world/trajectory/adapter.py`;
`src/investigation_world/trajectory/__init__.py`;
`tests/trajectory/test_operational_runtime_adapter.py`;
`docs/experience/operational-trajectory-adapter.md`. That is **four** paths, and `adapter.py`
is the first of them — it is the implementation surface for this lane, holding the context
model, the event projectors, and the entry point. The two symbol names
`OperationalRuntimeAdapterContext` and `trajectory_v2_from_operational_runtime` are reserved to
this lane.

## 1. The problem

`OperationalRuntime` (`src/investigation_world/operational/runtime.py`) is the executable
surface every Veritas operational world runs on: it executes public actions against a private
oracle, charges a budget, records `ActionEvent` objects, and scores a submitted episode through
`verify_operational_episode`. `TrajectoryV2` (`src/investigation_world/trajectory/models.py`) is
the canonical, identity-bound, buyer-safe record that the reverification engine, Observatory,
and the experience layer all consume.

There was no path between them. A runtime that had actually run could not be recorded as a
trajectory without a caller hand-building each `TrajectoryEvent` — which is exactly what
`tests/trajectory/reverify/test_reverification.py` had to do to construct a reverifiable
fixture, and what `examples/environments/veritas_environment_examples/machine_experience_ready.py`
still does. That hand-building is the hazard this gap exists to remove: the caller rewrites the
public projection of actions it did not record, re-scores an evaluation it already holds, and
has nowhere to put the verifier-only fields an `ActionEvent` carries. Three consequences follow:

| Consequence | Where it bites |
|---|---|
| Reverification requires an exact event shape the caller must guess | `reverify/engine.py::_decode_operational_act`, `_decode_submission`, `_validate_submission` |
| The evaluation has no source after `submit()` returns it | `OperationalRuntime.submit()` returns a `VerificationBreakdown` and retains nothing |
| Verifier-only truth has no declared home, so it leaks or is dropped | `ActionEvent.state_changes`, `side_effects`, `forbidden`, `consequence_severity`, `blocked_reason` |

The adapter is a **record converter**, not a runtime. Its contract is: given a closed runtime
and the evaluation the caller already holds, emit the canonical trajectory that describes
exactly what happened — nothing more, and nothing invented.

## 2. The mechanism

The design mirrors the existing legacy adapter in the same module,
`trajectory_v2_from_rollout_trace`, and its `RolloutTraceAdapterContext`. Two precedents,
reused rather than duplicated:

- `RolloutTraceAdapterContext` — the "unknown, not default" discipline for identity facts a
  source cannot supply.
- `_resource_id` / `_resource_call` — the single resource-call convention, which resolves on
  the `method` / `args` / `kwargs` payload shape this adapter also emits.

### 2.1 The entry point and its precondition

```python
def trajectory_v2_from_operational_runtime(
    runtime: OperationalRuntime,
    *,
    context: OperationalRuntimeAdapterContext | None = None,
) -> TrajectoryV2:
```

The runtime must be **closed** (`runtime.closed`), or the call raises `ValueError`. This is
not a convenience check. `TrajectoryV2` requires an `original_evaluation`, and only a submitted
runtime has one. An adapter that accepted an open runtime would have to either score the
episode itself — re-scoring, forbidden — or emit a trajectory with a fabricated evaluation.

The adapter never calls `act()`, `submit()`, or any mutating method on the runtime. It reads
`runtime.events`, `runtime.episode`, `runtime.state_snapshot()`, `runtime.budget`, and
`runtime.closed`, and writes nothing back.

### 2.2 The context

`OperationalRuntimeAdapterContext` mirrors `RolloutTraceAdapterContext` field for field where
the sources are structurally similar, and differs in four places where the operational source
is not the legacy source:

| Field | Why it differs |
|---|---|
| `breakdown: Any = None` | Mandatory in practice. `OperationalRuntime.submit()` returns the `VerificationBreakdown` without retaining it, so the caller supplies the object it already holds. |
| `submission: Any = None` | Mandatory in practice. The reverification engine requires exactly one `submit` event whose payload *is* the `EpisodeSubmission`; `submit()` does not record an `ActionEvent`, so the adapter emits it from the context. |
| `verifier: VerifierIdentity \| None = None` | `TrajectoryV2.validate_trajectory` requires `original_evaluation.verifier == trajectory.verifier`. The legacy context defaults to a blank `VerifierIdentity`; this one defaults to the statically authorized binding (§2.5) rather than inventing an identity. |
| `initial_state_digest` / `final_state_digest` | Override the computed digest outright and win over `scope`. The reverification engine compares these against `stable_hash` evidence digests, so a caller that already holds the exact digest passes it through verbatim. |

`breakdown` and `submission` are typed `Any`, not `VerificationBreakdown` / `EpisodeSubmission`,
for one reason: importing those names at module scope would import
`investigation_world.operational.models` at runtime, and `trajectory` must stay importable
without pulling `operational` into its import graph (§5). They are `TYPE_CHECKING` imports for
the static checker, and the runtime never validates their type — it calls
`breakdown.overall_reward` and `getattr(breakdown, name)`, which fails loudly on anything that
is not the real object.

### 2.3 The event payload contract

Each `ActionEvent` projects to exactly one `TrajectoryEvent`:

```python
{
    "method": "act",
    "action_name": event.action_name,
    "args": [event.action_name],
    "kwargs": copy.deepcopy(event.parameters),
    "success": bool(event.effect_applied and not event.blocked),
}
```

This is not a chosen shape. It is the shape `reverify/engine.py::_decode_operational_act`
recovers `(action_name, parameters)` from — `args[0]` carries the action name, `kwargs` carries
the parameters. The adapter emits that form and no other, because there is no second action
vocabulary to support. `step` is `event.sequence - 1`: `ActionEvent` sequences from 1, the
canonical event model from 0, and the engine checks `action_event.sequence == index` starting
at 1, so the mapping is exact in both directions.

The `submit` event is emitted once, after every act event, at step `len(acted)`:

```python
{
    "method": "submit",
    "args": [serialized_submission],
    "kwargs": {},
    "success": True,
}
```

`_decode_submission` accepts `args == [<submission dict>]` — a **mapping**, not the model object,
because it re-validates that mapping through `EpisodeSubmission.model_validate` — and
`_validate_submission` then requires the decoded submission to *equal* the evidence's submission.
The adapter therefore serializes the caller's submission with `model_dump(mode="json")` rather
than embedding the object itself. The payload *is* the submission the caller passed to `submit()`;
the adapter never synthesizes one, because a synthesized submission would fail that equality check
by construction, and a submission that passed it would be a forgery of what the agent claimed.

### 2.4 Where verifier-only truth goes

`ActionEvent` carries six fields that must never reach an evaluated agent or a buyer:
`state_changes`, `side_effects`, `forbidden`, `consequence_severity`, `blocked_reason`, plus
the `effect_applied` / `blocked` booleans. They go into the event's `private_payload`:

```python
private_payload={
    "sequence": event.sequence,
    "kind": event.kind.value,
    "system": event.system,
    "state_changes": copy.deepcopy(event.state_changes),
    "side_effects": copy.deepcopy(event.side_effects),
    "forbidden": event.forbidden,
    "consequence_severity": event.consequence_severity,
    "effect_applied": event.effect_applied,
    "blocked": event.blocked,
}
```

This is load-bearing, not decorative. `TrajectoryV2.public_payload()` and
`buyer_safe_payload()` run every model through `_safe_payload`, which drops any field named in
`_PRIVATE_BUCKETS` — `private_metadata`, `private_payload` — and recurses into dicts doing the
same. So the same mechanism that protects the legacy adapter's `private_metadata` protects the
verifier-only projection here, and the public event payload carries only `method`,
`action_name`, `args`, `kwargs`, and `success`.

The adapter also writes the full breakdown into the trajectory provenance record's
`private_metadata` under `operational_breakdown`, alongside the episode metadata. That is
evaluator-private by the same mechanism, and it is what makes the trajectory self-describing
for an evaluator without making it self-describing for a buyer.

### 2.5 The verifier identity rule

`TrajectoryV2.validate_trajectory` raises when `original_evaluation.verifier !=
trajectory.verifier`. Both are set to the same value, so the rule holds by construction:

1. If the context supplies `verifier`, that identity is used for both.
2. If it does not, the adapter uses `current_operational_verifier_binding().identity`, which is
   `VerifierIdentity(verifier_id=VERIFIER_ENTRYPOINT, version=VERIFIER_SEMANTICS_ID)` — the
   statically authorized local verifier, pinned to a committed git blob sha1 of
   `src/investigation_world/operational/verifier.py`.

The binding is not a name lookup. `OperationalVerifierBinding.__post_init__` rejects an
entrypoint, semantics id, or source blob that is not exactly the authorized one, and
`AuthorizedVerifierRegistry.resolve` is an exact-match `(verifier_id, version)` dict. So the
default is a statement about *which verifier scored this episode*, backed by a content pin, and
not a placeholder string. A caller that knows better overrides it; a caller that does not gets
the truth rather than a guess.

### 2.6 What stays unknown

Everything an `ActionEvent` cannot represent, and everything the runtime does not know, stays
unknown. `None` means *unknown*, not *default*:

| Field | Source | Value when unknown |
|---|---|---|
| `model`, `agent` | not in the runtime | blank `ModelIdentity` / `AgentIdentity`, overridable |
| `harness`, `runtime` | not in the runtime | `None` versions |
| `reset.seed`, `reset.reset_id` | not in the runtime | `None` |
| `task.split`, `task.taskset_version` | not in the episode | `None` |
| `usage.input_tokens`, `provider_cost`, `total_cost` | not in the runtime | `None` (only `environment_cost` is known) |
| `termination.truncated` | not in the runtime | `None`; `terminated` defaults to `True` because a submitted episode terminated |
| `failure` | not in the runtime | `FailureCategory.UNKNOWN` with no confidence |

`world_id` and `task_id` are *derived*, not unknown: `episode.world_id` and
`episode.task.task_id` are the episode's own identity and are always present. `world_id` is
overridable through the context because a caller may know the bundle version the episode was
compiled from, and the episode does not.

### 2.7 State digests

`runtime.state_snapshot()` is documented *"harness-visible state snapshot; do not expose
directly to evaluated agents."* The state is seeded from `episode.oracle.initial_state`, which
is private-by-construction. The adapter therefore digests it at a caller-chosen scope and
**defaults to `StateDigestScope.SEMANTIC`**, not the legacy adapter's `PUBLIC_SEMANTIC`:

```python
StateDigest(digest=canonical_hash(runtime.state_snapshot()), scope=scope)
```

`canonical_hash` is the trajectory digest function — sorted-keys JSON, sha256 — and is the same
function that digests the whole trajectory's `identity_payload`. Note this differs by design from
the reverification evidence model, which uses `foundry.models.stable_hash` for its state digests
(`json.dumps(..., default=str)`, no canonicalization). A trajectory that must bind to evidence
therefore supplies `initial_state_digest`/`final_state_digest` explicitly — the caller already
holds the replay state — and those override the computed value. That is the reconciliation path
the round trip in §4 exercises, rather than a shared digest function.

`NativeOperationalRuntime` is not special-cased anywhere in this path, and its breakdown is
consumed the same way. One property of the native runtime does *not* extend to replay
reverification, and is recorded rather than papered over: `NativeOperationalRuntime.submit()`
writes `native_artifact.*` keys into the runtime state *before* `super().submit()` scores and
asserts them in `episode.oracle.target_state`. Those keys are not the `state_changes` of any
`ActionEvent`, so the state `_validate_state_chain` replays from the recorded events cannot equal
the state the verifier scored. That is a property of the native runtime's own scoring path, not
of this adapter; the adapter's claim is shared adaptation through one code path, which is what
criterion 9 asserts.

## 3. What changed

Additive only. No existing field, function, name, or default was changed.

| File | Change |
|---|---|
| `src/investigation_world/trajectory/adapter.py` | `OPERATIONAL_RUNTIME_ADAPTER_ID`, `OPERATIONAL_RUNTIME_ADAPTER_VERSION`, `_REWARD_COMPONENTS`, `OperationalRuntimeAdapterContext`, `_operational_state_digest`, `_operational_event`, `_submit_event`, `_breakdown`, `trajectory_v2_from_operational_runtime`. Three private helpers, one private `Protocol` (`_ResourceCallEvent`), one public class, one public function, two constants. |
| `src/investigation_world/trajectory/__init__.py` | Four new names added to the import block and `__all__`. Alphabetical/positional placement preserved for the pre-existing names; the new names are appended so no existing line moves. |
| `tests/trajectory/test_operational_runtime_adapter.py` | New. |
| `docs/experience/operational-trajectory-adapter.md` | This document. |

`_operational_resource_call` was deliberately **not** added as a new helper. The existing
`_resource_id` / `_resource_call` pair resolves on the payload shape this adapter emits, so it is
called directly with the emitted `TrajectoryEvent` list. There is one resource-call convention,
not two — and one `_resource_call` definition, not two.

The one signature `_resource_call` needed was its parameter type. It was annotated
`event: TraceEvent` (foundry) and is now annotated with a small private `Protocol`,
`_ResourceCallEvent`, naming the four members the helper reads — `payload`, `step`, `event_type`,
`cost`. `TraceEvent` and `TrajectoryEvent` both structurally satisfy it, so the legacy call site
is unaffected and the operational call site type-checks. That is the only change to a
pre-existing annotation in this file, and it removes no caller.

No file outside the Work Contract's positive ownership is modified. In particular
`operational/**` is untouched — the adapter depends on it read-only, through
`TYPE_CHECKING` imports and one `reverify.operational` binding lookup — and
`trajectory/reverify/**` is untouched.

## 4. The round trip, end to end

This is the property the whole lane exists for, and it is asserted as a test rather than argued:

1. A real catalog episode (`build_enterprise_operations_world` + `apply_domain_realism`) is
   executed through `OperationalRuntime`, its required actions walked in the oracle's own
   order, and submitted.
2. The adapter converts it. The resulting trajectory's events are
   `["act"] * len(runtime.events) + ["submit"]`.
3. Every emitted `act` event is decoded through the reverification engine's own
   `_decode_operational_act` and compared to the expected public projection.
4. The single `submit` event is decoded through `_decode_submission` and equals the
   `EpisodeSubmission` the caller passed.
5. `OperationalReplayEvidence` is built from the same recorded state the adapter digested and
   attached with `attach_operational_replay_evidence`.
6. `reverify_trajectory` runs against the authorized binding and returns `REVERIFIED`, with a
   record whose reward and seven component scores equal the trajectory's
   `original_evaluation`.

Step 6 is the closure. It means the trajectory the adapter emits is not merely well-formed — it
is *the trajectory the offline verifier will accept and re-score to the same numbers*.

Two things the round trip had to get right, both of which are properties of the reverification
engine rather than of the adapter, and both of which are exercised by the test rather than
assumed:

- **The event digest covers the submit event.** `engine._validate_evidence_against_trajectory`
  compares `evidence.trajectory_events_digest` against `canonical_hash(trajectory.events)` —
  the *whole* emitted list, including the single `submit` event the adapter appends. Evidence
  built from the act events alone cannot match, so the digest is taken from the adapted
  trajectory.
- **The trajectory must name its evidence.** `_matching_private_reference` requires
  `trajectory.evidence_references` to contain a `TrajectoryReference` whose id and digest are the
  evidence's own. That reference is *derived* from the evidence's digest
  (`OperationalReplayEvidence.reference()`), so it cannot be computed before the evidence exists,
  and the adapter cannot construct it at all. The caller attaches it after adaptation, from
  `attach_operational_replay_evidence`.

Because the reference is appended after adaptation, it lands in `identity_payload`'s
`evidence_references` entry, so the trajectory id is computed *with* it. The flow is
self-consistent in that order: adapt → build evidence against the adapted trajectory → attach the
reference → attach the private payload. Both engine assertions that protect identity still hold —
`attach_operational_replay_evidence` refuses to run when attaching private evidence would change
the trajectory id, and its `for_trajectory` bind sets only `input_trajectory_id`, which the
evidence digest deliberately excludes.

## 5. Import direction

`investigation_world.trajectory` must be importable without importing
`investigation_world.operational`. The dependency is one-way:

```
trajectory  ──reads──▶  operational   (TYPE_CHECKING + one binding lookup)
```

The adapter therefore imports `ActionEvent` and `OperationalRuntime` under `if TYPE_CHECKING`
only. The single runtime import that *must* exist is
`from investigation_world.trajectory.reverify.operational import
current_operational_verifier_binding`, which is inside `trajectory/` already and is what makes
the default verifier identity resolvable. That import does pull `operational` in at runtime —
but it is a `trajectory` → `operational` edge, which is the correct direction, and
`reverify/operational.py` already had that edge before this lane.

The cycle that must not exist is `operational → trajectory`. It does not:
`grep -rn "investigation_world.trajectory" src/investigation_world/operational/` returns
nothing. This is asserted as a test that runs the import in a subprocess, because a cycle would
make the adapter itself unimportable from inside `operational`, which is exactly the caller it
serves.

## 6. Downstream consumers that become reachable

These gaps are **out of scope here** and are not implemented, specified, or pre-implemented.
Recording them because this adapter is what unblocks them, and because the boundary between
"unblocks" and "implements" is where this lane stops:

| Gap | Consumer | What the adapter enables |
|---|---|---|
| **G-04** | Observatory / evaluation aggregation | A runtime that ran can now be handed over as an identity-bound `TrajectoryV2` with a reverifiable event sequence, instead of a caller reconstructing the event list by hand. |
| **G-09** | transfer / comparison surfaces | `machine_experience_from_trajectory(traj)` succeeds on an operational trajectory with defaults, so an experience record exists for an operational episode without a bespoke construction path. |
| **G-10** | canonical evidence chain | The trajectory's provenance now carries `adapter_id`, `adapter_version`, the episode id, and the episode digest, so an evidence chain can name *which adapter* produced the record and from what. |

The ONTO-002 boundary this preserves is that **a trajectory is a record, not a re-execution.**
Nothing in this adapter re-runs, re-scores, or forks a runtime; the one place an evaluation
appears, it came from the caller's hand.

## 7. Acceptance evidence

All of the following is exercised by
`tests/trajectory/test_operational_runtime_adapter.py`. The ten cases the Work Contract
required:

| # | Criterion | Test |
|---|---|---|
| 1 | Round trip: events decode through the engine's decoders and reverify on a real catalog episode | `test_emitted_events_decode_and_reverify_on_a_real_catalog_episode` |
| 2 | Determinism of `trajectory_id` | `test_trajectory_id_is_deterministic_across_adaptations` |
| 3 | Identity sensitivity | `test_model_and_contract_identity_changes_change_trajectory_identity`, `test_a_partial_action_trace_changes_trajectory_identity` |
| 4 | Un-submitted runtime raises; adapter never calls `submit()` | `test_unsubmitted_runtime_is_rejected_without_calling_submit`, `test_missing_breakdown_is_rejected_without_re_scoring` |
| 5 | Verifier identity: `VERIFIER_ENTRYPOINT` / `VERIFIER_SEMANTICS_ID`, supplied context honored, `original_evaluation.verifier == trajectory.verifier` | `test_default_verifier_is_the_authorized_operational_binding`, `test_supplied_verifier_identity_is_honored_and_affects_identity`, `test_current_binding_pins_the_committed_verifier_source` |
| 6 | `machine_experience_from_trajectory(traj)` succeeds with defaults | `test_machine_experience_succeeds_with_defaults` |
| 7 | No private leakage in `public_payload()` / `buyer_safe_payload()` | `test_public_and_buyer_safe_payloads_carry_no_verifier_only_truth`, `test_private_payload_keeps_verifier_only_truth_out_of_the_public_event` |
| 8 | `investigation_world.trajectory` not imported by `investigation_world.operational.runtime` | `test_operational_package_does_not_import_trajectory` |
| 9 | Same suite for `NativeOperationalRuntime` | `test_native_runtime_adapts_through_the_same_path` |
| 10 | `tests/trajectory/test_rollout_adapter.py` passes unmodified | Not re-run in this module — it is a pre-existing file and is unmodified; the legacy entry point and context are untouched, so its nine assertions hold by construction. |

Beyond the required ten, the module also asserts:

| Criterion | Test |
|---|---|
| Provenance records the adapter id, version, source kind, episode id, and a digest | `test_provenance_records_the_adapter_and_the_source_runtime` |
| Supplied state digests win over computed ones | `test_supplied_state_digests_win_over_computed_ones` |
| All five catalog domains adapt through the same path, with unknown facts staying unknown | `test_every_catalog_domain_adapts_without_inventing_facts` |

One correction made after the first CI run is recorded here rather than buried in history. The
first revision of `test_every_catalog_domain_adapts_without_inventing_facts` iterated
`build_operational_suite(seed=7)` directly, but the catalog builders leave
`oracle.required_action_order` **empty** — it is `apply_domain_realism` that populates it. Every
episode therefore performed zero actions, and the loop exercised an empty trace rather than five
solved episodes. The suite is now deepened per episode with the realism family for that episode's
own domain. The same latent gap made the loop reference an undefined `breakdown`, which the
quality ratchet caught as a new `ruff:F821`.

### 7.1 Environment limitation

The development host used for this lane cannot import `investigation_world`. The immediate cause
is `pydantic_core`, whose native extension is built against glibc and cannot load under bionic
(`libdl.so.2`, `libpthread.so.0`, and a glibc `libgcc_s` are absent on this host, and no
bionic-built `pydantic_core` wheel is installable). This is the same constraint recorded for
G-01, and it is unchanged here.

The consequence is that the committed test module cannot be executed as a `pytest` suite on
this host, and **CI is the authority for it.** No committed assertion was weakened to make a
test pass locally. No shim was added to the repository to make the module importable. What
*was* verified on the host, without importing `pydantic_core`:

1. **Compilation.** `python -m py_compile` passes on `adapter.py`, `trajectory/__init__.py`,
   and the committed test module.
2. **Line length.** No line in the three Python paths exceeds the ruff `line-length = 100`
   configured in `pyproject.toml`. Markdown is not linted by that rule, so long table rows in
   this document are outside it.
3. **Import resolution.** The test module's imports were resolved by AST: every imported name
   is used, and no import is orphaned. `ruff`'s `F401` cannot fire on it.
4. **Import direction.** The cycle-free invariant in §5 is checked by source inspection
   (`grep -rn "investigation_world.trajectory" src/investigation_world/operational/` → no
   results) *and* asserted as a subprocess test, which does not require importing
   `investigation_world` into the test process.
5. **Payload shape, against the real decoder source.** `_decode_operational_act` and
   `_decode_submission` were read from `reverify/engine.py` and their acceptance conditions
   traced by hand against the exact payload dictionaries the adapter emits. The `act` payload
   satisfies `len(raw_args) <= 1` with `raw_args[0]` a `str`; the `submit` payload satisfies
   `isinstance(raw_args, list) and len(raw_args) == 1 and isinstance(raw_args[0], dict)`.
6. **Stop-condition resolution.** The verifier blob pin was recomputed on the host: the git
   blob sha1 of `src/investigation_world/operational/verifier.py` is
   `37c344287cb19b8e22bd705235bcfab67989065e`, which equals `SOURCE_VERIFIER_BLOB` in
   `portable_contract/compiler.py:61`. `current_operational_verifier_binding()` therefore
   constructs, and the default verifier identity in §2.5 is the authorized one.

What was **not** verified on the host and remains CI's responsibility: pydantic model
construction and validation (including `TrajectoryV2.validate_trajectory`'s
`original_evaluation.verifier == trajectory.verifier` rule and the `trajectory_id` derivation),
the `public_payload()` / `buyer_safe_payload()` projections under real pydantic, and the actual
`reverify_trajectory` outcome.

### 7.2 Quality gate

`tools/quality_baseline.py` enforces a repository-wide ruff 0.16.5 + mypy 2.3.1 ratchet against
`quality/python-quality-baseline.json`, which carries **977 accepted fingerprints**. The gate is
additive: a change may *remove* diagnostics but must not *introduce* any beyond the baseline.
The `trajectory` lane currently accounts for 2 ruff and 10 mypy fingerprints.

This lane's code was written to that constraint, and CI was used to verify it against the real
gate rather than against a guess. Across the run history this lane surfaced three fingerprints;
all three were eliminated structurally, and the lane now introduces **zero**:

- `mypy:arg-type` — `Argument 2 to "_resource_call" has incompatible type "TrajectoryEvent";
  expected "TraceEvent"`. `_resource_call` was annotated `event: TraceEvent` (foundry) and is
  called with `TrajectoryEvent` (trajectory); both types expose the four members the helper
  reads. The parameter is now typed as a small private `Protocol` (`_ResourceCallEvent`) naming
  exactly those members, so mypy has no incompatible pair to compare and the error cannot fire.
  The legacy call site is unchanged and still type-checks against the Protocol. No cast, no
  `# type: ignore`, no baseline edit. (An earlier revision tried removing a wrapper helper; that
  did not fix it, because the annotation itself — not the wrapper — was the error.)
- `ruff:F821` — `Undefined name \`breakdown\`` in the test module, surfaced by the
  `required_action_order` correction recorded in §7.
- `ruff:I001` — in the test module, not the implementation. `from investigation_world.trajectory
  .reverify import ...` preceded `from investigation_world.trajectory.models import ...`;
  ruff's isort orders `models` before `reverify`. (A first attempt misread this as the
  implementation module's `typing` line and split `from typing import TYPE_CHECKING, Any` into
  one import per line. That was harmless but fixed nothing — the fingerprint is recomputed from
  the file that actually carries it.)

The Protocol is the one place this lane changed an existing annotation, and it is additive in
behaviour: `_resource_call` accepted `TraceEvent` before and still does, because `TraceEvent`
structurally satisfies the Protocol.

Neither fix touched the baseline file, which is outside this lane's positive ownership. One
fingerprint was *removed* as a side effect (`mypy:assignment`, 22 → 21 in the summary); removals
are permitted by the additive gate, so no action was needed.

One typing concession remains, and it is recorded rather than silenced:

- `_context()` in the test module takes `**overrides` and forwards it to a pydantic model with
  `extra="forbid"` semantics on `CanonicalModel`, which mypy cannot check. Test modules are
  ruff-checked but not mypy-checked (`MYPY_COMMAND` targets `src` only), so this is a
  ruff-visible surface only, and ruff's `E**`/`F**` rules do not flag it.

The authoritative check is `python tools/quality_baseline.py check`, which runs on CI in
`.github/workflows/python-quality.yml`. It was **not** run on this host: neither `ruff` nor
`mypy` is installed, and installing them is prohibited by the Termux resource policy this device
operates under.

## 8. Stop conditions

The Work Contract named five potential stop conditions. Four were resolved as design decisions;
one was resolved by verification. None of them stopped the work.

| # | Condition | Resolution |
|---|---|---|
| 1 | State-digest scope: operational state is seeded from private oracle state | **Resolved by decision.** Default `StateDigestScope.SEMANTIC`, not the legacy `PUBLIC_SEMANTIC`, with caller-supplied digests winning. Follows the reviewer recommendation recorded in the contract's Unresolved §1: do not silently downgrade a private-seeded state to a public-scope digest. |
| 2 | Verifier identity may not be statically resolvable | **Resolved by verification.** The git blob sha1 of `operational/verifier.py` matches `SOURCE_VERIFIER_BLOB` exactly, so `current_operational_verifier_binding()` constructs and the default identity is the authorized one. No stop. |
| 3 | `NativeOperationalRuntime` mutates oracle state before scoring | **Resolved by decision, with one scope limit recorded.** No per-runtime branching: the mutation happens before `super().submit()` scores, so the caller's breakdown describes the recorded events and one code path adapts both runtimes. The limit is that the same mutation makes the replay state chain unequal for the native runtime — its `native_artifact.*` keys are not any `ActionEvent`'s `state_changes` — so replay reverification is asserted for `OperationalRuntime` only, and criterion 9 asserts shared adaptation for the native runtime. |
| 4 | Resource-call convention may differ for operational actions | **Resolved by decision.** `_resource_id` / `_resource_call` resolve on the emitted payload shape, so they are reused. No second convention, no new helper. |
| 5 | The reverify engine may require a payload shape the adapter cannot emit | **Resolved by inspection.** The engine's decoders accept exactly the shape §2.3 emits, confirmed against the decoder source and asserted by round-trip test. |

## 9. Deferred, explicitly

Per ONTO-002 §9 and the Work Contract's authority boundaries, the following are **not**
introduced here and remain deferred:

- **G-04** Observatory aggregation of operational trajectories. This adapter produces the
  object; wiring it into an aggregation surface is a different lane with different protected
  surfaces.
- **G-09** Transfer comparison over operational trajectories. `machine_experience_from_trajectory`
  succeeds with defaults here, which is the *precondition* for that lane, not its
  implementation.
- **G-10** Canonical evidence-chain binding of the provenance records emitted here. The
  `adapter_id` / `adapter_version` / episode digest fields exist so that binding can name them;
  the binding itself is not built.
- Any change to `operational/**`, `experience/**`, `qualification/**`, `observatory/**`,
  `gold10/**`, `release/**`, or `pyproject.toml`. None is touched.
