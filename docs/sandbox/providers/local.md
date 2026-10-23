# Local sandbox provider

`LocalSandboxProvider` executes explicitly registered commands and tools inside a Linux
Bubblewrap boundary. It implements the canonical `SandboxProviderProtocol`; it does not own world
state, action authorization, reward, or verifier truth.

## Boundary

The provider starts from `--unshare-all`, clears the environment, disables host networking by
default, mounts the session workspace read-only, and re-mounts only declared `writable_paths` as
writable. A command can see only:

- its explicitly declared read-only host dependencies;
- the sandbox workspace at `/workspace`;
- an ephemeral `/tmp`;
- `/proc` and `/dev` created by Bubblewrap; and
- `/run/veritas-secrets` when the request declares secret references.

`LocalNetworkPolicy.HOST` is an explicit opt-in. The default is `DENY`. The provider never falls
back to an ordinary host subprocess when Bubblewrap is missing or cannot establish the namespace.

Each `LocalCommandSpec` must name an absolute executable. Dynamically linked commands must also
declare every required runtime tree in `readonly_host_paths`; for example, a distribution may need
read-only `/usr`, `/lib`, and `/lib64` mounts. These are provider configuration, not agent-selected
host paths. Missing dependencies fail during session creation.

## Example

```python
from investigation_world.sandbox import SandboxCapabilityPolicy, SandboxCreateRequest
from investigation_world.sandbox.providers.local import LocalCommandSpec, LocalSandboxProvider

provider = LocalSandboxProvider(
    commands={
        "compile": LocalCommandSpec(
            executable="/usr/bin/python3",
            prefix_args=("/opt/veritas-tools/compile.py",),
            readonly_host_paths=("/usr", "/lib", "/lib64", "/opt/veritas-tools"),
        )
    }
)
session = provider.create(
    SandboxCreateRequest(
        writable_paths=("outputs",),
        capabilities=SandboxCapabilityPolicy(commands=("compile",)),
    )
)
```

The executable and prefix are operator-configured. A command request can append argv but cannot
replace the executable or invoke a shell unless the operator deliberately registered one.
Tool arguments are encoded as canonical JSON on stdin.

## Lifecycle and evidence

Mounted byte assets become the reset baseline. `reset()` deletes execution-created state, restores
the mounted bytes, resets the execution index, and increments the reset generation. `destroy()`
deletes the private temporary workspace and secret files and invalidates the session.

Replay metadata binds the canonical create request, asset declarations, provider configuration,
Bubblewrap identity, seed, reset generation, execution index, and current filesystem digest. The
ephemeral session ID is excluded from replay identity.

The provider rejects and rolls back:

- changes outside declared writable roots;
- symbolic links or non-regular workspace entries;
- stale copied Pydantic requests that no longer satisfy the neutral contract;
- output, artifact, execution-count, or timeout policy violations; and
- missing secret values or undeclared capabilities.

Secrets are mounted as hashed read-only filenames. `manifest.json` maps the public alias to its
in-sandbox path. Secret bytes never enter argv, environment variables, the workspace baseline, or
replay metadata. Returned output, errors, and captured artifacts are redacted.

## Limits

This backend requires Linux user/mount namespace support compatible with Bubblewrap. Some managed
containers disable that support even when the binary is installed; creation then fails closed.

The v1 neutral resource policy provides timeout, output bytes, artifact bytes, and execution count.
It does not yet express portable CPU, memory, disk, or process-count ceilings. Adding those fields
requires a separate provider-contract change with cross-provider semantics; this implementation
does not invent Local-only meanings in the shared contract.
