# NX-022 — Does the second channel follow the first?

Six randomized changes to a sensor register per address identified downstream dependence with 98.44% balanced accuracy on the primary panel and 98.83% on fresh seeds. Routing suspected dependent addresses to veto and the remainder to confirmed inverse repair raised final accuracy above both fixed policies on each panel. When a shared fault occurred before the manipulated register, the same diagnostic was near chance.

| Topology and panel | Audit detection, balanced | Audit-routed memory accuracy | Always repair | Always veto | Sham routing | Oracle routing |
|---|---:|---:|---:|---:|---:|---:|
| Downstream, primary | 98.44% | 86.72% | 84.77% | 74.80% | 84.38% | 87.11% |
| Downstream, fresh | 98.83% | 86.72% | 83.79% | 75.00% | 83.40% | 86.91% |
| Upstream, primary | 49.22% | 84.38% | 84.77% | 74.80% | 84.38% | 87.11% |
| Upstream, fresh | 51.76% | 83.59% | 83.79% | 75.00% | 83.40% | 86.91% |

Each Forge validation panel contained 32 disjoint procedural seeds. Sixteen memory addresses included eight dependent action channels and four persistently biased primary sensors, with random overlap. During the audit the world state stayed fixed while the register was overridden. Three or more matches between a decoy's predicted consequence and six observed outcomes classified the address as dependent. The sham scored the same kind of decoy against an unmodified channel. The threshold, intervention point, and selection policy were supplied. The consequence map and proposal gate were fitted from separate noisy calibration encounters. The oracle used hidden dependence labels only to select between the same two write policies.

The downstream gain over always repairing was 1.95 percentage points (paired seed bootstrap 95% interval 0.59–3.52), then 2.93 points (1.37–4.49). The decision rule required positive mean gains against both fixed arms plus 90% balanced detection accuracy downstream on both panels. It passed. The one-time audit cost 96 additional consequence readings and 96 register interventions per world; the accuracy endpoint carries no cost penalty. The outcome draws during deployment were paired across policies and topologies. In the upstream control, a dependence path bypassed the register, so a lack of response to register perturbation provided no assurance of independent evidence. Scientific qualification remains NOT_QUALIFIED.

[Protocol](PROTOCOL.md) · [Primary metrics](evidence/primary.json) · [Fresh metrics](evidence/fresh.json) · [Primary bundle](evidence/primary.zip) · [Fresh bundle](evidence/fresh.zip) · [Replay](evidence/replay.zip)

Using the Veritas ecosystem installation from the preceding studies, run from this directory:

```sh
python run.py /tmp/my-nx022-primary
python run.py /tmp/my-nx022-fresh --fresh
python summarize.py /tmp/my-nx022-fresh/runs/*/output/results.json
python ../csm_nx2/verify.py evidence/fresh.zip --replay evidence/replay.zip
```

The bundles retain the staged code, Forge release, TrainLab recipe and checked execution, Veritas evidence record and Research Lab graph. The primary and fresh receipts passed verification. All fresh raw outcomes matched on replay.
