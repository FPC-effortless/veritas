# CSM-NX — Neuroadaptive Skill Acquisition

Verified admission was the strongest result. After two eight-state skills had been learned in sequence, protected exact records scored 100% on both cycles after 64 silent ticks. An equally persistent, unchecked first-write table scored 39.9% on the old cycle and 43.5% on the new one. The difference depends on access to reliable feedback and a persistent internal cursor per skill.

This research ran all ten bounded experiments with Forge, TrainLab, Veritas evidence records and the Research Lab graph. It used the public CDL CSM skill executor and CSM-BDH handoff reader, Qubic Neuraxon v2 neurons and synaptic eligibility, and the TAC-Prime ID001 router. The components were tested separately except where the specified interventions connect them. All observations are from public synthetic problems. The project’s scientific qualification remains NOT_QUALIFIED.

## Results

Means below give each of the 26 Forge validation seeds equal weight. Native and simplified cell diagnostics use different stimuli. Percentages refer to the specified task and metric.

| Study | Measurement and result |
|---|---|
| NX-001 | Noisy binary decisions. Trinary evidence accumulation gave 87.94% accuracy in 3.51 observations, sign-only accumulation with the same stopping threshold 84.40% in 3.15, and continuous accumulation 87.46% in 2.48. One-shot binary gave 71.58%, fixed-six binary 86.60%. |
| NX-002 | After 16 distractions the simplified recurrence scored 51.41% with both mechanisms off, 82.69% with adaptive decay alone, 72.62% with complemented state alone and 90.08% with both. Direct interventions in the upstream cell gave 51.35%, 51.09%, 53.27% and 53.21%, respectively. Native both-on minus both-off was +1.86 percentage points, paired bootstrap 95% interval +0.96 to +2.88. |
| NX-003 | See retention and repair results below. |
| NX-004 | After four intervening events, a decaying eligibility trace recovered 83.17% of cue-action associations versus 60.10% for immediate credit. At sixteen events the scores were 66.83% and 62.98%. Both reached 100% at zero delay. |
| NX-005 | Native TAC identity routing with 1, 2, 4 and 8 messages gave 93.33%, 74.37%, 67.79% and 63.63% decision accuracy. Each task has one informative sender. In a second fixture using noisy scalar relevance, top-one gave 68.27% versus 64.23% with all eight. Ranking costs remain even when fewer messages are consumed. |
| NX-006 | Composition of identified modular-arithmetic operations reached 100% on triples absent from the lookup table, versus 15.34% for identity fallback. The CDL executor separately induced a swap from four observed transitions, admitted it, rejected a truncated program, and executed two rebound swaps correctly on 100% of fresh three-value cases. The primitive vocabulary was supplied. |
| NX-007 | From successful interactions in synthetic four-object scenes, word-feature counts reached 95.18% on withheld color-shape combinations versus 26.23% for choosing the first position. The separate CDL supervised reader reached 62.86% routing accuracy on a held-out instruction template after 32 updates. It uses eight candidate records. |
| NX-008 | A depth-two solver scored 100% on new grids drawn from its two-operation class. On depth-three targets it scored 3.61%, exactly matching identity fallback. In an interactive 5×5 torus with a hidden action mapping, four probes followed by planning achieved 100% versus 16.44% for fixed controls, averaging 6.46 total actions. These are local environments. No official ARC-AGI score was measured. |
| NX-009 | Full grid-rule inference on 128-task batches averaged 7,410 tasks/s serial, 5,498 with two workers and 5,153 with four, with 100% exact outputs. Worker startup, input transfer and result collection are timed. In the separate untraced single-query test, averaging within-seed p50/p95 gave 25.2/70.6 μs for the original solver and 32.2/64.8 μs with cached intermediate transforms. |
| NX-010 | Z3 returned unsat for both counterexample queries. Convex scalar decay preserves its real interval, and verified insertion into an unoccupied integer address preserves every occupied address. Exhaustive implementation checks covered 125 quantized decay transitions, 72 protected-write transitions and 72 revision transitions. These properties assume valid inputs. They do not establish whole-network stability. |

### NX-003 retention and correction

Each learner saw 96 proposal/outcome opportunities. Twenty percent of proposals were resampled uniformly, so occasional replacements were correct by chance. The two skills occupied different exact keys but shared eight synaptic addresses. A silent tick applies quantized synaptic leak without an external observation. Rollout starts at the learner's saved cursor and feeds each prediction back as the next input for 16 steps. The evaluator selects which internal cursor to test.

| Readout | Old skill before interference | Old skill after 64 ticks | New skill after 64 ticks |
|---|---:|---:|---:|
| Frozen | 12.5% | 12.5% | 0.0% |
| Hebbian | 95.0% | 17.3% | 8.4% |
| Reward-modulated Neuraxon eligibility | 100% | 11.8% | 12.7% |
| Unchecked last write | 35.1% | 36.5% | 28.4% |
| Unchecked first write | 43.0% | 39.9% | 43.5% |
| Verified first write | 100% | 100% | 100% |
| Verified first write with 10% flipped decisions | 87.5% | 87.5% | 88.2% |

