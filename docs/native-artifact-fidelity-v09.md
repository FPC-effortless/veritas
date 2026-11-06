# Veritas 0.9 Native Artifact Fidelity

Veritas 0.9 adds a native-artifact execution layer behind the existing Unified Operational Worlds contract. The purpose is to make operational work alter and verify real domain artifacts without changing the benchmark's public/private boundary or its seven-dimensional reward interface.

## Release boundary

The 0.9 operational contract is:

```text
TaskContract + public records + public actions
                |
                v
       OperationalRuntime
                |
       successful transition
                |
                v
 ParameterizedNativeArtifactWorkspace
                |
                +-- real XLSX workbook
                +-- SQLite enterprise replica
                +-- Kubernetes-style manifest/state bundle
                +-- rendered OSINT evidence corpus
                +-- GeoJSON/Shapely/pyproj workspace
                |
                v
      native artifact checks
                |
                v
existing hidden target-state verifier
                |
                v
outcome / state / constraints / side effects /
process / efficiency / evidence
```

Native checks do not create an eighth reward dimension. They become additional hidden target-state assertions before the ordinary Veritas verifier runs. An agent can therefore satisfy the synthetic state transition and still lose outcome/state credit if the actual artifact is wrong.

## Lazy materialization

The production distribution remains **4,480 operational episodes**. Veritas does not embed 4,480 binary workbooks, databases and GIS workspaces into the public benchmark bundle.

Every generated episode instead carries a deterministic public `NativeArtifactDescriptor` containing:

- opaque artifact ID;
- domain;
- engine name;
- file/bundle format;
- media type;
- default artifact filename;
- public source-record lineage;
- lazy/deterministic fidelity metadata.

The evaluator or rollout harness materializes bytes only when a case is executed. This keeps distribution generation, hashing and transport inexpensive while preserving deterministic reconstruction.

## Parameterized execution

Native artifacts derive their values from the episode's actual generated oracle/state contract rather than constants from the reference examples.

This matters because the production generator varies, among other fields:

- spreadsheet sheet/cell locations, formula periods and target enterprise value;
- enterprise deal/order/account/discount state;
- DevOps service identity, deployment and recovered error rate;
- OSINT names, companies, addresses and supported identity;
- GIS source layer, target layer and source/target CRS pair.

`ParameterizedNativeArtifactWorkspace` adapts the materialized bytes and native verifier to those case-specific targets.

## Financial / Spreadsheet engine

Engine: `openpyxl-workbook-v1`

Artifact: real `.xlsx` workbook.

Current workbook surfaces include:

- Revenue inputs;
- model/valuation sheet containing the defective formula;
- WACC sheet;
- control/check sheet;
- hidden Veritas artifact metadata sheet.

Operational actions can edit the actual formula cell, recalculate the supported generated `SUM` dependency, clear model-audit state, and record destructive value-overwrite behavior.

Native checks currently verify:

- expected generated formula is present in the actual workbook;
- generated target enterprise value was recomputed;
- audit state is clean;
- formula lineage has not been destroyed.

This is real XLSX mutation and validation. It is **not yet a full Excel-compatible calculation engine** supporting arbitrary formulas, macros, Power Query, external data connections or workbook rendering.

## Enterprise Operations engine

Engine: `sqlite-enterprise-replica-v1`

Artifact: real SQLite database.

The replica contains first-class tables for:

- CRM opportunities;
- CPQ quotes;
- ERP sales orders;
- IAM role assignments;
- customer credit profiles;
- append-only audit events.

Successful operational actions mutate the corresponding system tables. The native verifier checks approval routing, order control state, bypass state and audit history against the same hidden operational objective.

This is a transactional relational replica, not a claim to reproduce Salesforce, SAP, Dynamics or another vendor's full application behavior.

## DevOps / Incident Response engine

Engine: `declarative-kubernetes-sandbox-v1`

Artifact: directory bundle containing Kubernetes-style deployment/service manifests plus executable state files for cluster health, alerts and traces.

Successful recovery actions mutate cluster state, including:

- ready/desired replicas;
- generation;
- service health;
- generated target error rate;
- independent health-verification state;
- harmful unnecessary dependency intervention.

Native checks validate the recovered service and target error-rate/tolerance directly from the generated episode.

This is an executable deterministic infrastructure artifact sandbox. It is **not yet a live Kubernetes API server, container scheduler, Terraform/cloud control plane or real packet/network simulator**.

