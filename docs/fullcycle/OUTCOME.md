# FULLCYCLE-001 / FULLCYCLE-002 outcome contract

Requested outcome: build and execute the Forge → TrainLab → evaluation → chat lifecycle.

Owned surfaces: additive Forge language release, TrainLab fullcycle package and CLI dispatch,
public evaluator, fullcycle tests, example configuration, manual workflow, and this documentation.
Existing temporal datasets, protected panels, qualification engines and workbench remain unchanged.

Acceptance: fit BPE only on TRAIN; freeze and verify streaming shards; perform real pretrain,
midtrain, assistant-only SFT, frozen-reference DPO and policy-generated reward optimization;
retain checkpoints and optimizer/RNG/data cursor state; verify interrupted replay; independently
recompute public held-out metrics; export a self-contained model; generate through fresh-process
CLI and local streaming chat; repeat with the pinned TAC implementation if available.

Falsifiers: held-out rows in training; unmasked user loss; missing/wrong reference DPO;
RL labels substituted for policy rollouts; checkpoint/config/hash drift silently accepted;
resume differs from continuous CPU control; cached decode differs from full forward;
self-reported scores promoted to independent qualification; stages without real updates.

Reuse: existing TrainLab JSON/hash/atomic-write utilities and CLI; HF Tokenizers; installed
PyTorch autograd, SDPA, DDP, autocast/GradScaler and activation checkpointing. No replacement
qualification framework or private evaluation access. CPU engineering completion does not
establish GPU performance, broad capability, replicated gains or release qualification.

Integration authority: task branch and reviewable PR. No main merge or package release.