Comparing the two first-write tables isolates the admission decision at the same key capacity. Old-skill improvement was 60.1 percentage points (paired seed bootstrap 95% interval 43.5–75.7), and new-skill improvement was 56.5 points (42.3–70.9). Comparing a table to the synaptic-only arms also changes addressing and persistent storage. The suite computes all update candidates on one common budget and selects the visible readout. It does not establish equal standalone FLOPs, bytes or latency across architectures.

A separate repair fixture revises eight of sixteen records. Current valid writes, stale valid writes and invalid proposals arrive in shuffled order. With trusted revision numbers, verified versioned COPY applied 100% of corrections. Unversioned accepted writes applied 47.60%, and freezing applied 0%. Every policy preserved the eight untouched keys. Verification feedback is supplied externally. Learning such a verifier is an open question.

### Evidence and interpretation

The first exploratory run used 13 validation seeds. A disjoint 26-seed confirmation added native TAC and stricter controls. Noise, interaction, timing, proof and repair extensions reuse those 26 seeds. They are follow-up analyses. A fresh run of the final suite reproduced every non-timing family exactly. NX-009 checked every output against the generated targets on both runs. Intervals resample paired seeds 5,000 times and are descriptive, without multiple-comparison adjustment.

Process measurements use Linux ru_maxrss. The final run recorded about 89 MiB lifetime parent high-water RSS and roughly 18–19 MiB largest terminated child high-water RSS. These counters are cumulative and do not yield simultaneous total worker memory. Separate tracemalloc readings cover parent Python allocations. Batch numbers include tracing, while the single-query timer excludes tracing, synthesis of test inputs and creation of ground-truth labels. Timings cover the grid solver and depend on this machine and process load.

The models do not jointly learn a general skill library, unrestricted language or an open-ended planner. The most informative failures were the small upstream-cell recall difference, the depth-three grid collapse, and the speed penalty from multiprocessing on small requests. The cited historical Neuraxon headline benchmarks were outside this experiment.

- [Per-seed observations](evidence/results.json) and [means, standard deviations and paired intervals](evidence/summary.json)
- [Final evidence bundle](evidence/final.zip) and [fresh replay](evidence/replay.zip)
- [Development](evidence/development.zip), [confirmation](evidence/confirmation.zip), [feedback and interaction](evidence/feedback-and-interaction.zip), and [inference and proof](evidence/inference-and-proof.zip)

Each archive contains the Forge release and source, stage code and admission recipe, TrainLab run and output, Veritas evidence envelope, and Research Lab graph. External source files are fetched by Git object identity from their originating repositories. The handoff describes older private dependencies. This series uses the published components listed here. An independent review session checked the raw means, final source, run integrity and evidence digest.

## Reproduce

Use Linux with CPython 3.12.14, NumPy 2.3.5 and the Z3 shared library. From the Veritas repository root, install the four packages in a fresh virtual environment. The Veritas base for this series was eec439492407b0aa26922c23b5ae40d95289f4eb. The runner reads from the local clones using full commit hashes. The output directory must be new.

```sh
python -m pip install . ./integrations/forge ./integrations/trainlab ./integrations/research_lab numpy==2.3.5
git clone https://github.com/FPC-effortless/cdl-attention-experiment /tmp/cdl-nx
git clone https://github.com/DavidVivancos/Neuraxon /tmp/neuraxon-nx
git clone https://github.com/FPC-effortless/TAC-Prime /tmp/tac-nx
cd examples/csm_nx
python run.py /tmp/my-nx-run /tmp/cdl-nx /tmp/neuraxon-nx /tmp/tac-nx
python verify.py evidence/final.zip --replay /tmp/my-nx-run
python summarize.py evidence/results.json /tmp/nx-summary.json
```

- [CSM skill executor](https://github.com/FPC-effortless/cdl-attention-experiment/blob/2a3dd21fcbd55e87eca3c4e5bb05846136b86d4f/research/csm-bdh002-handoff/skill001/pilot.py)
- [CSM-BDH handoff reader](https://github.com/FPC-effortless/cdl-attention-experiment/blob/fef6eb2d2528300822b6142aa0bfe27cd9768421/research/csm-bdh002-handoff/study040/base/reader.py)
- [Neuraxon v2](https://github.com/DavidVivancos/Neuraxon/blob/fbbcdcd7fa74d1f84ca1a8bc64060441e94d66a3/neuraxon2.py)
- [TAC ID001 router](https://github.com/FPC-effortless/TAC-Prime/blob/e51a921f82575d57ecf048e82a3898ca968a4224/tacm/tacm/id001/routing.py)