## Investigation / OSINT engine

Engine: `rendered-evidence-corpus-v1`

Artifact: heterogeneous evidence directory.

Current materialized surfaces include:

- registry filing JSON;
- historical archive HTML;
- directory CSV;
- mutable investigation casefile JSON.

The casefile accumulates hypothesis, resolved identity, linked evidence, closure state and false-merge state. The native verifier derives the correct identity from the generated case rather than assuming a reference name.

This produces actual heterogeneous documents/files and mutable case state. It is not yet a browser-scale rendered web, OCR/image corpus or internet-scale search environment.

## GIS engine

Engine: `shapely-pyproj-vector-v1`

Artifact: GeoJSON workspace.

The workspace contains:

- immutable source vector layer;
- working derived layer;
- overlay target layer;
- workspace state;
- generated source and target CRS metadata.

Actions perform actual coordinate transformation through `pyproj`, geometry repair through Shapely and geometric intersection for overlay creation. Native checks validate generated target CRS, geometry validity, source preservation and overlay completion.

This is real vector geospatial execution. Raster processing, very large datasets, PostGIS, GDAL command surfaces and production cartographic rendering remain later integrations.

## Shared verifier integration

`NativeOperationalRuntime` mirrors only **successful, unblocked** operational actions into the artifact. A blocked action therefore cannot mutate either hidden operational truth or the native artifact.

At submission:

1. the native artifact is independently checked;
2. every native check is mapped into hidden `native_artifact.<check>` state;
3. those checks are appended as target-state assertions;
4. the ordinary Veritas verifier computes the existing seven scores;
5. failed native checks are also surfaced to the evaluator trace as `native_artifact:<check>` process violations.

This closes a key reward-hacking route: an agent cannot receive full state/outcome credit by invoking the correct API verbs while leaving the underlying workbook/database/infrastructure/evidence/GIS artifact incorrect.

## Distribution and integrity contract

The operational distribution advances from `operational-production-v2` to `operational-production-v3` while retaining exactly:

| Split | Per domain | Total |
|---|---:|---:|
| Train | 512 | 2,560 |
| IID test | 128 | 640 |
| OOD | 128 | 640 |
| Adversarial | 128 | 640 |
| **Total** | **896** | **4,480** |

The full distribution validator still checks public/private separation, opaque IDs, deterministic fingerprints, split integrity, stateful procedures, temporal provenance and trajectory invariants. v3 additionally validates native engine assignment, opaque artifact IDs and source-record lineage for every case.

Artifacts themselves are not included in public distribution hashes because they are deterministic lazy projections of the versioned episode contract.

## Native release gate

In addition to the ordinary unit suite and full 4,480-case descriptor/integrity gate, CI runs:

```bash
veritas validate-native-fidelity --seed 42 --cases-per-split 8
```

The evaluator selects one deterministic case from every domain × split cell:

```text
5 domains × 4 splits = 20 native executions
```

For every sampled case it:

- executes the evaluator-qualified required procedure;
- rejects blocked or missing evaluator transitions;
- materializes/mutates the actual artifact;
- requires every native artifact check to pass;
- submits through the ordinary verifier;
- requires shared state and outcome scores of 1.0.

This is separate from the 4,480-case validator: the latter provides exhaustive distribution/descriptor coverage, while the native gate provides executable byte-level sampling across all split regimes.

## CLI

Materialize an agent-facing native artifact without writing its private oracle:

```bash
veritas materialize-native financial_spreadsheet \
  --seed 42 \
  --split train \
  --case-index 0 \
  --output-dir ./native_case
```

Run the evaluator-only native release gate:

```bash
veritas validate-native-fidelity --seed 42 --cases-per-split 8
```

## What 0.9 does not claim

0.9 should be described as **native artifact fidelity**, not universal industrial simulation.

Not yet included:

- arbitrary Excel formula/macro/Power Query execution;
- live Kubernetes clusters, container networking, Terraform or cloud-provider APIs;
- vendor-complete CRM/ERP/CPQ application replicas;
- browser-scale web rendering, OCR-heavy OSINT or live internet state;
- raster GIS, GDAL/PostGIS-scale workloads or cartographic rendering;
- automatic materialization of every artifact in the 4,480-case distribution during bundle generation.

Those are higher-cost sandbox integrations that can now attach behind the same stable episode/action/oracle/verifier contract instead of requiring another benchmark redesign.
