# Unified Frontier Architecture Research Program

Status: coordination design, not an active training campaign. Parent implementation: Veritas Research Lab OS draft PR #470. The canonical 18-lane machine-readable registry is in `integrations/research_lab/examples/frontier_unified_program.json`.

## Objective

Develop and independently verify a frontier-competitive novel general-purpose TAC-OSM/PLM architecture. Run independent architecture hypotheses in parallel, then integrate only mechanisms that improve the complete model under matched compute and real data. Attention-free operation is not a requirement.

## Leadership and boundaries

The director owns frozen protocols, fair compute allocation and coordinated synthesis; independent lane leads perform engineering and experiments. A separate replicator challenges claims and maintains blind final sets. The integration lead measures coupled mechanisms. Human approval is required for spending, advancement to costly scale, merger and public breakthrough claims.

## Architecture and experimental tracks

A: PSN, PSN2, DPSL, Bounded Field, ATLAS-CASSA, USEF-X, NSF-v8/NFD.
B: TAC_CORE, SSA, GPU_KERNELS.
C: SCM_SIE, GEOMETRIC_KAKEYA, TOKENIZATION, LEARNING_OBJECTIVES, TAC_OCR.
D: PRS, MEMORY_GOVERNANCE.
F: FLOCK_COLLECT (collective local interaction and corrective associative memory).
Shared evaluation and replication form campaign E.

The architecture lanes run independently. Shared baseline definitions are reusable frozen artifacts, not scheduling barriers. Only explicit experiment dependencies delay a lane.

## Evidence and promotion

G0: Recover exact source and data, validate correctness and trainability.
G1: Fit with >=3 preregistered seeds; show a hypothesis-specific effect against strong matched controls.
G2: Independent replay, state knockout, OOD/confound checks and complete failure accounting.
G3: Port into TAC-OSM and test base, component A, component B and A+B at similar parameter count and training FLOPs. Promote only for a verifiable Pareto gain without unacceptable regression.
G4: Scale 1M -> 10M -> 50M -> 100M+ with real held-out language, code, structural and efficiency panels, independent review and human approval.

Use Transformer, optimized Mamba-2, Gated DeltaNet-2, GRU, and task-specific diagnostics. Exact stores are references, not learned-model victories. Do not average unrelated scores into a single global ranking.

## FLOCK/COLLECT special protocol

FLOCK004 reported 98.8%, 60.0%, 16.1% corrective recall at 8, 32 and 128 pairs while attention reported 99.6%, 99.9%, 97.4%. The two variables memory load and sequence length were confounded. COLLECT005 fixed length/age/update counts and observed corrective recall 56.5% -> 9.4% as competing keys grew 1 -> 31. Prior records are reported evidence, not independently rerun by this change.

The next campaign must independently vary length, load, target age and overwrite count; compare learned addressing, separate address/value paths, matrix memory, and collective communication. Gated DeltaNet-2 already separates erase and write: novelty requires an additional mathematical difference and comparative gain.

## Runbook

Use a checkout of the stacked branch with TrainLab, Forge and Lab OS installed:

```bash
export PYTHONPATH="$PWD/integrations/research_lab/src:$PWD/integrations/trainlab/src:$PWD/integrations/forge/src"
python integrations/research_lab/examples/frontier_bootstrap.py --check
python integrations/research_lab/examples/frontier_bootstrap.py --root .trainlab/frontier
research-lab --root .trainlab/frontier status
```

Bootstrap registers versioned research knowledge and one program, not training jobs. Actual parallel execution requires operator-supplied trusted work-order recipes, real GPU inventory, persistent workers and independently verified receipts. Paid GPU budgets remain unauthorized. See Lab OS README for agent output and replay contracts.

Initial executable milestone: recover seven ARCHPAR sources; preregister TAC_CORE baselines and FLOCK-COLLECT-006; freeze multi-domain benchmarks; begin matched training only with real workers and budgets. Report failures as faithfully as successes.
