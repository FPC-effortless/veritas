# CSM-NX-011–020 — Autonomous verification and acquired procedures

The learned verifier admitted 3,408 writes on the primary independent-noise panel. All were correct, every key acquired a value, and the old and newly introduced records were all correct at the end. In every seed the learned gate recovered the same simple policy: require at least two of three probes to agree with the proposal. A fixed rule produced identical decisions. When the sensors and proposer shared a persistent error on four of sixteen keys, 865 of 3,407 admitted writes were wrong. The hardest verification problem in this experiment was obtaining independent evidence.

This is a bounded synthetic study. Veritas recorded OBSERVED evidence with scientific status NOT_QUALIFIED. The primary panel used 32 Forge validation seeds. The independent-consequence and checkpoint alias probes were follow-ups on those same seeds. A second Forge release supplied 32 disjoint validation seeds for replication and two additional controls. See the fresh results below.

[Prospective protocol](PROTOCOL.md) · [Primary archive](evidence/primary.zip) · [Extended archive](evidence/extended.zip) · [Replay](evidence/replay.zip) · [Per-seed observations](evidence/results.json.gz) · [Summary and intervals](evidence/summary.json)

## NX-011 — what the verifier could learn

For each seed the learner fitted a four-bin predictive model on 1,200 calibration encounters. Each encounter contained a proposed value, three noisy probes and a later independently sampled environmental consequence. The model estimated the probability that the consequence would agree with the proposal, conditional on the number of agreeing probes. It received no simulator correctness bit, latent skill value, or supervised accept/reject target. The experiment supplied the feature, sampling policy, noise channel and 0.75 admission threshold.

Evaluation introduced eight keys, then eight more, then reversed four of the original values. The 5,120 opportunities across seeds included writes to existing keys. Final old accuracy scores the four original, unchanged keys; new accuracy scores the eight introduced later. The four reversed keys are scored separately. One lookup produces one action. These measures do not replicate the previous cycle's autonomous multi-step rollout.

| Primary condition | Accepted-write precision | Accepted / offered | Final key coverage | Old | New | Reversed keys | Online accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| Learned, independent errors | 100% | 66.56% | 100% | 100% | 100% | 100% | 93.40% |
| Fixed two-agreement rule | 100% | 66.56% | 100% | 100% | 100% | 100% | 93.40% |
| Accept all, independent errors | 68.34% | 100% | 100% | 71.88% | 68.36% | 75.00% | 68.34% |
| Reject all | undefined | 0% | 0% | 0% | 0% | 0% | 0% |
| Learned, common-mode fault | 74.61% | 66.54% | 100% | 75.78% | 74.61% | 75.00% | 69.79% |

The frozen decision rule required ≥95% pooled precision, ≥75% final coverage and ≥85% each on old and new records. The learned and fixed gates passed under independent noise and failed under common-mode corruption. Reject-all failed. Relative to accept-all, learned old accuracy improved by 28.1 percentage points (paired seed bootstrap 95% interval 21.9–35.2), and new accuracy improved by 31.6 points (26.6–36.7). Observed zero errors is a finite-panel result.

A follow-up learned a separate action-to-consequence mapping from noisy calibration observations. Under common-mode corruption, requiring this additional consequence to agree produced 2,269 correct writes out of 2,280 accepted (99.52%). Final coverage fell to 76.95% and accuracy across all keys reached only 75.20%. When the extra channel also shared the original sensor reading, precision fell to 74.47%. This follow-up tests a veto; it cannot reliably invent a correct alternative proposal for a systematically corrupted address.

The learned policy cost three probes per proposal. Mean within-seed median/p95 cost was 1.02/1.45 μs for generating a proposal and its three simulated readings, deciding, writing and retrieving the answer. The separately traced warmed loop peaked at 760 bytes of incremental Python allocation. Calibration, real sensor latency, persistent model storage and whole-process RSS are outside that figure.

## NX-012–020

