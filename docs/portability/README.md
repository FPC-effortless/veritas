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

Portable environment manifests and tasksets receive content-derived identities. Portable task IDs
are derived from environment identity/version, immutable public task digest, split, and seed. Run IDs
also include an invocation identity.

A portability implementation must preserve:

```text
(environment_version, task_id, seed) -> same verifier-relevant initial state
```

The portable SRE runtime records deterministic initial/terminal state digests so reset/replay can be
checked independently of a vendor runner.

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

Generated files currently include:

```text
Dockerfile.hud
pyproject.toml
env.py
tasks.py
portable_manifest.json
private_tasks.json
README.md
```

`private_tasks.json` is operator-private and is deliberately separate from the buyer-safe portable
manifest.

## Prime Intellect adapter

New Prime work targets `verifiers.v1` rather than the frozen legacy environment abstraction.

The generated package exports an `SRETaskset` containing immutable `TaskData` and a deterministic
`@vf.reward` scorer. Harness and runtime selection remain outside the taskset, matching the v1
Taskset x Harness x Runtime decomposition.

A legacy `load_environment` bridge is not yet part of the first implementation slice. If added, it
must remain a compatibility surface only and must not become the internal Veritas portability API.

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
It currently validates:

- deterministic identities;
- buyer-safe/private boundaries;
- SRE sealed-release projection;
- deterministic reset and grading behavior;
- deterministic generated package contents;
- generated Python syntax;
- generated HUD and Prime code against the currently installed external SDK APIs in a separate job.

The remaining 0.11 release work is to add a true clean-install/container smoke test outside the
repository checkout, golden canonical-vs-adapter reward parity, and final private-package leakage
attacks against the real sealed SRE release.
