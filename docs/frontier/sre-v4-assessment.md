# SRE v4 — Frontier Qualification assessment

## Current state

SRE v4 is scientifically qualified under Veritas 0.10: the frozen public release identifies candidate `SRE-CAND-92A84929AD1E82E24357`, qualification report `QREPORT-C585121E94D91766BB6664E3`, panel `QPANEL-AFF065BA4C2FD75BE9BB3EBE`, evidence manifest `EVID-2C69B48DCDD5F2232EABDC9B`, and private release manifest `PRIVREL-036192DA63716D331C929C0C`. The scientific release passed 18/18 gates.

Its current Frontier Qualification status is:

- `scientifically_qualified = true`;
- `frontier_qualified = false`;
- `frontier_status = NOT_YET_FRONTIER_QUALIFIED`.

The reason is evidentiary, not a reversal of the scientific result. The currently documented Qwen2.5-0.5B and SmolLM2-360M executions are useful real-model/commercial integration evidence, but they are not policy-declared strong/frontier calibration evidence. Frontier Qualification therefore emits `UNKNOWN` for non-saturation rather than inferring utility from those runs.

## Evidence still genuinely missing

Under the default Frontier policy, SRE v4 still needs:

1. strong/frontier model or agent observations on the exact frozen panel, with immutable model snapshot and harness identity, to establish non-saturation;
2. weak/medium versus strong/frontier comparable evidence with sample size/uncertainty sufficient for capability-separation inference;
3. paired or otherwise comparable runs of the same strong model snapshot under at least two harness/configuration conditions for harness sensitivity;
4. categorized strong-model failures broad enough to test whether parser, infrastructure, or a single causal class dominates;
5. a sanitized aggregate task-diversity artifact carrying the structural fields required by Frontier Qualification. The frozen public release proves source and causal-stratum breadth, but buyer-safe release metadata alone does not contain the private task rows needed to recompute all topology/action/schema/near-duplicate dimensions;
6. explicit generalization evidence represented by mode rather than a single held-out flag. Existing scientific source-disjoint split construction is important evidence, but Frontier Qualification does not silently convert a release label into unmeasured frontier-agent transfer performance;
7. training-value evidence tied to a policy-declared strong/frontier system. Existing positive Training Value v3 evidence is retained as within-family evidence only and is not represented as cross-family or external-benchmark transfer;
8. a post-training unrelated/control benchmark establishing capability preservation. Without it, the control/regression guardrail is `UNKNOWN`.

This is the intended scientific result: SRE v4 can be a valid benchmark before Veritas has enough evidence to claim it is a frontier-useful training/evaluation environment.
