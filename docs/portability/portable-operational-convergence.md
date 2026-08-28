# Portable operational convergence

Status: **integration candidate, not a release qualification**.

This document records the shared-surface integration of the portable operational feature lanes. It does not supersede Veritas scientific qualification, Frontier Qualification, the sealed SRE release process, or repository release authority.

## Convergence baseline

The convergence branch was cut from `main` commit:

`df5d6f94d53ee15c988c282827b86dec039de8ef`

All required feature lanes were present at that baseline: portable contract/runtime, MCP compiler, Woyengi consumer, trajectory/reverification, NeMo/OpenEnv/Harbor/Prime/HUD exporters, cross-runtime conformance, CLI, sandbox, and Observatory trajectory diagnostics.

## Merged interface identities

| Surface | Interface/version |
| --- | --- |
| Python distribution metadata | `investigation-world 0.11.0` |
| Legacy release manifest | `PortableEnvironmentManifest` schema `0.11.0` |
| Generic portable operational contract | `PortableOperationalContract` schema `1.0.0` |
| Portable contract compiler | compiler version `1` |
| MCP protocol compiler target | `2026-07-28` |
| Trajectory | `veritas.trajectory.v2` |
| Offline reverification | `veritas.trajectory.reverification.v1` |
| HUD generic operational export | export `1`, wire protocol `hud/1.0`, pinned SDK `hud==0.6.15` |
| Harbor generic operational export | `veritas-harbor-export-v1`, Harbor task schema `1.4` |
| OpenEnv generic operational export | `openenv-operational-v1` |
| Prime generic operational export | adapter `prime-verifiers-v1-operational`, export schema `1`, generated package version `0.11.0` |
| NeMo native operational export | NeMo Gym `gymnasium_agent` / `GymnasiumServer` contract as documented on 2026-08-27 |
| Woyengi pinned fixture | WorldBundle/artifact/action-schema `v0.1`, minimum runtime `0.1.0` |

The package root exports `PortableOperationalContract`, `PortablePublicContract`, `PortableOperationalRuntime`, `PortableRuntimeProtocol`, `compile_operational_episode`, `compile_mcp_surface`, `CONTRACT_SCHEMA_VERSION`, and `MCP_PROTOCOL_VERSION`. The installed operational CLI is `veritas-portable`; `tools/world_portability.py` remains a compatibility launcher.

## Release-manifest bridge

`PortableEnvironmentManifest` may carry a `PortableOperationalContractReference` containing only:

- portable operational contract schema version;
- `PortablePublicContract.public_id`.

The full `PortableOperationalContract.contract_id` is intentionally not part of this buyer-safe reference because it commits to evaluator-private semantics. When no generic operational contract is attached, the reference is omitted from serialization rather than emitted as `null`; this preserves the serialized shape and content-derived identity of existing SRE HUD/Prime manifests.

## Runtime compatibility and semantic-loss status

| Runtime | Current mapping status | Full CLI conformance replay | Known unsupported/shared-interface semantics |
| --- | --- | --- | --- |
| Direct portable runtime | canonical | baseline | none within the supported `PortableOperationalContract` schema |
| NeMo Gym | native reset/step adapter over shared runtime | supported | NeMo function tools have no native output-schema slot; exact output schema is retained in Veritas extension metadata |
| HUD | protocol-first adapter over shared runtime/MCP surface | supported | runtime-specific session/prompt fields are generated transport fields |
| Harbor | environment + MCP runtime + separated verifier packaging | supported | container/service configuration is deployment metadata, not portable semantics |
| OpenEnv | adapter delegates through shared MCP/runtime | **not available through the stable public trace API** | stable public API does not expose the complete operator trace required by `AdapterConformanceReport`; implementation parity is instead covered by exporter/direct-runtime tests |
| Prime Verifiers v1 | generated package delegates to shared runtime | **not available through the stable public replay API** | stable public replay exposes only terminal result; FastMCP lacks an arbitrary-public-JSON-Schema registration primitive and a public commit-state-then-tool-error primitive, so the exporter uses documented compatibility shims |

`AdapterConformanceReport.passed` is true only when `semantic_losses == []`. Missing conformance evidence is not converted into a semantic PASS. In particular, OpenEnv and Prime remain explicitly unsupported for full CLI conformance replay until their stable public interfaces expose the required trace fields.

## Verification gates

The dedicated `Portable Operational Convergence` workflow runs the merged portable operational suites for:

- deterministic portable contract identity/serialization and public/private leakage;
- portable runtime reset, permission, termination/truncation, budgets, and verifier behavior;
- MCP compilation;
- all five generic runtime exporters;
- Woyengi pinned-fixture/action-schema parity;
- trajectory conversion and offline reverification;
- cross-runtime conformance and falsifiers;
- sandbox boundaries;
- Observatory trajectory diagnostics;
- installed CLI behavior;
- clean wheel build/install outside the repository checkout.

The workflow also runs Ruff plus an isolated Mypy check over the newly packaged operational CLI surface. Repository-wide Ruff/Mypy runs were used diagnostically during convergence, but they expose pre-existing repository debt and are not substituted for the repository's existing functional release gates or reported as passing evidence.

The existing `Portability Validation` workflow remains authoritative for the frozen SRE HUD and Prime compatibility smoke paths. The ordinary repository `CI` workflow remains authoritative for the full repository pytest/compile/build/production/frontend/container ladder. Sealed production validation remains separately controlled and must not be inferred from ordinary implementation tests.

## Release rule

A green implementation branch is not by itself a release authorization. Promotion requires the repository's existing review, branch-protection, qualification, sealed/private-evidence, and release-workflow authority. Any gate with missing evidence must be recorded as **UNVERIFIED** or **BLOCKED**, never PASS.
