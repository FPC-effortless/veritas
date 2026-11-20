# NX-021 — Generating a correction from independent action outcomes

The previous circle could veto a bad observation yet left roughly a quarter of the key space incorrect or empty under persistent sensor faults. Here an inverse model proposes a replacement and a second outcome checks it. In two disjoint 32-seed panels this raised final accuracy to 99.02%. With both action readings driven by the same faulty sensor observation, confirmed repair reduced accuracy below veto alone.

| Outcome source and policy | Primary accuracy | Primary write precision | Fresh accuracy | Fresh write precision |
|---|---:|---:|---:|---:|
| Independent, veto | 75.00% | 99.49% | 75.59% | 99.31% |
| Independent, inverse repair | 90.96% | 90.2% | 89.06% | 90.1% |
| Independent, confirmed repair | 99.02% | 99.51% | 99.02% | 99.37% |
| Shared, veto | 74.0% | 76.2% | 74.8% | 75.5% |
| Shared, confirmed repair | 67.8% | 70.6% | 68.4% | 69.8% |

The simulator drew a new bijection over eight values for each seed. The learner observed 1,200 noisy cue–effect pairs to estimate the forward and inverse maps. A separately calibrated initial gate filtered proposals. For admitted proposals, all three policies consulted the same first outcome. On disagreement, veto skipped the write, inverse proposed the value most associated with the outcome, and confirmed repair required a second outcome consistent with that replacement. The learner had access to observable effects. The simulator used hidden values to generate effects and score writes. The extra channel's error rate was 10%.

Confirmed-minus-veto improvement was 24.02 percentage points (paired seed bootstrap 95% interval 23.24–24.80), then 23.44 (22.46–24.22). Both panels cleared the prespecified 10-point gain and 95% accepted-write precision. Confirmed repair correctly replaced 676 of 679 values and 694 of 697 values. It used 0.884 and 0.885 action readings per offered proposal, compared with 0.674 and 0.670 for veto, in addition to three initial sensor readings. Empty addresses count as incorrect. Write precision pools writes; final accuracy gives each seed equal weight. Intervals use 5,000 paired seed resamples with seed 123.

The map was stationary and invertible by construction. Sensor independence and informativeness were experimental conditions. Detecting when channels share a fault remains open. Veritas scientific status is NOT_QUALIFIED. Forge selected validation seeds; TrainLab checked run integrity and execution minima; Research Lab linked each run and Forge release to the public evidence record. The fresh replay matched all raw observations.

[Protocol](PROTOCOL.md) · [Full metrics](evidence/summary.json) · [Primary](evidence/primary.zip) · [Fresh](evidence/fresh.zip) · [Replay](evidence/replay.zip)

Use the Python ecosystem installation from the previous circle. From this directory run:

```sh
python run.py /tmp/new-nx021-primary
python run.py /tmp/new-nx021-fresh --fresh
python ../csm_nx2/verify.py evidence/fresh.zip --replay evidence/replay.zip
```
