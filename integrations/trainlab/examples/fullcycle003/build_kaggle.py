"""Generate a notebook job definition; does not submit or start Kaggle compute."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


def build(commit, output):
    import nbformat as nbf

    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("an immutable source commit is required")
    notebook = nbf.v4.new_notebook()
    notebook.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    notebook.metadata["language_info"] = {"name": "python"}
    notebook.cells = [
        nbf.v4.new_markdown_cell("""# Full-cycle TAC-OSM 10M on Kaggle T4

This file is a source template; runtime logs and verified session receipts establish
whether GPU work actually ran. Choose GPU T4 ×2 and enable Internet in Kaggle.
The two-rank recipe preserves 200,015,872
pretraining token presentations and 256 total RL trajectories; it changes the
RL optimizer-update count from 64 to 32. It trains 40 layers at width120 with a
3072-token fitted BPE and 10,040,600 parameters.

The first launcher session is bounded to four hours plus checkpoint shutdown
grace (installation before the launcher is extra). It may need a later session.
Only a verified `COMPLETE` session receipt means the full lifecycle finished.
Outputs under `/kaggle/working/fullcycle003` include the prepared release and run
state. Raw public downloads stay in temporary storage, outside Git and outputs.

The builder checks schema and Python cell syntax without executing this template.
Budget arithmetic and launcher controls are tested separately from GPU execution.
"""),
        nbf.v4.new_markdown_cell("## 1. Parameters"),
        nbf.v4.new_code_cell(f"""from pathlib import Path
import os
import subprocess
import sys
import json
import runpy
import importlib

SOURCE_COMMIT = {commit!r}
GPUS = 2
SESSION_BUDGET_SECONDS = 14400
PREVIOUS_OUTPUT_ROOT = None  # Optional attached prior output containing data/ and run/.
PREPARED_DATA_ROOT = None  # Optional verified data/ folder for a fresh run.
SOURCE = Path("/kaggle/working/fullcycle003-source")
OUTPUT = Path("/kaggle/working/fullcycle003")
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
"""),
        nbf.v4.new_markdown_cell("## 2. Require actual T4 hardware before downloads"),
        nbf.v4.new_code_cell("""import torch
if not torch.cuda.is_available() or torch.cuda.device_count() != 2:
    raise RuntimeError("Select Kaggle GPU T4 x2 before running this notebook.")
devices = [torch.cuda.get_device_name(i) for i in range(2)]
if any("T4" not in name for name in devices):
    raise RuntimeError("This job requires T4 x2; no accelerator fallback is enabled.")
version = tuple(int(part) for part in str(torch.__version__).split(".")[:2])
if not (2, 5) <= version < (3, 0):
    raise RuntimeError("A supported CUDA PyTorch 2.5+ install is required.")
print({"devices": devices, "torch": str(torch.__version__), "training_ranks": GPUS})
"""),
        nbf.v4.new_markdown_cell("## 3. Install the exact source and training dependencies"),
        nbf.v4.new_code_cell("""if not SOURCE.exists():
    SOURCE.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(SOURCE)], check=True)
    subprocess.run(["git", "-C", str(SOURCE), "remote", "add", "origin",
                    "https://github.com/FPC-effortless/veritas.git"], check=True)
    subprocess.run(["git", "-C", str(SOURCE), "fetch", "--depth", "1", "origin", SOURCE_COMMIT],
                   check=True)
    subprocess.run(["git", "-C", str(SOURCE), "checkout", "--detach", "FETCH_HEAD"], check=True)
head = subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip()
dirty = subprocess.check_output(["git", "-C", str(SOURCE), "status", "--porcelain",
                                 "--untracked-files=no"], text=True).strip()
if head != SOURCE_COMMIT or dirty:
    raise RuntimeError("Existing source is different or modified; use a fresh source directory.")
subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                str(SOURCE), str(SOURCE / "integrations/forge"),
                str(SOURCE / "integrations/trainlab") + "[training]",
                "tokenizers==0.23.3"], check=True)
# Packaged installs are visible to this already-running notebook kernel.
importlib.invalidate_caches()
_ = importlib.import_module("trainlab.runner")
"""),
        nbf.v4.new_markdown_cell("""## 4. Acquire, verify, probe GPUs and train

The launcher downloads the pinned public data, fits TRAIN-only BPE, checks the
reviewed release/tokenizer hashes, persists prepared inputs and performs a small
synthetic GPU gradient/communication diagnostic. Diagnostic weights are discarded.
The full pipeline then starts from its own seeded initialization. No private
evaluation data or account token is embedded here.

To resume in a new Kaggle session, attach the previous outputs and set
`PREVIOUS_OUTPUT_ROOT` to their root. Keep the same source, runtime and GPU count;
the controller refuses incompatible recovery. Save the complete output folder.
For a fresh run reusing only approved data, set `PREPARED_DATA_ROOT` to the
previous `data/` directory. This verifies/copies the release and tokenizer without
copying an old run protocol or optimizer state. Set only one input option.
"""),
        nbf.v4.new_code_cell("""launcher = SOURCE / "integrations/trainlab/examples/fullcycle003"
launcher = launcher / "kaggle_run.py"
arguments = ["--output", str(OUTPUT), "--gpus", str(GPUS),
             "--budget-seconds", str(SESSION_BUDGET_SECONDS)]
if PREVIOUS_OUTPUT_ROOT:
    arguments += ["--resume-input", str(PREVIOUS_OUTPUT_ROOT)]
if PREPARED_DATA_ROOT:
    arguments += ["--prepared-input", str(PREPARED_DATA_ROOT)]
# Run the supervisor in this kernel so Stop reaches its checkpoint grace handler.
# An extra subprocess.run wrapper would kill the supervisor too early on interrupt.
runpy.run_path(str(launcher))["main"](arguments)
"""),
        nbf.v4.new_markdown_cell("## 5. Inspect actual status and preserve outputs"),
        nbf.v4.new_code_cell("""receipt = json.loads((OUTPUT / "session-receipt.json").read_text())
print(json.dumps(receipt, indent=2))
if receipt["status"] != "COMPLETE":
    print("Full training is not complete. Preserve outputs before starting another session.")
else:
    report = json.loads((OUTPUT / "run/report.json").read_text())
    print({"optimizer_updates": report["total_optimizer_updates"],
           "model_manifest_sha256": report["model_manifest_sha256"],
           "qualification": report["scientific_qualification"]})
"""),
    ]
    for cell in notebook.cells:
        if cell.cell_type == "code":
            ast.parse(cell.source)
    nbf.validate(notebook)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(notebook, output)
    receipt = {
        "status": "STAGED_UNSUBMITTED",
        "source_commit": commit,
        "accelerator": "NvidiaTeslaT4",
        "gpu_count_required": 2,
        "pretraining_token_presentations": 200015872,
        "schema_validated": True,
        "python_cells_compiled": True,
        "gpu_executed": False,
        "browser_preview_inspected": False,
        "execution_scope": "source generation only; submission and GPU evidence are separate",
    }
    output.with_suffix(".staging.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    print(build(options.source_commit, options.output))
