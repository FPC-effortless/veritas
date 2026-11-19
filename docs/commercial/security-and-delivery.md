# Veritas Security and Delivery Model

## Deployment options

Veritas is designed to support several evaluation delivery modes:

### Customer-controlled offline evaluation

The customer's model and the Veritas evaluator run on the same user-controlled device. Model preprocessing, embeddings, inference, state updates and optional speech remain local. The evaluator uses an in-process adapter or a literal loopback endpoint; remote/cloud inference is not supported. Private benchmark truth remains in a separate evaluator-only process/workspace on that device.

### Customer-controlled evaluation runner

Veritas runs inside customer-controlled compute while private evaluator assets are mounted separately from the evaluated model process. The model still executes locally on the same device; local process/loopback boundaries do not authorize outbound inference.

### Isolated container evaluation

The evaluated model and Veritas runtime may be placed in separate containers or processes on the same device with explicit filesystem boundaries. Model inference receives only local task inputs; deny outbound network access and keep private oracle data evaluator-only.

### Air-gapped/private deployment

For sensitive environments, the same runtime can be packaged for an isolated network. Model weights and benchmark assets are pre-staged and evaluation artifacts are exported after completion.

## Data boundary

A production commercial deployment should keep these classes separate:

| Data class | Agent access | Evaluator access |
| --- | --- | --- |
| Public task/objective | Yes | Yes |
| Public system observations | Yes | Yes |
| Tool schemas and budgets | Yes | Yes |
| Agent trajectories | Agent produces | Yes |
| Hidden CompanyWorld truth | No | Yes |
| Private task oracle | No | Yes |
| Private benchmark seeds | No | Yes |
| Customer secrets | Only as explicitly required | Only as explicitly required |

## Recommended controls

- unique benchmark-run identifiers;
- immutable benchmark/version hashes;
- per-run temporary credentials;
- strict separation of public and private files;
- read-only benchmark evidence;
- append-only trajectory and action journals;
- isolated work directories per episode;
- explicit outbound-network policy;
- resource/time/token/tool budgets;
- logs for every tool call and mutable state transition;
- post-run credential revocation;
- defined retention and deletion policy for customer inputs and trajectories.

## Model endpoint handling

For endpoint-based evaluation, production deployments must enforce:

- literal loopback IP endpoints only (`127.0.0.1` or `::1`);
- exact `/v1/chat/completions` path;
- no DNS names, LAN/public addresses or URL-embedded credentials;
- environment proxies disabled and redirects rejected;
- optional local bearer authentication and customer-managed token limits;
- TLS verification when local HTTPS is used;
- deterministic request logging with secrets redacted.

The endpoint restriction protects the evaluator's transport boundary; it does not prove the model process itself makes no network requests. Airplane-mode execution and a physical network trace are separate acceptance evidence.

## Benchmark confidentiality

The commercial private benchmark should not be published in full. Development examples, benchmark methodology and public-reference policies can remain inspectable while private seeds, holdout worlds and evaluator oracles are distributed only to trusted evaluator infrastructure.

## Supply-chain and repository controls

The Veritas repository already runs package, container, Python-version, frontend and dependency/security checks in CI. Commercial releases should additionally be tagged, signed where possible, associated with a benchmark manifest, and built from a protected release branch or immutable commit.

## Procurement evidence to prepare per customer

- architecture/data-flow diagram;
- dependency and container inventory;
- vulnerability scan results;
- data retention statement;
- subprocessor list for any approved data-storage or tooling services; model inference providers are not permitted for company-delivered customer models;
- incident-response contact and process;
- business continuity/recovery statement;
- model artifact provenance and local runtime/operator inventory;
- benchmark confidentiality statement;
- customer-specific deployment and network diagram.
