# Veritas 0.11 Portability

## Purpose

0.11 makes a qualified Veritas environment distributable without requiring a buyer to adopt the full
Veritas development repository or a Veritas-hosted SaaS backend.

The internal contract is vendor-neutral. HUD and Prime Intellect are adapters over that contract,
not the abstraction Veritas core is built around.

## Architecture

```text
Canonical qualified release
        |
        v
PortableEnvironmentManifest
        |
        +-- deterministic release/task/run identities
        +-- taskset visibility boundary
        +-- reset contract
        +-- capability contract
        +-- verifier contract
        +-- artifact/provenance/licensing metadata
        +-- optional vendor-neutral metering hook
        |
        +--------> HUD v6 package
        |
        +--------> Prime Verifiers v1 taskset
```

The first proof SKU is **Veritas SRE Evaluation Pack v1** because its SRE v4 release is already
qualified, frozen, sealed, real-model-tested, and pilot-rehearsed. CompanyWorld is expected to be a
higher-value later flagship, but it should consume the same portable contract rather than forcing a
new adapter architecture.

## Identity invariants

Portable environment manifests and tasksets receive content-derived identities. A portable SRE task
uses a one-way source digest derived from immutable release identity, canonical scenario identity,
and public digest. The canonical scenario ID is never copied into the portable task record. Including
it only inside the one-way identity derivation is required because distinct sealed cases may
legitimately share the same public digest. The opaque source digest, environment identity/version,
split, and seed then determine the portable task ID. Run IDs also include an invocation identity.

A portability implementation must preserve:

```text
(environment_version, task_id, seed) -> same verifier-relevant initial state
```

The portable SRE runtime records deterministic initial/terminal state digests so reset/replay can be
checked independently of a vendor runner. Regression coverage includes distinct private cases with
identical public digests to ensure portable identities remain unique without exposing canonical
private scenario IDs.

## Metering contract

The runtime exposes an optional vendor-neutral metering callback. It emits immutable
`episode_started` and `episode_graded` events containing only content-derived event identity,
run/environment/task identity, seed, state digest, reward when available, and buyer-safe metadata.

The portability layer deliberately does not add customer identity, billing state, provider
credentials, prompt text, private ground truth, or wall-clock timestamps. A marketplace or hosted
service may add those concerns outside the portable runtime. Tests reject prompt/hidden-label leakage
through the reference metering sink.

## Private-data boundary

`buyer_safe` and `public_sample` manifests must not include:

- private-test task rows;
- private task identities;
- hidden causal labels/oracles;
- private artifacts;
- decryption material;
- developer-local paths or undeclared local dependencies.

The portable manifest records only the sealed private task count and immutable release identities.

Operator-private exports are allowed to materialize hidden task records in the generated external
package. Those generated records are evaluation secrets and must never be committed to the public
repository or uploaded as buyer-safe artifacts.

For SRE, operator-private task records contain only a portable task ID, deterministic seed, agent
prompt, expected causal class, and immutable public digest. Canonical source scenario IDs are not
copied into the generated external package.

## HUD adapter

The generated HUD package follows the current protocol-first v6 model:

- a HUD `Environment` hosts a task template;
- the template yields the prompt;
- the agent/harness produces an answer;
- deterministic grading yields an `EvaluationResult` reward;
- the container serves `env:env` on the HUD control channel.

Generated files include:

```text
Dockerfile.hud
pyproject.toml
env.py
tasks.py
portable_manifest.json
private_tasks.json
qualification_evidence.json
README.md
```

`private_tasks.json` is operator-private and is deliberately separate from the buyer-safe portable
manifest. `qualification_evidence.json` is buyer-safe aggregate qualification evidence and contains
no private rows or hidden labels.

For the pinned HUD 0.6 SDK used by 0.11 validation, the executable local image path is standard Docker:

```bash
docker build -f Dockerfile.hud -t veritas-sre-v1:local .
```

The release workflow then boots that image and exercises the live HUD task-start/task-grade control
protocol. 0.11 does not claim a `hud build` command because the validated HUD 0.6.15 CLI does not
provide one.

## Prime Intellect adapter

New Prime work targets `verifiers.v1` rather than making the frozen legacy environment abstraction
the internal contract.

The generated package exports an `SRETaskset` containing immutable `TaskData` and a deterministic
`@vf.reward` scorer. Harness and runtime selection remain outside the taskset, matching the v1
Taskset x Harness x Runtime decomposition.

A compatibility-only `load_environment()` bridge is also generated and continuously exercised in CI
for existing community/environment-hub flows. New integrations should use the v1 taskset path.

## Commands

Buyer-safe manifest:

```bash
python tools/export_sre_portable_manifest.py \
  --qualification /secure/path/qualification.json \
  --output /tmp/veritas-sre/portable_manifest.json
```

Operator-private HUD + Prime packages:

```bash
python tools/export_sre_portable_package.py \
  --qualification /secure/path/qualification.json \
  --output /secure/output/veritas-sre \
  --adapter both
```

For a production export, supply the expected candidate/evidence/report/panel/private-release IDs and
source bundle SHA-256 so the export cannot silently drift to a different release.

## Validation strategy

`Portability Validation` runs independently from the repository's ordinary CI and Security checks.
It validates:

- deterministic content-derived environment/taskset/task/run/metering identities;
- unique opaque task identities even when sealed cases share a public digest;
- buyer-safe/private boundaries and leakage rejection;
- deterministic reset and canonical reward parity;
- generated HUD and Prime package determinism;
- clean external SDK installation and import validation;
- a generated HUD Docker image plus live task-start/task-grade protocol smoke test;
- Prime Verifiers v1 taskset loading and the compatibility-only legacy bridge;
- the exact encrypted/frozen SRE v4 release with all five canonical release identities and 30 private tasks;
- exact sealed HUD image build and Prime wheel build outside the Veritas package layout;
- ciphertext-only seal retention and buyer-safe proof upload;
- deletion of decrypted private release material from runner temp.

The sealed production proof records only buyer-safe facts: exact release identities and source bundle
SHA, private task count, deterministic package IDs, reset/reward parity booleans, and explicit
no-private-scenario-ID assertions. It does not publish task rows, private labels, predictions,
decryption material, or plaintext benchmark artifacts.

A release PR is merged only after the review-ready merge ref has fresh successful CI, Security, and
Portability Validation checks. Draft-state checks are evidence for debugging but are not used to
bypass branch protection after GitHub regenerates the merge ref on the ready-for-review transition.
