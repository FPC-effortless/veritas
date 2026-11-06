# Environment fidelity contract (ENV-001)

Veritas fidelity labels describe **realism and implementation scope only**. They do not establish
verifier correctness, scientific validity, capability usefulness, Frontier qualification, or release
maturity.

The governed levels are:

- `L0_ABSTRACT_STATE_MODEL`: abstract state transitions with evidence for the state-model contract.
- `L1_STRUCTURED_SYNTHETIC_APPLICATION`: structured synthetic application behavior is exercised.
- `L2_NATIVE_ARTIFACT_EXECUTION`: native artifacts are executed in addition to modeled application
  behavior.
- `L3_FAITHFUL_MULTI_SERVICE_REPLICA`: the environment implements evidenced multi-service topology
  and interactions.
- `L4_CONTROLLED_REAL_SYSTEM_INTEGRATION`: a controlled integration crosses a real-system boundary.

A label is not a free-form environment assertion. `FidelityDeclaration` requires version-bound
evidence, explicit coverage by realism dimension, limitations, omitted real-world semantics, and
reset/replay constraints. Each level has baseline evidence and coverage requirements; stricter
qualification policies may add claim-specific minimum levels or require particular dimensions.

`FidelityRecord` content-addresses the complete disclosure together with the exact assessment-policy
identity. Changing the environment version, evidence, coverage, caveats, reproducibility profile, or
policy therefore changes the record identity.

`FidelityClaimRequirement` is the policy hook for consumers such as Gold-10. Consumers can reject a
claim when the recorded level is below the minimum, when a required dimension is omitted, or when a
dimension must be fully covered but is only partial. This check is deliberately separate from the
environment runtime, so existing flagships can consume fidelity metadata without runtime changes.

## Interpretation rules

Do not infer a higher level from one implementation detail. In particular, the presence of a native
file is not sufficient for L2 or L3: all dimensions required by the level must have non-omitted,
evidence-linked coverage. Evidence is bound to the exact `environment_version`; evidence from another
version is rejected.

Fidelity is a disclosure boundary, not a quality score. L4 is not automatically "better" for a task
than L2, and no fidelity level implies that a verifier is correct or that a capability claim has been
scientifically established.
