# SRE v4 zero-capital recovery checkpoint

## Recovery state

The original encrypted SRE v4 private seal has been recovered using the matching private RSA key under evaluator-side handling. The key itself and all decrypted private rows remain outside the repository and must not be published.

Recovery verification established all of the following without modifying the frozen release:

- encrypted Actions artifact SHA-256: `9dcfde1f915d51f6f8cec954bf6ed651391dc6f71a24b143273eb1168b57f4aa`;
- the recovered private RSA key derives the same public key committed at `ops/sre-v4-seal-public.pem`;
- both internal encrypted-file checksums pass;
- RSA-OAEP-SHA256 data-key decryption succeeds;
- AES-256-CBC/PBKDF2-200000 private bundle decryption succeeds;
- the recovered ZIP passes integrity validation;
- candidate: `SRE-CAND-92A84929AD1E82E24357`;
- qualification report: `QREPORT-C585121E94D91766BB6664E3`;
- panel: `QPANEL-AFF065BA4C2FD75BE9BB3EBE`;
- evidence manifest: `EVID-2C69B48DCDD5F2232EABDC9B`;
- private release manifest: `PRIVREL-036192DA63716D331C929C0C`;
- 87 frozen scenarios;
- 30 frozen private-test cases;
- 16 recovered source files.

No private scenario text, per-case label, scenario identifier, prediction, or key material is included in this document.

## Buyer-safe zero-cost diversity findings

A private evaluator-side pass over the 30 frozen private cases produced the following aggregate diagnostics:

| Metric | Observed |
| --- | ---: |
| source families | 12 |
| source normalized entropy | 0.81433734 |
| effective source-family count | 7.56515075 |
| largest source-family share | 0.33333333 |
| causal classes | 4 |
| causal normalized entropy | 0.98279812 |
| effective causal-class count | 3.90574086 |
| largest causal-class share | 0.33333333 |
| semantic-cluster proxy count | 25 |
| largest semantic-cluster share | 0.10 |
| near-duplicate share under Frontier normalization | 0.13333333 |
| exact normalized duplicate share | 0.06666667 |
| available-dimension effective diversity | 6.96128788 |

These values are evidence, not a Frontier task-diversity PASS. The recovered SRE v4 rows do not provide six of the eight default structural dimensions used by Frontier Qualification: workflow topology, tool/action sequence, verifier condition, artifact schema, component signature, and grammar family.

The default Frontier policy therefore requires at least four available core diversity dimensions. Sparse dimension coverage produces `UNKNOWN` rather than silently ignoring unavailable structure. This preserves the distinction between a narrow causal-classification benchmark with meaningful source/causal breadth and a richer environment with demonstrated structural task diversity.

## Next zero-capital experiments

With the seal and key recovered, private SRE v4 execution is no longer blocked on artifact custody. The remaining zero-capital sequence is:

1. run the preregistered open-weight model ladder on the exact 30-case frozen panel using private/local compute only;
2. reduce each private evaluation into buyer-safe Frontier observations and categorized failure aggregates;
3. create paired same-panel weak/strong comparisons rather than inflating sample size through repeated runs;
4. run direct versus two-stage harness comparisons on the same model snapshot;
5. leave closed frontier-model and frontier-scale post-training evidence `UNKNOWN` until private-safe credits, partner compute, buyer-run evaluation, or funding is available.
