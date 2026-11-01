# Kaggle full-run launch

Outcome: stage the exact 10M model and reviewed public release for Kaggle's
NvidiaTeslaT4 (T4 x2). The user selected Kaggle for the full run. This launcher
does not alter the native architecture, tokenizer or core training mathematics.

Two ranks reduce pretraining accumulation from 4 to 2, preserving the global batch
and **200,015,872** pretraining token presentations. Mid/SFT/DPO also preserve
their global batches. RL changes 64 to 32 updates, preserving 256 total trajectories;
its per-update global group batch differs. GPU/DDP execution remains unverified
until the actual job runs. A synthetic one-update gradient/communication probe
runs first and discards its weights before the full seeded initialization.

The launcher checks real T4 hardware before downloading, fits the same TRAIN-only
BPE, refuses a release/tokenizer hash mismatch, and copies only the prepared
release/tokenizer into persistent outputs. Raw shards stay in temporary storage.
It uses a four-hour launcher budget plus up to 120 seconds of shutdown grace;
installation before launcher startup is extra. The first session may not finish
the full lifecycle. Status is COMPLETE only after a successful worker and full
artifact verification. Interrupted work is not relabeled as completed training.

Recovery requires the saved data/ and run/ output folders, identical source/runtime
and GPU count. Existing output folders are never overwritten by an input restore.
Resume also compares the entire resolved configuration against this exact full
recipe, including model, seed, precision, stage budgets, prepared release and
tokenizer pins. A valid checkpoint from a different pilot cannot qualify as this
run. The core source/runtime/checkpoint guards remain intact. A changed Kaggle image
can cause strict replay to refuse recovery; that is not bypassed.

Process supervision requires Linux `/proc` to use the current PID namespace and
refuses to start compute when that condition fails. It tracks detached training
ranks, gives their checkpoint handlers time to finish, then removes any remaining
owned process groups. This staging host has a mismatched `/proc` namespace, so
the five process integration fixtures are skipped here. The cheap CPU-only
`Kaggle launch controls` workflow runs them on a normal Ubuntu runner; GPU/NCCL
behavior still requires the actual Kaggle run.

The notebook calls the supervisor directly in its kernel. Notebook interruption
therefore reaches the checkpoint grace handler without an extra subprocess
wrapper that could terminate the supervisor early.

Build the notebook after publishing a concrete source commit:

```bash
python -m pip install 'nbformat>=5.10,<6'
python integrations/trainlab/examples/fullcycle003/build_kaggle.py \
  --source-commit COMMIT_SHA --output FULLCYCLE_003_Kaggle_T4.ipynb
```

Select GPU T4 x2 and Internet in Kaggle, then run all cells. The notebook installs
the pinned source, acquires public inputs, runs the GPU probe and starts training.
No Kaggle credential is embedded. The source checkout refuses unexpected changes.
For an additional session, attach previous outputs and set PREVIOUS_OUTPUT_ROOT.

Falsifiers: silent CPU/other-GPU fallback; doubled pretraining token budget; raw
data copied into Git; unverified inputs; diagnostic weights reused as the training
initialization; overwritten resume data; or submission/completion claimed from an
unexecuted notebook. CPU fixtures cover arithmetic, fail-closed device selection,
restore boundaries, timed process shutdown and notebook syntax/schema.

Current access: the Hugging Face Jobs operation is unavailable; Kaggle has no
available connector or configured API credential, and browser initialization fails
with `failed to start node_repl backend: Connection closed`. No Kaggle job has
been submitted. Notebook GPU execution and visual browser inspection are unrun.
