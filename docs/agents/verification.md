# Verification ladders

## Universal ladder

1. targeted failing test/reproduction/falsifier;
2. targeted unit/integration checks;
3. formatter/lint/typecheck/static analysis as applicable;
4. broader test suite;
5. build/package/container smoke tests as applicable;
6. security/privacy checks as applicable;
7. performance/reliability checks where the change can affect them;
8. release/deployment gates only when this is actually release/deployment work.

Never claim a check passed unless it actually ran.

## Veritas scientific ladder

After implementation checks, add only the gates relevant to the changed surface:
1. deterministic environment/verifier tests;
2. leakage/contamination/private-artifact checks;
3. policy ordering and exploit resistance;
4. distribution/stratum/task-diversity gates;
5. calibration/discrimination evidence;
6. replicated model/agent evidence where required;
7. scientific qualification result;
8. frontier qualification result where applicable;
9. buyer-safe sanitization and exact release-identity checks;
10. aggregate CI/Security and external release requirements.

Scientific/frontier/manual expensive gates are not substitutes for cheap implementation tests and should not be triggered automatically unless the active task requires them.
