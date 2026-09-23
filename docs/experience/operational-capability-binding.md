# Operational Capability Binding

Work ID: `G-02` (issue #394). The G-01 content-identified `CapabilityContract` was a
declaration with no operational referent: a world or episode could say "external-investigation"
in prose but nothing recorded *which revision of that contract* the world was built to
exercise. This lane adds the machine-checkable binding. It is the second row of the ONTO-002
G-02 group (`docs/experience/canonical-ontology-gap-audit.md` §7, row G-02), and it consumes
G-01 read-only.

Status: **binding metadata only.** The field records identity; it never participates in
execution, verification, scoring, qualification, or release decisions. G-03 (#395) is a
separate lane with disjoint ownership and is not implemented or pre-implemented here.

Owning Work ID: `G-02` / #394 — branch `feat/operational-capability-binding`. Positive
ownership, per the Work Contract: `src/investigation_world/operational/models.py`;
`src/investigation_world/operational/catalog.py`;
`src/investigation_world/operational_world/models.py`;
`src/investigation_world/operational_world/capability_pack.py`;
`tests/unit/test_operational_capability_binding.py`;
`docs/experience/operational-capability-binding.md`. That is **six** paths. No file outside
them is modified.

## 1. The problem

A capability contract pins what a capability means at one revision. A world is compiled
against that meaning. Without a binding between the two, drift is undetectable: a contract's
content changes while its `capability_id` stays the same, and every world that was compiled
against the old content silently claims to exercise the new capability.

The capability pack manifest carried the worst version of this — a hand-written string:

```python
"capability": "operational_procurement_investigation",
```

That string is not content-derived, is not unique to any revision, and is not verifiable. It
is replaced here by the G-01 identity pair.

## 2. The mechanism

`CapabilityBinding` is a reference, not an identity. It mints nothing: it carries the G-01
capability identity (`capability_id` + `content_digest`) computed by
`investigation_world.foundry.models.capability_contract_digest`. There is exactly one
capability identity scheme in the repository, and this lane is not it.

### 2.1 The field scheme

Three additive optional fields, all defaulting to `None` / `()`:

```python
class OperationalEpisode(BaseModel):
    capability: CapabilityBinding | None = None
class OperationalWorldSpec(BaseModel):
    capability: CapabilityBinding | None = None
class InvestigationPackSpec(BaseModel):
    capability: CapabilityBinding | None = None
```

Optional, so every existing construction — every `OperationalWorldSpec(...)`, every catalog
builder, every pack build — stays valid without change. `OperationalWorldSpec.capability` is
carried through to `CompiledOperationalWorld.public_payload()` for free, because
`public_payload` already serializes the whole spec (minus evaluator-only `scenario_types`).

`CapabilityBinding` itself:

```python
class CapabilityBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability_id: str
    content_digest: str
    binding_gaps: tuple[str, ...] = ()
```

### 2.2 Fail closed on identity, advisory on coverage

Two separate rules, deliberately not the same rule.

**Identity is strict.** `capability_binding_from_contract` recomputes the digest from the
contract's own content and compares it to the contract's declared digest; a mismatch raises
`ValueError` and is never silently accepted. This mirrors
`CapabilityContract.validate_content_digest` from G-01 exactly, so a binding cannot be
constructed against a stale or tampered contract. Independently,
`CapabilityBinding.validate_capability_binding` rejects an empty `capability_id` and any
`content_digest` that is not a well-formed `CCONTRACT-<20 hex uppercase>` value, so a
hand-written or truncated digest cannot be smuggled in through a model constructor.

**Coverage is advisory.** When an episode (or its `HiddenOracle`) is supplied to
`capability_binding_from_contract`, the contract↔oracle coverage findings are computed and
recorded on the binding as `binding_gaps`. A gap is never raised and never fails
construction.

### 2.3 Why coverage is advisory, and why it is an existence check

`CapabilityContract.success_conditions` and `hard_invariants` are free-form prose
`list[str]`. `HiddenOracle.target_state` is `list[StateAssertion]` and `invariants` is
`list[OperationalInvariant]`. The two sides are not mechanically equatable, and a
plausible-looking string match between prose and structured assertions would be a check that
passes vacuously and fails silently. That is a falsifier, not a guarantee, so this lane
**does not implement it.**

The only decidable coverage question is an existence check: is each episode-side reference
key named by the contract's prose? `episode_contract_terms` enumerates the episode-side keys —
`invariant_id`s and `object_id.field_name` pairs — and a gap is recorded for each one not
named by the contract's `success_conditions` or `hard_invariants`.

Prose↔structured-assertion equivalence is explicitly out of scope and is not claimed. A
contract whose prose names an invariant id is covered by that id; whether the prose *means*
the same thing the assertion checks is a semantic question this lane does not answer and does
not pretend to.

**Why advisory rather than strict.** The strict rule would fail on `main` the moment it was
enforced, because no existing contract's prose names existing oracle keys (the catalog binding
in §4 demonstrates this). Failing closed there would force a choice between two bad options:
weaken an oracle or a catalog until the prose matches, or make the coverage check vacuous so
the check always passes. The first corrupts the benchmark; the second is a false guarantee.
Recording the gaps instead makes them a **deliverable finding** for the lanes that can act on
them (G-07 qualification, G-09 transfer, G-12 calibration), without this lane altering any
contract, oracle, or catalog to make the finding go away.

### 2.4 The binding does not feed any digest

`binding_gaps` is excluded from the binding's own identity payload: the identity fields are
`capability_id` and `content_digest`, and `capability_id` + `content_digest` together are
exactly the G-01 identity, nothing more. So findings can accumulate without churning episode
identity — a recorded gap never changes what the episode is.

### 2.5 No private oracle state in the binding

`CapabilityBinding` is public declaration content, mirroring `CapabilityContract`. It holds no
private scenario identifier, hidden label, oracle row, or decrypted bundle, and it must never
be populated from `HiddenOracle` state. The coverage check reads **identifiers**
(`invariant_id`, `object_id.field_name`), never oracle values: `episode_contract_terms` never
looks at `expected_value`, and the gap message never contains one.

## 3. What changed

Additive only. No existing field was renamed, removed, retyped, or given a different default.

| File | Change |
|---|---|
| `operational/models.py` | `CapabilityBinding`; `episode_contract_terms`; `capability_binding_from_contract`; `OperationalEpisode.capability`; `public_payload()` emits `"capability"` (null when unset) |
| `operational/catalog.py` | `build_investigation_osint_world` binds its episode to the real `external-investigation` contract via `capability_binding_from_contract` |
| `operational_world/models.py` | `OperationalWorldSpec.capability` |
| `operational_world/capability_pack.py` | `InvestigationPackSpec.capability`; `public_manifest()` replaces the hardcoded `"capability"` string with `capability_id` + `content_digest`, omitting both keys when no binding is set; the builder threads the spec binding through to each compiled `OperationalWorldSpec` |

The hardcoded string is **removed**, not renamed. When a binding is present the manifest now
carries the two identity keys; when it is absent it carries neither, which is the honest
representation of an unbound pack rather than a fabricated capability name.

No world construction, episode execution, verifier, oracle, qualification, training, or
release path changed behavior. The portable-contract round trip
(`src/investigation_world/world_portability/compiler.py`,
`OperationalEpisode.model_validate(episode.model_dump(...))`) is unaffected: an additive
optional field round-trips by construction, and `None` validates against
`CapabilityBinding | None`.

### 3.1 Adjacent observation, not changed by this lane

`src/investigation_world/operational_world/compiler.py:99` constructs a `CompanyWorldTask`
with `task_type="operational_procurement_investigation"`. That is a second hardcoded
capability string in the same family as the one this lane replaced, but it lives outside this
Work Contract's positive ownership (`compiler.py` is not one of the six paths). It is recorded
here as an observation for whoever owns that surface next. It is not a binding and carries no
digest, so it does not affect any identity claim made here.

## 4. The real binding

`build_investigation_osint_world` is the catalog episode with an investigation-shaped
objective, and it already carried `metadata={"legacy_capability_family":
"external_investigation"}` — the exact legacy reference this lane replaces with a
content-derived one. It is now bound:

```python
capability=capability_binding_from_contract(
    external_investigation_capability_contract(), episode=oracle
),
```

with the real G-01 identity:

| `capability_id` | `content_digest` |
|---|---|
| `external-investigation` | `CCONTRACT-91A20E2ED9D0445EE997` |

The oracle is passed so the advisory coverage check runs for real. The result is recorded,
not raised. At the audited head the episode's keys are not named by the contract's prose, so
`binding_gaps` is non-empty:

```
osi-no-false-merge is not named by the external-investigation contract
investigation.subject_resolved is not named by the external-investigation contract
investigation.resolved_to is not named by the external-investigation contract
investigation.provenance_complete is not named by the external-investigation contract
```

That is the correct outcome and it is left standing: weakening the oracle to make the gaps
disappear would corrupt the benchmark, and weakening the check would make it a false
guarantee. The gaps are the deliverable finding.

## 5. Acceptance evidence

All of the following is exercised by
`tests/unit/test_operational_capability_binding.py`.

| Criterion | Test |
|---|---|
| Valid binding round-trips and is carried in `public_payload()` | `test_valid_binding_round_trips_and_is_carried_in_public_payload` |
| Capability-ID mismatch fails closed | `test_capability_id_mismatch_fails_closed` |
| Content-digest mismatch fails closed | `test_content_digest_mismatch_fails_closed` |
| Stale content is not accepted | `test_stale_content_is_not_accepted`, `test_stale_content_in_a_real_binding_is_rejected` |
| Deterministic identity | `test_deterministic_identity`, `test_identical_contracts_give_identical_bindings` |
| Serialization round-trip | `test_serialization_round_trip` |
| Contract/evaluator consistency | `test_binding_from_a_real_contract_matches_its_declared_digest`, `test_real_catalog_episode_is_bound_to_the_real_digest`, `test_pack_manifest_carries_the_g01_identity_pair`, `test_real_contract_binding_survives_a_public_payload_round_trip` |
| No hidden-oracle leakage in the binding | `test_binding_carries_no_private_oracle_state`, `test_coverage_check_reads_identifiers_not_values`, `test_binding_gaps_do_not_change_identity` |
| Compatibility with unbound episodes | `test_unbound_episodes_still_construct`, `test_pack_manifest_omits_capability_keys_when_unbound` |

## 6. Downstream consumers

These gaps are **out of scope here** and are not implemented or pre-implemented. Recording them
because this lane is what unblocks them:

| Gap | Consumer | What the binding enables |
|---|---|---|
| **G-07** | `MaturityRecord` / `QualificationReport` | A qualification record can bind to a capability *contract revision* via the same identity pair, rather than binding only to a capability name. |
| **G-09** | transfer comparison | Two identified conditions can be compared under one contract *and* one verifier, with the contract revision pinned so the comparison cannot silently span a contract edit. |
| **G-12** | `CalibrationProfile` | A profile can state which capability contract it calibrates, using the same identity pair. |

The distinction G-09 enables is the ONTO-002 G-11 boundary: "transfer evidence exists" must
not be readable as "transfer improvement was measured." That boundary is not addressed here;
it belongs to the G-09 object.

## 7. What this lane does not claim

- No scientific, qualification, or release conclusion is drawn from the tests passing. They
  exercise the binding's semantics, not agent performance.
- The digest is sha256 truncated to 80 bits. Best-effort, not a collision guarantee — same
  trade as G-01, and the same caveat applies.
- Prose↔structured-assertion equivalence is not implemented and not claimed (§2.3).
- The binding is metadata. Nothing in this lane makes a world easier, harder, or different to
  solve.
