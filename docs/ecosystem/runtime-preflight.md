# Runtime provenance preflight: local inspection, not native admission

This additive helper responds to the independent laboratory's SET-STAGE-070 and
SET-IMPORT-PROTOCOL-071 findings in Veritas issue #482. Those investigators staged
and inspected ENV064; this implementation did not reproduce staging, import the
candidate, or establish runtime viability.

The exact archived Torch 2.6.0+cpu `torch/__init__.py` SHA256 is
`5a190666c3853aa236c4d48ed64e2d4bbcd23bd32c21e64c0867646a6852e43f`.
Its lines 2779–2784 enable backend discovery when
`TORCH_DEVICE_BACKEND_AUTOLOAD` is absent; lines 2756–2758 load and call discovered
entry points. Native initialization at line 2046 means “import-only” is not
“no native calls.” Clearing the environment does not disable autoload.

## Implemented local boundary

`trainlab.runtime_preflight.inspect_runtime` checks a separately operator-pinned
policy and local file inventory without importing any candidate code. It checks:

- exact interpreter/file bytes and modes, with bounded file count/total bytes;
- no missing/extra regular files or symbolic/special members;
- canonical existing paths without symbolic-link ancestors;
- explicit proposed `-I -S -B`, three import roots, and exact environment including
  `TORCH_DEVICE_BACKEND_AUTOLOAD=0` instead of an empty environment;
- before/opened/after file observations for detectable replacement during read.

It always returns `native_execution_admitted: false`, `runtime_viability: UNTESTED`
and `isolation: NOT_DEMONSTRATED`. `require_native_admission` refuses every receipt,
including a forged affirmative flag. It is intentionally not wired to a launcher.
No install, permission change, network call, model fit, candidate import or public
publication occurs. Native resource policy and trust authority remain separate.

Input policy fields: `schema=trainlab.runtime-preflight.v1`, canonical `root`,
`interpreter={path, identity}`, `files={relative_path: identity}`, `flags`,
`environment`, `sys_path`. Identity fields are `sha256`, `bytes`, `mode` (integer).
`policy_sha256` is SHA256 of TrainLab canonical finite JSON `_bytes(policy)`.
Policy hashes identify content; an attacker-supplied hash is not operator approval.

## Required remaining work

The e692367 assurance capture records Torch version/build, Python/platform and
capture/observer source hashes. Those are useful replay identities, not a native
runtime lock. The runner inherits its environment. Identical version/build strings
can coexist with different backend plugins or native dependencies. This does not
show existing numerical results are wrong, only that runtime equivalence is weaker
than complete binary closure.

Before connecting any native launcher:

1. Freeze an operator-selected runtime policy and complete relevant distributions,
   executable modes, loaded library/dependency identities and import-path policy.
   The original experiment lock and a new candidate runtime remain distinct.
2. Demonstrate filesystem/network/credential isolation and resource enforcement in
   the actual host. `-I/-S`, read-only modes and process groups are not a sandbox.
   Same-user changes, ancestor replacement and hash-to-use races remain possible.
3. Independently exercise timeout, output cap, malformed/missing receipt, crash,
   child escape/cleanup, environment merge, plugin-entrypoint and custody-change
   controls using inert stdlib stand-ins. Inventory matching is not a launcher test.
4. Obtain applicable native-import authority before one exact-runtime import probe.
   Record actual environment, flags, path, origin, version and library observations.
   Disabled plugins must be set before the first Torch import; setting it afterward
   cannot undo earlier side effects. Existing Torch imports should block a clean
   runtime claim.
5. Keep static inspection, actual import viability, measured model execution,
   numerical replay and scientific adequacy as separate results. Neither an
   accepted signed review nor an import success supplies the other results.

The helper does not bind empty directories or the contents of stdlib/dynload
roots. It does not establish complete native loader closure, immutable custody,
rights clearance, installation completeness or secret-safe execution. A
`torch_shm_manager` executable-mode difference must be preserved, not treated as
proven import failure or repaired silently. The stage manifest is not binary
custody after its original scratch tree disappears.

## Non-atomic inventory observation

Directory enumeration and file hashing are sequential, not an atomic filesystem
snapshot. A file added after enumeration can be absent from the checked inventory;
`STATIC_LAYOUT_MATCH` means the enumerated files matched at observation, not that
an identical complete tree existed at one instant or remains unchanged afterward.
Individual before/after file checks do not close directory-level races. Repeating
a scan can detect some changes but cannot prove immutable custody. This is why a
matching report still cannot authorize native execution. The regression test
retains a deterministic after-enumeration addition and verifies refusal of native
admission rather than claiming this race has been prevented.

## Startup semantics and timing are unverified

The independent laboratory's SET-ENV-073 review (Veritas #482,
comment 6889492811) found that explicitly supplying `LC_CTYPE=C.UTF-8` made
Python's observed environment equal its requested environment, but changed
`sys.flags.utf8_mode` from 1 to 0 under its pinned interpreter, in both normal
and optimized runs. Equal environment dictionaries or encoding names do not
establish equivalent startup behavior. This corroborates and narrows the earlier
072 environment observation, rather than providing native admission.

This static policy preserves its original five-key environment and `-I -S -B`
flags. It neither starts Python nor observes effective flags or locale. Adding
locale keys or `-X utf8` is a policy change, not a transparent repair, and is
refused by this version. A future version must explicitly freeze intended UTF-8
mode, locale, encoding/error behavior and observed startup checks before adoption.

073 also distinguishes recording an input hash from enforcing a separately pinned
expected hash before use. Its owner's probe did not enforce every recorded input;
its independent review checked the frozen members. Our operator policy digest is
checked before inventory use, but none of these sequential checks establishes
atomic hash-to-execution custody or pins the complete native dependency closure.

The 072 fixture's .35-second work-loop budget starts after preflight, with a
separate two-second cleanup polling budget. The 073 proposed 20-second total
deadline is not implemented. A fixed stdlib probe's five-second subprocess timeout
is not proof of a hard end-to-end launch/cleanup bound or escaped-descendant
containment. This helper supplies no launcher or timeout enforcement at all.
