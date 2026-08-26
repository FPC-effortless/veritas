# Veritas 0.8 — Deep Domain Realism

Veritas 0.8 deepens the five production operational domains without changing the public seven-dimensional verification contract or the 4,480-case default distribution scale.

## What changed

The v0.7 distribution already provided deterministic train/IID/OOD/adversarial generation, private-oracle separation, executable actions and production-scale CI validation. v0.8 makes the generated work materially more operational by adding stateful procedures, temporal/provenance-rich records, domain-native control surfaces and trajectory-aware verification.

The shared reward contract remains:

1. outcome
2. state
3. constraints
4. side effects
5. process
6. efficiency
7. evidence

No domain receives a private success definition that bypasses this contract.

## Stateful procedures

`HiddenActionEffect` now supports hidden state preconditions and required prior actions. A syntactically valid action can therefore be rejected by the simulated system when prerequisites are not satisfied. Blocked actions do not mutate hidden state and do not satisfy required process steps.

`HiddenOracle` now supports:

- ordered required procedures;
- repeated action counts;
- final-state and trajectory-wide invariants;
- threshold comparisons in state assertions.

This closes a major environment loophole: performing the correct verbs in the wrong order is no longer equivalent to correctly executing the workflow.

## Temporal and epistemic records

Every `OperationalRecord` can now carry:

- observation time;
- validity interval;
- source authority;
- confidence;
- freshness;
- provenance references.

These fields are public operational evidence, not hidden truth. Agents must reason over stale/current, authoritative/non-authoritative and independently sourced records while the evaluator keeps ground truth private.

## Financial / Spreadsheet

The production cases now include workbook manifests, formula-lineage graphs, calculation chains, source-ledger reconciliation, review notes and model-governance policies.

A representative successful procedure is:

`inspect lineage -> reconcile source -> repair formula -> recalculate -> validate controls`

Recalculation is blocked until the repaired formula and source reconciliation are both valid. Source balances and external links can be protected by trajectory-wide invariants.

Artifact contract: `xlsx_formula_dependency_graph_v2`.

## Enterprise Operations

Cases now span CRM, CPQ, ERP, IAM and finance-control state. Evidence includes role assignments, quote versions, customer credit profiles, order-line state, account context and immutable audit events.

A representative controlled procedure is:

`verify authority -> validate credit -> request approval -> hold order -> update stage -> reconcile systems`

The agent must maintain authority and cross-system consistency rather than merely reaching a desired CRM status.

Artifact contract: `crm_cpq_erp_control_graph_v2`.

## DevOps / Incident Response

Cases now include change-management data, deployment diffs, distributed dependency graphs, log signatures, SLI windows, SLO policy and Kubernetes deployment specifications.

A representative procedure is:

`correlate change -> inspect dependencies -> recover service -> verify health -> validate SLO`

The intervention is blocked until the diagnostic scope is established, and recovery is not considered complete until a post-recovery service-level check succeeds.

Artifact contract: `incident_telemetry_dependency_graph_v2`.

## Investigation / OSINT

Cases now include explicit hypothesis state, repeated evidence linking, source provenance, source-independence metadata, identifier crosswalks, negative evidence, archived reporting and chain-of-custody invariants.

A representative procedure is:

`record hypothesis -> resolve identity -> link multiple evidence roots -> corroborate -> close case`

A resolution cannot be promoted to corroborated truth from one supporting record, and evidence repetition is distinguished from independent support.

Artifact contract: `multi_source_provenance_casefile_v2`.

## GIS Operations

Cases now include catalog metadata, CRS definitions, datum/axis-order context, spatial extent, topology rule sets, schema profiles, lineage and output contracts.

A representative procedure is:

`inspect metadata -> reproject -> repair geometry -> validate topology -> execute overlay`

The verifier can enforce tolerance-based output rules such as maximum sliver rate while preserving immutable source lineage.

Artifact contract: `vector_crs_topology_lineage_v2`.

## Production distribution compatibility

The deep distribution wrapper retains the existing split counts:

- train: 2,560 total;
- IID: 640 total;
- OOD: 640 total;
- adversarial: 640 total;
- total: 4,480 executable episodes.

New realism-layer record IDs are deterministically made opaque before public packaging. Difficulty vectors are recomputed after adding domain-native actions, records and procedure depth. The production validator additionally requires system heterogeneity, temporal/provenance records, stateful preconditions, trajectory invariants and at least five ordered procedure steps per generated case.

## Scope boundary

`deep domain realism` does not mean that Veritas now embeds every native industrial execution engine.

The environment is materially deeper at the operational/state/procedure/evidence level. The next fidelity layer remains pluggable native engines such as:

- real XLSX files and formula-evaluation engines;
- containerized Kubernetes/Terraform sandboxes;
- richer enterprise databases/application replicas;
- larger rendered evidence corpora and document formats;
- native vector/raster GIS execution and file verification.

Those engines should attach behind the same `TaskContract -> Runtime -> HiddenOracle -> seven-dimensional verifier` boundary rather than fragmenting the product into incompatible benchmarks.
