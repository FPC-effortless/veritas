---
name: diagnosing-bugs
description: Diagnose bugs by building a red-capable reproduction, tracing callers, and testing ranked causal hypotheses.
---
# diagnosing-bugs
Reconstruct the failing context and build the smallest reliable reproduction before explaining causes. Trace the real flow end to end and inspect every material caller/sibling path of the seam you may change. Rank falsifiable hypotheses; change one causal variable at a time. The minimal fix is the root-cause fix: prefer one guard/correction at the shared seam over repeated patches in individual callers. Add a regression check at a stable observable seam, then apply the broader verification ladder. For Veritas, test hidden/public state separation, replay, verifier semantics, leakage, and native-artifact/state agreement when relevant.
