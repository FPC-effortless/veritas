# Veritas Operational Production Scale

Veritas 0.7 promotes the five unified operational domains from reference-only examples to a deterministic production-scale synthetic task distribution.

## Default distribution

The default `OperationalDistributionConfig` compiles **4,480 executable episodes**:

| Split | Per domain | Five-domain total |
|---|---:|---:|
| Train | 512 | 2,560 |
| IID test | 128 | 640 |
| OOD | 128 | 640 |
| Adversarial | 128 | 640 |
| **Total** | **896** | **4,480** |

The five domains are:

1. Financial / Spreadsheet
2. Enterprise Operations
3. DevOps / Incident Response
4. Investigation / OSINT
5. GIS Operations

Every generated case remains an executable `OperationalEpisode` with public records/actions and a separately packaged private oracle. Scale does not turn the benchmark into a static prompt collection.

## Distribution construction

Generation is deterministic for a fixed distribution version and seed. A case receives an evaluator-only seed derived from the distribution seed, domain, split and case index. Domain parameterizers then vary operational state rather than merely changing prose.

Current parameterization includes:

- **Financial / Spreadsheet:** workbook/sheet/cell locations, formula windows, valuation outputs and units.
- **Enterprise Operations:** deal/order identities, customers, requested discounts and transaction values.
- **DevOps / Incident Response:** services, databases, deployments, error rates, latency and replica health.
- **Investigation / OSINT:** companies, abbreviated identities, true/decoy people, addresses, registry identifiers and historical dates.
- **GIS Operations:** source/overlay layers, CRS pairs, feature counts and geometry defects.

Each domain also carries multiple scenario-family labels in the evaluator bundle so future generators can deepen family-specific semantics without changing the public/runtime contract.

## Train, IID, OOD and adversarial isolation

Split membership is evaluator-only.

- **Train:** low-noise procedural cases intended for capability development.
- **IID test:** held-out seeds and surface forms from the same broad operating regime.
- **OOD:** unfamiliar roles/vocabulary plus higher distractor pressure.
- **Adversarial:** tighter resource bounds, misleading/conflicting context and high adversarial pressure.

The validator checks exact per-domain/per-split counts and verifies that train IDs never overlap held-out IDs.

## Anti-leakage boundary

The public bundle deliberately does **not** expose per-case:

- split;
- generator seed;
- scenario-family label;
- surface-profile label;
- difficulty vector;
- hidden target state;
- hidden action effects;
- forbidden-action labels;
- evaluator oracle.

Public task/world/record IDs are derived from opaque hashes rather than containing split or seed text. Public episode order is deterministically hash-mixed rather than emitted in split blocks.

The private evaluator bundle retains split assignment, seed, family/profile metadata, difficulty and the full oracle.

## Reproducibility

The distribution compiler produces separate hashes for:

- the public episode payload;
- the private evaluator/oracle payload.

For a fixed version/configuration, recompilation must reproduce the same hashes and task IDs. Regression tests enforce this on reduced fixtures, while CI performs a full default-scale compile.

## Production-scale CI gate

The required CI workflow contains a dedicated `Production-scale operational distribution` job that runs:

```bash
veritas validate-production-scale --seed 42
```

That gate compiles and validates the full **4,480-case** default distribution. The repository is not considered green unless this job, the Python test matrix, package build, environment smoke tests, frontend build and container-health check all succeed.

## Building artifacts

Generate the default public/private bundle with:

```bash
veritas build-distribution \
  --seed 42 \
  --output veritas_operational_distribution_public.json \
  --oracle-output veritas_operational_distribution_private.json
```

The counts can be raised without changing the environment contract:

```bash
veritas build-distribution \
  --train-per-domain 2048 \
  --iid-per-domain 512 \
  --ood-per-domain 512 \
  --adversarial-per-domain 512 \
  --output public.json \
  --oracle-output private.json
```

That configuration produces 17,920 episodes.

## What “production scale” means here

Veritas uses the term specifically for the **procedural synthetic benchmark/runtime distribution**:

- thousands of deterministic executable episodes;
- explicit train/IID/OOD/adversarial partitions;
- private-oracle separation;
- reproducible manifests and hashes;
- difficulty/adversarial pressure;
- CI validation at full default scale;
- one runtime/verifier contract across five economically relevant domains.

It does **not** imply that every domain already executes native industrial artifacts. The current operational records/state engine is the executable substrate. Higher-fidelity engines remain a separate fidelity track: native XLSX/formula DAG execution, container/Kubernetes/Terraform sandboxes, richer enterprise application/database replicas, larger evidence corpora, and native vector/raster GIS artifacts.

Those artifact engines should plug into the same task/oracle/runtime/verifier contract rather than creating new benchmark products.

## Scaling invariant

Increasing case count is not sufficient by itself. A Veritas production distribution must preserve:

1. deterministic generation;
2. public/private isolation;
3. held-out split integrity;
4. meaningful state variation;
5. executable actions and consequences;
6. independent verification;
7. adversarial pressure without oracle leakage;
8. trace/replay compatibility;
9. reproducible distribution fingerprints;
10. calibration hooks so realism can be measured rather than asserted.
