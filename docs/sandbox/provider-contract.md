# Sandbox provider contract

The sandbox boundary is infrastructure only. It gives operational environments a stable way to provision an isolated execution session, mount explicitly declared byte assets, invoke allow-listed commands or tools, capture declared writable artifacts, enforce execution policy, reset/destroy the session, and record replay-relevant infrastructure metadata.

It does **not** own semantic world state, action authorization, reward, verifier truth, termination, or operational effects. A sandbox result may become evidence for an operational action/effect only when the portable runtime or another authorized semantic layer explicitly applies that action/effect. Sandbox filesystem mutation alone never changes operational ground truth.

## Core surface

`SandboxProviderProtocol.create(request)` returns a `SandboxSessionProtocol`. A session exposes:

- `mount(asset_id, content)` for assets declared in `SandboxCreateRequest`;
- `execute(request)` for allow-listed command/tool capabilities;
- `capture(paths)` for artifacts under declared writable paths;
- `reset()` to restore the mounted baseline and discard execution-created state;
- `metadata()` to report deterministic/replay-relevant infrastructure identity;
- `destroy()` to invalidate the session and clear local state.

The core models and protocols contain no Daytona, Modal, Docker, Kubernetes, or other provider-specific concepts. Provider identity appears only as generic `provider_name` / `provider_version` replay metadata. Provider adapters can be added in isolated modules without changing the contract.

## Asset and filesystem boundary

Assets are declared by logical `asset_id`, normalized relative POSIX mount path, expected SHA-256, and read-only flag. Mounting accepts bytes only. There is no host-path field in the provider-neutral contract, so a caller cannot request an arbitrary host filesystem mount through this API.

Execution artifacts are accepted only under `writable_paths`. Read-only mounted assets cannot be overwritten. `capture()` is also restricted to writable artifact paths, so mounted input fixtures are not accidentally turned into public trajectory artifacts.

`LocalDeterministicSandboxProvider` is the first implementation. It uses an in-memory virtual filesystem and registered pure handlers; it does not invoke host subprocesses or expose host filesystem paths. Handlers receive a read-only snapshot and return a filesystem delta. The delta is committed only after timeout/output/artifact/path policy checks pass.

## Failure attribution

`SandboxExecutionResult` separates these origins:

- `request`: invalid provider-neutral request shape;
- `policy`: denied capability, path, timeout, or resource ceiling;
- `workload`: an allowed command/tool ran and returned a non-zero exit code;
- `infrastructure`: the provider could not supply or execute the configured handler.

An infrastructure error is therefore never represented as a workload/model failure. The sandbox contract intentionally has no `model_failure` field.

## Secrets and public output

`SandboxSecretRef` contains only a non-secret alias and opaque identifier. Secret material is supplied privately to a provider implementation. The local deterministic provider redacts referenced secret byte sequences from stdout, stderr, captured artifacts, and surfaced exception messages before returning public result models or persisting virtual artifacts.

Secret values are not included in create requests, spec digests, replay metadata, or result schemas.

## Determinism and replay metadata

`SandboxReplayMetadata` records:

- contract version;
- provider name/version;
- deterministic create-spec digest;
- declared asset-manifest digest;
- seed;
- reset generation;
- execution index;
- virtual-filesystem digest.

The ephemeral `session_id` is deliberately separate from replay identity. Two sessions created from the same request, receiving the same mounted bytes and deterministic handler results, produce identical replay metadata even though their session IDs differ.

Reset restores the mounted baseline, removes execution-created files, sets the execution index back to zero, and increments reset generation. Destroy clears state and makes subsequent session operations invalid.

## Resource policy

The initial neutral policy supports deterministic ceilings that the local test double can actually enforce:

- timeout in milliseconds;
- maximum combined stdout/stderr bytes;
- maximum bytes in an execution's artifact delta;
- maximum dispatched executions per reset generation.

Future provider adapters may enforce stronger CPU, memory, network, or isolation policies internally. Such provider capabilities should not be added to the neutral contract until they have cross-provider semantics that can be stated and tested without leaking a specific provider's vocabulary.

## Integration rule

The safe integration sequence is:

1. Portable/runtime layer authorizes an operational action or tool invocation.
2. Sandbox executes the infrastructure portion under declared capabilities/policy.
3. Sandbox returns infrastructure result, artifacts, failure attribution, and replay metadata.
4. The semantic runtime decides whether an authorized operational effect follows from that result.
5. Verifier/reward logic evaluates semantic state independently of sandbox infrastructure state.

This ordering is the falsifier for accidental ground-truth mutation: sandbox state is evidence/infrastructure, never semantic authority.
