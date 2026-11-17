# Docker sandbox provider

`DockerSandboxProvider` executes each allowed command or tool in a fresh container while retaining
the canonical sandbox session workspace and lifecycle. It implements infrastructure semantics only;
container filesystem changes never directly change operational ground truth or verifier state.

## Boundary

Images must be pinned as `name@sha256:<digest>`. Mutable tags are rejected. Every execution uses:

- `--pull never`, so image acquisition is never an implicit side effect of sandbox execution;
- `--rm` and a unique container name;
- a read-only root filesystem;
- all Linux capabilities dropped;
- `no-new-privileges`;
- a PID ceiling;
- the host caller UID/GID;
- a constrained ephemeral `/tmp`;
- the complete workspace mounted read-only; and
- separate writable bind mounts only for declared `writable_paths`.

The default `DockerNetworkPolicy.NONE` passes `--network none`. `BRIDGE` is an explicit
operator-controlled opt-in for the container workload. Neither policy authorizes the Docker daemon
to acquire an absent image: a missing pinned image fails closed and must be installed by an explicit
operator action outside sandbox execution. There is no automatic fallback to Local execution when
Docker, its daemon, or the configured image is unavailable.

## Example

```python
from investigation_world.sandbox import SandboxCapabilityPolicy, SandboxCreateRequest
from investigation_world.sandbox.providers.docker import DockerCommandSpec, DockerSandboxProvider

provider = DockerSandboxProvider(
    image="registry.example/veritas-worker@sha256:<64 lowercase hex characters>",
    commands={"compile": DockerCommandSpec(argv=("/worker", "compile"))},
)
session = provider.create(
    SandboxCreateRequest(
        writable_paths=("outputs",),
        capabilities=SandboxCapabilityPolicy(commands=("compile",)),
    )
)
```

Command requests append argv to the registered command. Tool arguments are passed as canonical JSON
on stdin. Neither request kind can replace the pinned image or registered executable prefix.

## Lifecycle and evidence

`create()` validates Docker daemon availability and creates a private session workspace; it does not
start a persistent container. Mounted assets form the reset baseline. Each `execute()` uses a fresh
container against that workspace. `reset()` restores mounted bytes and discards mutations.
`destroy()` removes the host-side workspace and secret material.

Replay metadata binds the create request, asset declarations, pinned image and provider
configuration, Docker daemon identity, seed, reset generation, execution index, and filesystem
digest. Container names and host temporary paths are ephemeral and are never returned.

Docker-reserved launch exit codes are reported as infrastructure failures, not workload/model
failures. Timeout and output-limit interruption both force `docker rm -f` for the named container
before the workspace result is accepted. A successful removal permits the original timeout or
output-limit result to be returned. If removal raises, times out, exceeds its output bound, or exits
nonzero, container absence has not been established: the execution fails closed as an infrastructure
error and that session is permanently non-reusable. Only `destroy()` remains available so host-side
workspace and secret material can still be discarded. This prevents a possibly orphaned container
that retains workspace or secret bind mounts from being followed by further sandbox operations.
Missing Docker or a failed daemon probe raises `DockerUnavailableError` before a session exists.

The shared workspace layer rejects and rolls back read-only input changes, symlinks, non-regular
files, undeclared output paths, and resource-policy violations. It revalidates copied Pydantic
requests before trusting paths or capability shapes.

Secrets use a read-only `/run/veritas-secrets` mount with hashed filenames and a public-alias
manifest. Values are excluded from argv, environment variables, replay metadata, and the ordinary
workspace, and are redacted from surfaced output and artifacts.

## Limits

Image acquisition remains an operator concern rather than an execution side effect. Sandbox runs use
`--pull never`; they neither silently pull an absent digest-pinned image nor substitute a tag. The
neutral v1 resource policy does not express portable CPU, memory, or disk limits, so this provider
enforces only the shared timeout/output/artifact/execution limits plus its fixed hardening defaults.
Portable CPU/memory fields require a separately reviewed shared-contract extension rather than
Docker-specific values leaking into environment semantics.
