# Capability Contract Content Identity

Work ID: `G-01` (issue #391). The identity foundation for the canonical evidence chain,
ordered first by `docs/experience/canonical-ontology-gap-audit.md` §10 (gap G-01, row 1).

Status: **identity only.** This document specifies a content-derived digest for an existing
declaration type. It does not implement, specify, or pre-implement any downstream binding.
G-02, G-07, G-09, and G-12 remain their own lanes.

Owning Work ID: `G-01` / #391 — branch `feat/capability-contract-content-identity`. Positive
ownership, per the Work Contract: `src/investigation_world/foundry/models.py`;
`src/investigation_world/foundry/capability_families.py`;
`src/investigation_world/foundry/companyworld.py`; `src/investigation_world/foundry/cli.py`;
`tests/unit/test_foundry_capability_contract_identity.py`;
`docs/experience/capability-contract-identity.md`. That is **six** paths, and `models.py` is
the first of them — it is the implementation surface for this lane, holding the digest field,
the validator, and the two helpers.

## 1. The problem

`CapabilityContract` (`src/investigation_world/foundry/models.py`) is a complete
pre-evaluation declaration: objective, subcapabilities, success and failure conditions, hard
invariants, and transfer targets. But it carried **no content-derived identity**. Every
downstream reference to a capability was a bare string:

| Reference | Location |
|---|---|
| `FailureFamily.affected_capability` | `experience/models.py` |
| `CapabilityGap.capability` | `experience/models.py` |
| `TrainingRecipe.capability_contract_id` | `foundry/training_product.py` |
| `FoundryTaskMetadata.capability_tags` | `foundry/models.py` |
| `DemonstrationSet.capability_contract_id` | `foundry/expert_trajectories.py` |

A bare `capability_id` string cannot detect that a contract's *content* changed while its
*name* stayed the same. Two declarations that disagree about what "external-investigation"
means are indistinguishable from the outside. That is exactly the binding the canonical
evidence chain depends on, which is why ONTO-002 ordered G-01 before every other gap.

## 2. The mechanism

The design mirrors two existing repository precedents exactly:

- `CapabilityGraph.validate_graph` — `src/investigation_world/observatory/capability_graph.py`
  computes `CGRAPH-<hex>` from nodes and edges, and rejects a supplied `graph_id` that
  disagrees with contents.
- `MaturityPolicy.validate_policy` — `src/investigation_world/qualification/maturity.py`
  computes `MPOL-<hex>` from policy version and requirements, with the same fail-closed rule.

### 2.1 The field

`CapabilityContract` gained one additive field:

```python
content_digest: str = ""
```

Default unset, so every existing construction — including every call site that builds a
contract from a literal — stays valid without change. It is a **second, content-binding
identifier**. `capability_id` remains the human-readable identifier and remains the primary
key for every existing reference. This is not a replacement identity scheme and not a new
capability registry.

### 2.2 The payload

```python
capability_contract_digest_payload(contract) -> dict[str, Any]
```

Deterministic, covering **all eight content-bearing fields**:

`capability_id`, `version`, `objective`, `subcapabilities`, `success_conditions`,
`failure_conditions`, `hard_invariants`, `transfer_targets`.

`content_digest` is excluded from its own computation; an identifier that fed its own
digest would be circular. Lists are copied so later mutation of the input cannot
retroactively change what was pinned. The payload is built from the model's own field
values, never from object identity, insertion order, wall time, process id, or the `repr`
of an unsorted structure.

### 2.3 The digest

```python
capability_contract_digest(contract) -> str
```

Canonicalized through the existing `stable_hash` helper in `foundry/models.py` —
`json.dumps(..., sort_keys=True, separators=(",", ":"), default=str)` over the payload, then
sha256. Format:

```
CCONTRACT-<20 hex uppercase>
```

The prefix matches the `CGRAPH-…` scheme named in the Work Contract. The truncation length is
**20 hex characters = 80 bits.**

### 2.4 The validator

```python
@model_validator(mode="after")
def validate_content_digest(self) -> "CapabilityContract":
    expected = capability_contract_digest(self)
    if self.content_digest and self.content_digest != expected:
        raise ValueError("content_digest does not match capability contract contents")
    self.content_digest = expected
    return self
```

Two behaviors, both load-bearing:

1. **Derive, do not require.** Unset input is filled with the computed value. The three
   existing producers — `external_investigation_capability_contract()`,
   `selective_agency_capability_contract()`, `companyworld_capability_contract()` — construct
   contracts without passing a digest, and the validator derives it.
2. **Fail closed.** A supplied digest that does not match the content raises `ValueError` at
   construction time. The digest is **never** silently recomputed and accepted. Silently
   accepting a mismatch would make the binding advisory instead of binding, and a stale pin
   would then look like a fresh one.

`CapabilityContract` is not a frozen model (unlike `CapabilityGraph` and `MaturityPolicy`),
so the validator assigns the field directly rather than through the `object.__setattr__`
escape hatch those two need.

## 3. What changed

Additive only. No existing field was renamed, removed, retyped, or given a different default.

| File | Change |
|---|---|
| `foundry/models.py` | `content_digest` field; `validate_content_digest`; `capability_contract_digest_payload`; `capability_contract_digest`; `CAPABILITY_CONTRACT_DIGEST_LENGTH`; `CAPABILITY_CONTRACT_DIGEST_PREFIX` |
| `foundry/cli.py` | `generate-external-demos` prints `capability_contract_id` and `capability_contract_content_digest`; `export-training-artifacts` incorporates the capability-contract content digest into the inputs used to derive `run_id`, and prints the digest per run |
| `foundry/capability_families.py` | No change. Producers already construct without a digest; the validator derives it. |
| `foundry/companyworld.py` | No change, for the same reason. |
| `tests/unit/test_foundry_capability_contract_identity.py` | New |

No file outside the Work Contract's positive ownership is modified. In particular
`foundry/__init__.py` is **not** touched: the helpers and constants stay in `models.py`, and
the two test modules and the CLI all resolve them from there. `cli.py` never imports the
helpers at all — it reads `contract.content_digest` directly — so no package-level re-export
is needed to make the change work.

The CLI change is requirement 5: a human or downstream tool can now pin a contract by
content, not only by name. `export-training-artifacts` incorporates the content digest into
the inputs used to derive `run_id`, alongside `dataset_id`, `bundle_id`, and `base_model`.
The digest is **not recoverable** from the resulting identifier: `run_id` retains only a
12-character hash fragment, which is too short to carry the 20-character digest. What it
preserves is the weaker, sufficient property that a change in capability-contract content
changes the derived run identity, so an artifact built against one contract revision cannot
be mistaken for an artifact built against another.

No world construction, episode execution, verifier, oracle, qualification, training, or
release path changed behavior. Serialization round-trips keep working — a new optional field
is backwards compatible by construction. `TrainingRecipe.capability_contract_id` still
compares `capability_id` to `capability_id`, unchanged.

## 4. No private material in the payload

`CapabilityContract` is a public declaration. The digest payload contains no private scenario
identifier, hidden label, oracle row, or decrypted bundle. The implementation reaches into no
protected surface to compute the digest: it reads the contract's own public fields.

## 5. Truncation, and what it does not mean

The digest is sha256 truncated to 80 bits. That is a deliberate trade — a 20-character
identifier is readable and fits the `CGRAPH` precedent — and it is **best-effort, not a
collision guarantee.** This document does not claim infallibility. A collision would require
an attacker to find a second contract whose content hashes to the same leading 80 bits, which
is infeasible in practice for the threat model (detecting accidental or negligent content
drift in a declaration that is already public) but is not a proof.

For a binding that needs the full digest, `capability_contract_digest_payload` is exported so
a caller can hash it without truncation.

## 6. Downstream consumers that become bindable

These gaps are **out of scope here** and are not implemented or pre-implemented. Recording
them because this lane is what unblocks them:

| Gap | Consumer | What the digest enables |
|---|---|---|
| **G-02** | `OperationalWorldSpec`, `OperationalEpisode`, capability pack | A world or episode can declare which contract *revision* it was built for, and a validator can reject a pack whose contract content has drifted since the world was compiled. Touches protected `operational/**`; must be additive metadata plus validators, never runtime behavior. |
| **G-07** | `MaturityRecord` / `QualificationReport` | A qualification record can bind a capability *contract revision* to an agent identity under a stated panel, rather than binding only to a capability name. Must not duplicate `qualification/**`. |
| **G-09** | transfer comparison | Two identified conditions can be compared under one contract *and* one verifier, with the contract revision pinned so the comparison cannot silently span a contract edit. Reuses `observatory/aggregation.py` statistics; is not a runtime class and not a new evaluation engine. |
| **G-12** | `CalibrationProfile` | A profile can state which capability contract it calibrates. Smaller than G-02 — a reference field or documentation, not a mechanism. |

The distinction G-09 enables is the ONTO-002 G-11 boundary: "transfer evidence exists" must
not be readable as "transfer improvement was measured." That boundary is not addressed here;
it belongs to the G-09 object.

## 7. Acceptance evidence

All of the following is exercised by `tests/unit/test_foundry_capability_contract_identity.py`.

| Criterion | Test |
|---|---|
| Format `CCONTRACT-<20 hex uppercase>` | `test_digest_is_derived_and_matches_expected_format` |
| Stability across repeated construction | `test_digest_is_stable_across_repeated_construction` |
| Determinism across separate processes | `test_digest_is_deterministic_across_separate_processes`, `test_synthetic_contract_is_deterministic_across_separate_processes` |
| Every content-bearing field changes the digest | `test_every_content_bearing_field_changes_the_digest` (8 params) |
| Field order does not change the digest | `test_field_order_does_not_change_the_digest` |
| Identical content yields identical digest | `test_identical_content_yields_identical_digest` |
| Digest excluded from its own payload | `test_digest_field_is_excluded_from_its_own_payload` |
| Mismatch raises `ValueError` | `test_mismatched_explicit_digest_raises_value_error`, `test_digest_field_is_excluded_from_its_own_payload`, `test_restored_contract_resists_content_drift` |
| Correct explicit digest accepted | `test_correct_explicit_digest_is_accepted` |
| Default unset stays valid | `test_digest_defaults_unset_so_existing_constructions_stay_valid` |
| All three real producers derive a digest | `test_all_three_real_producers_derive_a_stable_digest` (3 params) |
| Round-trip serialization | `test_round_trip_serialization_preserves_the_digest` |
| No private material in payload | `test_digest_payload_carries_no_private_material` |
| Second identifier, replaces nothing | `test_digest_is_a_second_identifier_and_replaces_nothing` |

The three real producers, at the audited head, are:

| Producer | `capability_id` | digest |
|---|---|---|
| `external_investigation_capability_contract()` | `external-investigation` | `CCONTRACT-91A20E2ED9D0445EE997` |
| `selective_agency_capability_contract()` | `selective-agency` | `CCONTRACT-CD5F4659B54AF50F3BC7` |
| `companyworld_capability_contract()` | `companyworld-enterprise-control` | `CCONTRACT-E70433EA95DC0FD29A1E` |

### 7.1 Run identity

Requirement 5 is also covered directly, in the same authorized test module:

| Criterion | Test |
|---|---|
| Identical contract content yields the same derived run identity | `test_identical_contract_content_produces_the_same_derived_run_identity` |
| Changed contract content changes the derived run identity | `test_changed_contract_content_changes_the_derived_run_identity` |
| Pre-existing inputs (`dataset_id`, `bundle_id`, `base_model`) still affect run identity | `test_existing_run_id_inputs_retain_their_influence` (3 params) |
| The digest is not recoverable from `run_id` | `test_the_digest_is_not_recoverable_from_the_derived_run_identity` |

The tests call the production `_artifact_run_id` helper directly, at the narrowest seam that
exercises the changed behaviour. That is deliberate: the whole point of the change is the
deterministic relationship between contract content and run identity, which the CLI's
argument handling and artifact writing neither affect nor obscure. The extraction of
`_artifact_run_id` and `_artifact_run_id_inputs` is behaviour-preserving — the command passes
the same four values to the same `stable_hash` call as the previous inline construction, so
the derived `run_id` for any given input set is byte-identical to it.

### 7.2 Environment limitation

The development host used for this lane cannot import `investigation_world`. The immediate cause
is not the `duckdb` dependency named in earlier drafts of this section: it is `pydantic_core`,
whose native extension is built against glibc and cannot load under bionic (`libdl.so.2`,
`libpthread.so.0`, and a glibc `libgcc_s` are absent on this host, and no bionic-built
`pydantic_core` wheel is installable). `duckdb` is additionally absent, so the `calibration`
import chain would fail independently of `pydantic_core` — but `pydantic_core` fails first and
blocks every import path through `investigation_world`, so it is the binding constraint.

The constraint is stronger than a blocked package root. Because `CapabilityContract` is a
pydantic model, and `foundry/models.py` imports `pydantic` at module scope, **the committed
test module cannot even be collected on this host**: its module-level imports resolve through
pydantic, and pydantic cannot initialize. `pytest --collect-only` fails with
`ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'`.

The consequence is that the committed test module cannot be executed as a `pytest` suite on
this host, and **CI is the authority for it.** No committed assertion was weakened to make a
test pass locally. No shim was added to the repository to make the module importable — the
`pydantic` shim named in item 4 below lives outside the repository and touches no repository
file. What *was* verified on the host, without importing `pydantic_core`:

1. **The three documented producer digests are exact.** Each producer function in
   `foundry/capability_families.py` and `foundry/companyworld.py` was read by AST, its
   content-bearing arguments converted to plain Python, and the documented `CCONTRACT-…` value
   recomputed independently from the `stable_hash` specification
   (sorted-keys JSON, `separators=(",", ":")`, `default=str`, sha256, 20 hex, uppercased). All
   three match the §7 table byte for byte.
2. **The run-identity invariants hold against the real production source.** `_artifact_run_id`,
   `_artifact_run_id_inputs`, and `stable_hash` were extracted verbatim from `cli.py` and
   `models.py` by AST and executed in an isolated namespace, with `TrainerKind` supplied by an
   equivalent `StrEnum`. The checks passed: digest format, digest sensitivity to content,
   identical content → identical run identity, changed content → changed run identity, all
   three pre-existing inputs (`dataset_id`, `bundle_id`, `base_model`) still affecting run
   identity, and the digest not being recoverable from `run_id`.
3. **Cross-process determinism.** The digest computation is a pure function of sorted-keys
   JSON, so repeated computation in a fresh interpreter is byte-identical by construction; this
   was confirmed for the producers in step 1.
4. **The real production validator source, executed.** `foundry/models.py` was compiled and run
   on this host under a minimal `pydantic` shim providing only `BaseModel`, `Field`, and
   `model_validator`. This is not a reimplementation of the validator: the module's own source
   was executed verbatim, so the `model_validator(mode="after")` body that CI will run is the
   code that ran here. Twelve checks passed against it: derive-on-unset, format,
   independent recomputation from the payload, fail-closed `ValueError` on a mismatching
   supplied digest, acceptance of the correct digest, `ValueError` on content drift against a
   pinned digest, exclusion of `content_digest` from its own payload, coverage of all eight
   content-bearing fields, all eight fields changing the digest, construction order
   invariance, input-list mutation not retroactively changing a computed digest, and stability
   across repeated construction.

What was **not** verified locally, and remains CI's responsibility: pydantic's own
serialization and coercion machinery — `model_dump`/`model_validate_json` round-tripping
(`test_round_trip_serialization_preserves_the_digest`) and pydantic's exact `Field` default
handling for an unset digest (`test_digest_defaults_unset_so_existing_constructions_stay_valid`)
were exercised through the shim, not through pydantic, and the shim is deliberately narrower
than pydantic. The CLI command end-to-end, and the broader foundry suite named in the Work
Contract's verification ladder step 2, did not run.

This is a coverage limitation of the host, not of the test design: the committed test module
imports through the package surface and runs unmodified wherever the package imports, which is
the condition CI provides.

## 8. Falsifiers

This lane fails if any of the following holds. The status of each is stated precisely: some
were cleared by source inspection, some by executable checks on this host, and some **could not
be checked locally at all** and remain open until CI runs. The last is not a form of PASS.

### 8.1 Cleared by source inspection and executable checks

- The digest is derived from a non-deterministic source: object identity, insertion order,
  wall time, process id, or the `repr` of an unsorted structure. It is not — the payload is a
  sorted-keys JSON serialization of the model's field values, verified by recomputing all
  three producer digests independently and by a fresh-interpreter check.
- The payload omits a content-bearing field, so two genuinely different contracts share one
  digest. It does not — all eight fields are covered, each with a dedicated sensitivity case
  in the test module, all eight were confirmed present in the executed payload, and each of
  the eight was confirmed individually to change the digest on this host.
- Field order changes the digest. It does not — the payload is canonicalized by
  `json.dumps(..., sort_keys=True, ...)`.
- The digest is not derivable from the documented algorithm. It is — all three producer
  digests were recomputed from the `stable_hash` specification and match the §7 table exactly.
- Changing contract content does not change the derived run identity. It does — verified
  against the real production `_artifact_run_id` source.
- Identical contract content does not produce the identical run identity. It does — verified
  the same way, as was the continued influence of `dataset_id`, `bundle_id`, and `base_model`.
- The digest is encoded in or recoverable from `run_id`. It is not — `run_id` keeps 12 hex
  characters, which cannot carry the 20-character digest; verified explicitly.
- `foundry/__init__.py`, `CapabilityGraph`, `MachineExperience`, `OperationalEpisode`,
  `OperationalWorld`, Gold-10, SRE/HUD, release surfaces, or any other negative-ownership
  surface is modified. None is — confirmed by `git status --porcelain`, which now reports no
  path outside the six authorized ones.
- A digest collision is asserted to be impossible rather than best-effort. It is not; §5
  states the 80-bit truncation explicitly.
- Sealed/private benchmark content appears in the digest payload, the new test, or this
  document. It does not; the payload is built only from the model's public fields.
- The digest silently recomputes and is accepted when a supplied digest does not match the
  content. It does not — the real production `validate_content_digest` source was executed
  (§7.2, item 4) and raised `ValueError` on both a mismatching supplied digest and on content
  drift against a pinned digest; the correct digest was accepted, and an unset digest was
  filled by derivation.
- The digest changes without a content change. It does not — the same executed-source harness
  confirmed stability across repeated construction and invariance to construction order, and
  that later mutation of an input list does not retroactively change a digest already
  computed from it.

### 8.2 Not cleared locally — pydantic's own machinery

The validator logic itself now executes on this host under a minimal `pydantic` shim (§7.2,
item 4), but the shim is deliberately narrower than pydantic, so three things remain open:

- pydantic's serialization and coercion, as exercised by
  `test_round_trip_serialization_preserves_the_digest` (`model_dump` / `model_validate_json`).
  The shim has no equivalent of these methods, so round-trip preservation of `content_digest`
  is **unexecuted locally**. Source inspection finds no defect — the field is a plain `str`
  with a default, so it serializes and deserializes as itself — but inspection is not
  execution.
- pydantic's exact `Field` handling for an unset digest, as exercised by
  `test_digest_defaults_unset_so_existing_constructions_stay_valid`. The validator fills an
  empty string by derivation, which the executed source confirmed, but pydantic's own default
  resolution is **unexecuted locally**.
- All three real producers construct a valid contract *through pydantic*. Their digests were
  verified by independent recomputation, but pydantic's own model construction was not.

### 8.3 Not cleared locally — ruff

`ruff check` and `ruff format --check` are an acceptance criterion of the Work Contract. No
ruff wheel installs on this host, and the glibc binary cannot execute even after TLS-segment
patching, so `ruff` itself is **unexecuted locally** and must run in CI.

What *was* checked, without running ruff: all three Python files in this lane were measured
against the `line-length = 100` configured in `pyproject.toml` `[tool.ruff]`, and all three
are now within it. This matters because CI's quality gate is a ratchet, not zero-tolerance:
`.github/workflows/python-quality.yml` runs `tools/quality_baseline.py check`, which fails
only on diagnostics whose `(tool, path, code, message)` fingerprint is not already in
`quality/python-quality-baseline.json`. That baseline already contains **926 `ruff:E501`
fingerprints** — which is why `test_foundry.py` (10 lines over 100) and
`test_foundry_companyworld.py` (3) pass CI today. But fingerprints are keyed by path, and
`tests/unit/test_foundry_capability_contract_identity.py` is a new file, so none of its
diagnostics can be grandfathered. An earlier revision of this lane had three lines over 100
(109, 101, 106 characters); their E501 fingerprints were reconstructed and confirmed absent
from the baseline, so they would have failed the ratchet. All three were wrapped, and the
re-wrapped string in `test_digest_is_deterministic_across_separate_processes` was confirmed
AST-identical to the original, so the fix changed formatting only.

What was **not** checked, because ruff cannot run here: `E` (other pycodestyle rules), `F`
(Pyflakes — unused imports/names), and `I` (isort import ordering), the three rules the
`[tool.ruff.lint]` `select` list enables. Two approximations were run instead, neither of
which is ruff executing: import order in the new test module was checked as
stdlib / third-party / first-party, which is the order rule `I` produces; and unused imports
were checked by binding every imported name and confirming each is referenced in the module
body. All three Python files are clean on both, and all three are within the 100-column
limit. `from __future__ import annotations` is exempt from `F401` by ruff's own rule and is
used by 336 files in this repository, so its presence is not a defect.

### 8.4 Not cleared locally — CI suite

The Work Contract's verification ladder step 2 names the broader foundry suite
(`test_foundry.py`, `test_foundry_cli.py`, `test_foundry_companyworld.py`,
`test_foundry_cycle.py`, `test_foundry_operationalization.py`,
`test_foundry_task_distribution.py`, `test_foundry_materializer.py`,
`test_foundry_restorations.py`) plus the new test. **None of these ran locally**, including
`test_foundry_cli.py`, which is the suite most likely to notice an unintended behaviour change
in `export-training-artifacts`. That is the outstanding risk this document cannot close.

## 9. Ownership compliance

The Work Contract for `G-01` / #391 authorizes **six** positive-ownership paths:

```
src/investigation_world/foundry/models.py
src/investigation_world/foundry/capability_families.py
src/investigation_world/foundry/companyworld.py
src/investigation_world/foundry/cli.py
tests/unit/test_foundry_capability_contract_identity.py
docs/experience/capability-contract-identity.md
```

`git status --porcelain` on this branch reports four modified or added paths:

```
src/investigation_world/foundry/cli.py
src/investigation_world/foundry/models.py
tests/unit/test_foundry_capability_contract_identity.py
docs/experience/capability-contract-identity.md
```

**Every reported path is an authorized one.** No file outside the frozen positive ownership is
modified, and no ownership authorization or update is required. Two details worth recording
explicitly, because an earlier revision of this lane got both wrong:

- `foundry/__init__.py` is **not** modified. An earlier revision added a package-level
  re-export of the two helpers and two constants; that was out of scope, and it was also
  unnecessary — `cli.py` reads `contract.content_digest` directly and never imports the
  helpers, and the test module resolves them from `foundry.models`, where they already live.
  The re-export was reverted. The helpers remain in their implementation module.
- `tests/unit/test_foundry_capability_contract_run_identity.py` **does not exist** on this
  branch. An earlier revision created it as a separate module for the run-identity invariants,
  but that path is not in the Work Contract. The invariants were moved into the authorized
  `test_foundry_capability_contract_identity.py` (§7.1) and the separate file was deleted, so
  no coverage was lost and no out-of-scope file remains.

`capability_families.py` and `companyworld.py` are positive-ownership paths and were **not**
modified — their producers already construct without a digest, so the validator derives it, and
requirement 3 holds with no change to them.

The Work Contract's negative ownership protects the specific surfaces named there (protected
`operational/**`, `operational_world/**`, Gold-10, SRE/HUD, `release/**`, package identifiers,
`CapabilityGraph`, training experiment code, `docs/experience/machine-experience.md`,
`annotation/**`, `docs/experience/canonical-ontology-gap-audit.md`,
`.github/agent-roadmap.yml`, and the rest), and none of those is touched.

## 10. Deferred, explicitly

Per ONTO-002 §9 and the Work Contract's authority boundaries: causal `CapabilityGap`
semantics, adaptive world mutation, `DistributionProfile`, and `DifficultyVector` semantics
are **not** introduced here and remain deferred. Downstream gaps G-02, G-07, G-09, and G-12
are separate lanes with their own protected-surface negotiation; G-02 in particular touches
protected `operational/**` and needs additive metadata plus validators, not runtime behavior.
