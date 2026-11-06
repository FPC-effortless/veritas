# Native submission and persistent state

Work ID: `NATIVE-SUBMIT-001` (#431). Part of completion tracker #430.

`NativeOperationalRuntime.submit` verifies the materialized artifact before ordinary
seven-component verification. Native check results become `native_artifact.*` state
assertions. With a persistent substrate, those results must reach the substrate,
because the ordinary verifier reads its state rather than the runtime's local copy.
Previously, identical successful native executions could receive different scores
solely because a substrate was attached (financial state/outcome: 1.0 versus 0.5).

The runtime now uses the existing `PersistentOperationalSubstrate.apply_changes`
API to append one evaluator event (`actor="verifier"`,
`action_name="verify_native_artifact"`) containing the check results. This preserves
append-only state reconstruction. It does not fabricate an agent `ActionEvent`,
charge agent budget, remove artifact checks, or change verifier identity/weights.
Standalone execution is unchanged. A repeated submission fails before verification
or any history mutation.

Regression coverage in `tests/unit/test_native_substrate.py` compares complete
verification results in all five domains, checks substrate replay and integrity,
ensures agent traces/budgets are untouched, rejects repeat submission, and corrupts
a real workbook to prove both runtime modes reject the same artifact failure.

## Remaining integration boundary

This is **not** native offline-reverification completion. G-03 (#395 / PR #397)
still needs a separately owned reconciliation for submit-time native assertions and
failure attribution: the current reverification engine reconstructs state only from
agent `ActionEvent.state_changes`, whereas artifact checks occur at submission.
Do not fold evaluator events into agent actions, silently omit native checks, or
relax the engine's state-chain validation to claim a round trip. A content-bound,
evaluator-private submission-evidence contract and its canonical trajectory binding
need their own ownership and review. No scientific, frontier, training, commercial,
or release qualification follows from this correction.
