---
name: code-review
description: Independently review a change across universal, repository-specific, and unnecessary-complexity axes.
---
# code-review
Review separately: (1) correctness/maintainability, (2) task/spec compliance, (3) security/privacy, (4) architecture/invariants, (5) verification evidence, and (6) unnecessary complexity/minimality. For the complexity axis, use Ponytail findings when material: `delete`, `stdlib`, `native`, `yagni`, `shrink`; identify concrete file/line, what can be cut, and what replaces it. Do not flag a necessary smoke/regression check as bloat. Correctness/security/performance findings remain separate from the complexity pass. For Veritas add (7) benchmark/scientific validity, (8) frontier-utility evidence when claimed, (9) leakage/contamination/exploit resistance, and (10) release/private-artifact safety. A pass on one axis cannot cancel a failure on another. Cite concrete file/hunk evidence. If the complexity-only pass finds nothing material, `Lean already. Ship.` is sufficient for that axis.
