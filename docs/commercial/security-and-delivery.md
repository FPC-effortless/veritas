# Veritas Security and Delivery Model

## Deployment options

Veritas is designed to support several evaluation delivery modes:

### Vendor-hosted evaluation

The customer supplies an endpoint or temporary credentials. Veritas runs the benchmark and returns results. Private benchmark truth remains inside the evaluator boundary.

### Customer-controlled evaluation runner

Veritas runs inside customer-controlled compute while private evaluator assets are mounted separately from the evaluated agent. This mode is appropriate when customer prompts, model endpoints or internal tool schemas must remain inside the customer's environment.

### Isolated container evaluation

The evaluated agent and Veritas runtime are placed in separate containers or processes with explicit network and filesystem boundaries. Public task data flows to the agent; private oracle data remains evaluator-only.

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

For endpoint-based evaluation, production deployments should support:

- OpenAI-compatible chat/completions endpoints;
- configurable authentication headers;
- customer-managed rate and token limits;
- zero-retention endpoints where the customer requires them;
- endpoint hostname allowlists;
- TLS verification;
- deterministic request logging with secrets redacted.

## Benchmark confidentiality

The commercial private benchmark should not be published in full. Development examples, benchmark methodology and public-reference policies can remain inspectable while private seeds, holdout worlds and evaluator oracles are distributed only to trusted evaluator infrastructure.

## Supply-chain and repository controls

The Veritas repository already runs package, container, Python-version, frontend and dependency/security checks in CI. Commercial releases should additionally be tagged, signed where possible, associated with a benchmark manifest, and built from a protected release branch or immutable commit.

## Procurement evidence to prepare per customer

- architecture/data-flow diagram;
- dependency and container inventory;
- vulnerability scan results;
- data retention statement;
- subprocessor list for any hosted third-party inference providers;
- incident-response contact and process;
- business continuity/recovery statement;
- model/provider data-use settings where applicable;
- benchmark confidentiality statement;
- customer-specific deployment and network diagram.
