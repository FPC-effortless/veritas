# Phase-1 CASM Boolean benchmark

This directory is the benchmark-first implementation of Phase 1 of the CASM program. It is intentionally independent of the learned router: the generator and oracle must establish that the environment contains genuine structural-selection ambiguity before CASM is evaluated.

## Frozen Phase-1 properties

- single-pass topological Boolean execution; no recurrent settling or spectral-radius calibration;
- operators: AND, OR, XOR, NOT, plus INPUT/OUTPUT;
- binary fan-in is capped at 2;
- fixed slot universe with an episode-specific existence mask;
- true program edges are stored separately from slot existence;
- structural canonicalization is for deduplication, not for replacing raw evaluation inputs;
- exhaustive truth-table evaluation is available for small input counts;
- no runtime values are consumed by the future structural router;
- the first falsification control is `copy-mask`, which has no learned parameters.

The crucial benchmark invariant is that co-existing nodes must admit structurally legal distractor relationships. If existence plus the fixed adjacency already determines every true edge, learned routing is not being tested.

The next implementation stage adds the PyTorch CASM-S harness only after these generator/oracle tests pass.
