# Prime Verifiers v1 shared-interface gaps

The generic exporter can preserve Veritas semantics without changing shared Veritas code, but the
current Prime Verifiers v1 / FastMCP integration does not expose every primitive required for a
fully public adapter implementation. These are upstream/shared-interface gaps, not reasons to
modify `portable_contract`, `portable_runtime`, or the SRE compatibility exporter in this lane.

## 1. Arbitrary public JSON Schema registration

`PortableActionDefinition.input_schema` and portable runtime-operation schemas are language-neutral
JSON Schema. Current Verifiers v1 delegates MCP registration to FastMCP 1.x. FastMCP's public
`add_tool()` API derives an input schema from a Python callable signature; it does not accept an
arbitrary pre-existing JSON Schema as the registration authority.

The generated adapter therefore:

- retains the exact portable input and output schemas in public Prime `TaskData`;
- registers a permissive raw-argument carrier;
- replaces the FastMCP 1.x internal tool descriptor's `parameters` with the exact portable input
  schema;
- leaves canonical validation to `PortableOperationalRuntime`;
- pins `mcp>=1.24,<2` and fails registration if the expected descriptor API is unavailable.

A future public FastMCP/Verifiers API such as `add_tool(input_schema=..., argument_decoder=...)`
would remove this compatibility shim.

### Output-schema note

The exact portable output schema is preserved in the public task/binding manifest and successful
tool returns are the unmodified portable observation. It is deliberately not asserted as MCP
`outputSchema`: MCP structured-output semantics couple an advertised output schema to
`structuredContent` conversion/validation, while a portable output may use JSON Schema shapes that
FastMCP would otherwise wrap or reinterpret. Advertising a transformed output schema would violate
the losslessness requirement. A public raw output-schema/result-encoder API would close this gap.

## 2. Persisting state for a structured tool rejection

Portable runtime failures are structured results, and a rejected invocation can still affect
budget/event history. Prime Verifiers v1's task-scoped state wrapper publishes mutated tool state
after a successful tool return; when a tool raises, that automatic publication is skipped.

To preserve deterministic replay while still presenting a Prime tool error, the generated adapter
records the invocation and calls the current protected `Toolset._push_state(...)` primitive before
raising the public failure message. The message contains only the portable public failure code and
message; evaluator-private details, budget snapshots, reward components, and state digests are not
returned.

A public Verifiers primitive for "commit task state, then return/raise a tool error" would remove
this protected-method dependency.

## 3. First-party Veritas runtime distribution

The repository package metadata is outside this lane's ownership, and no verified first-party
`investigation-world` registry release was available when this exporter was implemented. The
generated package therefore declares an immutable Git PEP 508 dependency pinned to the Veritas
commit containing the merged portable contract/runtime. That satisfies the no-development-checkout
requirement without an undeclared local path.

A first-party published wheel can replace the Git reference through the exporter's existing
`veritas_requirement` parameter; no Prime semantic mapping needs to change.
