# 086: Replay under matched updates

**Selective replay failed the registered directional gate in all three paired schedules. This result is NOT_QUALIFIED.** It improved delayed early-skill Brier error slightly relative to repeating the current example, but never by the prespecified 0.02. Delayed early-skill classification accuracy was zero in every selective run.

## Design and observed results

Three independently seeded order/RNG trajectories shared the same balanced cue–feedback motifs. Within each trajectory, the current-only, uniform-history and highest-loss-history arms began at zero and saw the same 256 observed practices (128 early, 128 interfering late). Each used two logistic updates per observation. The second update either repeated the current observation or reused an earlier item from a capacity-32 bank; before anything was in the bank all three repeated the current observation. The learner had visible cues and feedback consequences only. An inert initial draft had three nominal seeds but identical effective learning sequences and replay RNGs; it was held and corrected prospectively before any learning or held predictions. All three effective sequence and replay stream identities were distinct in executed R2.

The primary rule required selective replay to decrease early-skill Brier error by at least 0.02 relative to current-only in every trajectory, without increasing later-skill error by more than 0.05 anywhere. Brier is the mean squared probability error (lower is better).

| Paired trajectory | Early current | Early uniform | Early selective | Later current | Later uniform | Later selective |
|---|---:|---:|---:|---:|---:|---:|
| 1 | .28901 | .27289 | .28846 | .21466 | .23085 | .21431 |
| 2 | .28994 | .27282 | .28853 | .21749 | .23186 | .21429 |
| 3 | .29020 | .27492 | .28848 | .21564 | .23267 | .21433 |

The selective early gains were 0.00055, 0.00141 and 0.00172. Its later penalty bound was met. Early accuracy (current/uniform/selective) was 0/37.5/0%, 50/50/0% and 50/50/0%. Uniform replay gave a descriptively better early Brier result in all three schedules, at higher later error. Its comparison was secondary; it did not establish a promotion or a general replay advantage. Each trajectory's two held panels scored 16 entries each, repeating eight cue motifs twice. Distinct trajectories do not provide independent task families, and repeated query entries are not independent new skills or evidence of generalisation.

## Work and custody

Each arm and trajectory consumed 256 primary observations, 512 updates and 1,536 feature touches. Each replay arm used 255 historical secondary updates. Selective inspected 7,664 bank entries per trajectory, uniform inspected 255 and current-only inspected none. This is matched update work, **not** total matched compute or memory cost. Combined native fit, predict and verify elapsed times were 0.171152 s, 0.035612 s and 0.054894 s, respectively, across all arms and trajectories. These are stage measurements, not per-arm latency or complete costs, and exclude upstream world/data construction and review. No 12:1 inference advantage follows.

- Design: [PROTOCOL_082_086.md](PROTOCOL_082_086.md), 086 section; [prospective trajectory amendment code](stage_086_trajectory.py) SHA-256 `d87e8d5c2a020be04b696cf1b96fed21f4b1c4abe00c1aab80df41a9b5855549`. Staged role protocol `143b5118b80cc7e64a9bbb52b6527fa5abe635c79860d510d391cc8f27228943`; world specification `ca24c0d1e7bb4e82d99d71f7e104ce131ea987852dee19bc9658a8bf52580553`.
- Exact [stage worker](stage_086_worker.py) `65e706622ee18db542e18ebc8d18f4eb2915b4fa5d9242019a31241c4d6ad823` and [learner](../../src/research_lab/life_study_082_086.py) `596e59decbb39522d5fe97f3660805a031682e83a35d7c5df5cd60c99d362c33`.
- Reviewed recipe digests: fit `eba1f815a9433fb663d0fa1844eadc8ddd6d26c0ba478dd285a62d91abca6166`, predict `2a3c637adee7ece3fde4c204d7b7cc27eaf9ec3971e4fc82a11b81df2c47afba`, verify `f8dbc2184df0e72bfc347fae0d4a33ad7ea330beb276ecbf65c1077c23090f08`.
- Canonical 081 world gate stage digest `25c71b275e128ee8dd534d6cd6adcfbcf077c942a564f121ef27f1e91721fd94`. Native verified stages: fit `cd56f9c4e90c7e1442957206c235e339938817c8208c3bc19b300af7da050a70`, predict `e44b98f458a02720e949d69831ad1287d381d0e17a2fd57f8a7c0d14f6d1542d`, verify `43e1d68176e0a6cf18ddf91e5b66f62fbb89af08cb90723b4d77f8f945040b4d`. Private aggregate `718e941ff9f41069ed3f33ceac9158d737cacb183bcc5fe8a3888ce0722f5567`; typed Veritas evidence `4dd660d8fef8511e86d460e45c2adfcf036a106ace972b421dcd15bbc2177db3`. Digest references do not provide access to private artifacts.
- All three separately reviewed TrainLab stages met their declared execution criteria. The predictor consumed only 96 cue-only requests, with earlier/final checkpoint snapshots recorded before scoring. The verifier consumed sealed truth and retained predictions, with no refit or new prediction. Research Lab recorded the private evidence. The independent retained-output audit verified all three native receipts, recomputed 576 saved probabilities from checkpoint snapshots and checked all 36 arm/snapshot/phase/trajectory metric cells. No separate executable same-seed replay was performed.

## Resume

Use the [four gates](FOUR_GATE_PROTOCOL.md), [bundle builder](stage_084_086_bundle.py) and [conductor](conductor.py). Audit the completed run from authorized private artifacts; do not relaunch its stages or reuse old approvals. Any follow-up needs a distinct execution root, prospectively frozen data, adequate independent interference families, separate exact fit/prediction/scoring review, and comparison of full cost (including selecting and reading history). Preserve this failed gate rather than selecting a favorable metric or renaming the chosen comparator afterward. Raw records, hidden answers, per-request predictions, checkpoint bytes, private cohort identifiers and approval records are not in this checkpoint.