| Study | Experiment and primary or extended-panel result |
|---|---|
| **012 · Matched address capacity** | All arms had 16 keys × 8 output scores and could address every key independently. Final accuracy was 0% frozen (no writes), 85.55% Hebbian, 84.77% eligibility, 70.90% unconditional exact replacement and 100% verified exact replacement. Equal addresses remove the earlier collision confound. Each rule uses a different update policy and effective state; this is not an equal-FLOP comparison. |
| **013 · Recovery** | Inject an incorrect value, then allow up to 16 observation/repair attempts. Under independent noise, learned verification reached correctness and stayed correct through the horizon in 2,046/2,048 cases (99.90%), versus 68.80% unconditional and 0% locked. Median observed sustained recovery was 1 step versus 15 for unconditional. With common-mode bias during the first eight steps, the learned median moved to 9. The archives retain right-censoring; medians exclude unresolved episodes. |
| **014 · Primitive discovery** | The model inferred four unknown six-record permutations from before/after observations containing repeated values. Exact operation recovery rose from 7.81% with one example to 68.75% with three and 100% with eight. Given a hypothesis class of parity predicates and permutation maps, it also identified a conditional operation and achieved 100% on new record values, versus 49.57% for a single fixed map. |
| **015 · Composition depth** | With primitive effects learned and the requested operation sequence supplied, exact execution at depths 3, 4, 8, 16 and 32 reached 97.88%, 97.69%, 97.20%, 96.97% and 96.88%. At depth 32, only 3.87% of goals were reachable by any sequence of length at most two under the learned maps. The two-step reachability control has access to the goal. The study measures execution of a supplied sequence; goal-only discovery is tested in NX-018. |
| **016 · Hierarchy** | Repeated adjacent pairs in training traces induced eight macros with up to five nesting levels. On fresh sequences from the same motif generator, they preserved 100% of outputs using 16.09% of the primitive executor calls. This count excludes the tokenization pass. |
| **017 · Grounded communication** | A learner inferred word–attribute associations and a conditional instruction from scene interactions and action feedback. On withheld color–shape combinations it selected the correct action 100% with one gate-state question per trial, versus 50.03% when silent. Two-token descriptions were 100% exact. Availability of a truthful answer, token boundaries, attribute axes and the choice of when to ask were supplied. |
| **018 · Reusable reasoning procedures** | Search had 160 successor evaluations and 40 unique goal states per seed, all absent from training goals. Primitive breadth-first search solved 25.00%, mined macro search 22.11% and random macro search 21.72%. Mined minus random was +0.39 points (paired 95% interval −1.64 to +2.34). Expanding the vocabulary spent search budget on more branches. Reusable execution alone did not produce a planning advantage. |
| **019 · Compiled inference** | For 16 learned depth-32 programs, all execution paths produced 100% exact outputs. Mean within-seed single-request p50/p95 was 0.442/0.509 μs compiled and 11.50/12.59 μs interpreted. In batches of 256, compiled Python took 0.375 μs/query, vectorized NumPy 0.687 and interpreted Python 12.24. Traced batch Python allocation peaks were about 25.2, 61.5 and 25.3 kB respectively. |
| **020 · Integrated execution** | The full from-scratch path scored 28.91% exact on multi-token requests (mixed lengths 1, 3 and 8); unchecked writes scored 19.08%, immediate credit 7.39%, and supplied routing 100%. In the separate held-synonym checkpoint condition these were 47.07%, 36.20%, 10.19% and 98.37%. Both full paths acquired all four module records. Coverage alone substantially overstates system performance. |

NX-019 mean costs were 746 μs to acquire the four primitive maps and 202 μs to compile the 16-program library. Amortizing these library costs equally and charging twelve median single requests per program gives **64.5 μs compiled versus 184.6 μs interpreted**. The median seed broke even after 1.08 uses per program, equivalent to two whole requests. Inference takes a program ID and a tuple of six input records and returns a tuple of outputs. This speedup applies to that specialized representation. Full language-to-action routing and execution in NX-020 took roughly 260 μs per median request.

The integrated path uses the CDL handoff reader's sparse features, Neuraxon synaptic eligibility for delayed feature-to-module updates, the upstream TAC identity router, a learned admission gate, persistent full-key records, and executable native CDL COPY sequences assembled from an induced and admitted swap. A flat permutation execution control reproduced the full path's accuracy. Native checkpoint and fresh-reader conditions in the first panel differ in vocabulary and test distribution, so the cross-condition difference does not measure the effect of pretraining.

## Disjoint 32-seed replication

The primary verifier decision repeated. With independent errors it made **one wrong write in 3,384 accepted**, reaching 99.97% precision, 99.80% final key coverage, 100% old accuracy and 99.61% new accuracy. The incorrect write was repaired after nine stream events. Under common-mode corruption it made 858 errors in 3,396 accepted (74.73% precision). Adding an independently generated consequence raised precision to 99.44%, while final all-key accuracy remained 75.20%. Four persistently distorted keys deprive a veto-only policy of adequate alternatives.

Depth-32 execution reached 100%, while only 3.09% of targets were reachable within two steps. On held-out goal search, primitive, mined and random macro planners solved 22.73%, 21.02% and 18.75%. The cost-weighted compiled/interpreted estimates were 76.1/219.1 μs per program.

In a new teaching experiment, two agents independently inferred the same six action words from grounded interactions. Given a before/after event, the teacher generated a swap description and sent it to a listener acting on fresh values. Grounded messages produced 100% exact transfers, versus 4.03% each for silence and scrambled vocabulary, over 3,200 trials. The mean message length was 1.89 tokens. Both agents had access to the slot representation, and the teacher used a supplied decomposition algorithm. The learned behavior was the action vocabulary and its transfer across instances.

In the held-synonym integration test we held words, native router, training interactions, requests, verifier and execution path fixed while varying only the reader weights. The upstream checkpoint reached **51.24%** full-request accuracy, fresh reader weights **8.20%**, and supplying the route yielded **100%** for both. The paired improvement was **43.03** percentage points (descriptive 95% seed bootstrap **31.05–55.70**). These aliases come from the upstream reader vocabulary. They were held out of local association training; their semantics need not be novel to the checkpoint. The from-scratch condition that trained all local tokens reached 26.76%.

[Follow-up protocol](FRESH.md) · [Fresh archive](evidence/fresh.zip) · [Fresh replay](evidence/fresh-replay.zip) · [Fresh per-seed results](evidence/fresh-results.json.gz) · [Fresh summary](evidence/fresh-summary.json)

## Reproduction and evidence

The environment used CPython 3.12.14, NumPy 2.3.5, Linux x86-64, AMD EPYC 9V74 and the Veritas base from PR #580. The raw observations include every seed, arm, recovery duration and censoring outcome. The runner pins dependencies by Git commit and retains file hashes. Each ZIP contains the source version actually run, Forge seed release, TrainLab research recipe and checked receipt, Veritas evidence envelope, and Research Lab graph. Previously published dependencies and the frozen upstream reader checkpoint are reconstructed from pinned source revisions. The task families are synthetic; the panel provides no estimate on an external reasoning benchmark or deployment distribution.

From the root of the GitHub branch:

```sh
python -m pip install . ./integrations/forge ./integrations/trainlab ./integrations/research_lab numpy==2.3.5
git clone https://github.com/FPC-effortless/cdl-attention-experiment /tmp/cdl-nx2
git clone https://github.com/DavidVivancos/Neuraxon /tmp/neuraxon-nx2
git clone https://github.com/FPC-effortless/TAC-Prime /tmp/tac-nx2
cd examples/csm_nx2
python run.py /tmp/my-nx2-run /tmp/cdl-nx2 /tmp/neuraxon-nx2 /tmp/tac-nx2 --fresh
python verify.py evidence/extended.zip --replay evidence/replay.zip
python verify.py evidence/fresh.zip --replay evidence/fresh-replay.zip
python analyze.py /tmp/my-nx2-run/runs/*/output/results.json /tmp/my-nx2-summary.json
```

The extended and fresh suites each have their own replay. Verification checks the Forge release, the TrainLab run, the evidence-bound output and equality of every non-timing/non-allocation observation. The archived primary and extended stage drivers reproduce the earlier suite variants using the same local clones.

- [CDL skill executor](https://github.com/FPC-effortless/cdl-attention-experiment/blob/2a3dd21fcbd55e87eca3c4e5bb05846136b86d4f/research/csm-bdh002-handoff/skill001/pilot.py)
- [CSM-BDH handoff reader and checkpoint](https://github.com/FPC-effortless/cdl-attention-experiment/tree/fef6eb2d2528300822b6142aa0bfe27cd9768421/research/csm-bdh002-handoff/study040/base)
- [Neuraxon v2](https://github.com/DavidVivancos/Neuraxon/blob/fbbcdcd7fa74d1f84ca1a8bc64060441e94d66a3/neuraxon2.py)
- [TAC identity routing](https://github.com/FPC-effortless/TAC-Prime/blob/e51a921f82575d57ecf048e82a3898ca968a4224/tacm/tacm/id001/routing.py)
