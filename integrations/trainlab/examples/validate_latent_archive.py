"""Read-only numerical regression against a caller's preserved research archives.

No input records, model weights or empirical outputs are vendored in Veritas.
The command never imports archived research code or invokes a model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from trainlab.latent.geometry import pca_fit
from trainlab.latent.statistics import make_bootstrap
from trainlab.runner import LabError, digest, write_json


def check(root):
    atlas = root / "latent_atlas"
    table = json.loads((atlas / "output/projection_metrics.json").read_text())
    comparisons, inputs = [], {}
    for row in table:
        path = atlas / "work" / row["group"] / f"{row['model_id']}.npz"
        inputs[str(path.relative_to(root))] = digest(path)
        with np.load(path, allow_pickle=False) as data:
            report, fit = pca_fit(data[row["representation"]])
        expected = [row["pca2_variance"], row["pca3_variance"], row["effective_dimension"]]
        observed = [
            float(fit["explained_variance_ratio"][:2].sum()),
            float(fit["explained_variance_ratio"][:3].sum()),
            report["effective_dimension"],
        ]
        match = bool(
            np.allclose(expected, observed, atol=1e-10, rtol=1e-10)
            and report["retained_rank"] == row["d90"]
        )
        comparisons.append(
            {
                "group": row["group"],
                "model": row["model_id"],
                "representation": row["representation"],
                "matched": match,
                "maximum_abs_error": float(np.max(np.abs(np.asarray(expected) - observed))),
            }
        )
    cycle = root / "latent_transfer_006/analysis/position"
    for name in ("family_values.npz", "family_bootstrap_draws.npz", "condition_summaries.json"):
        inputs[str((cycle / name).relative_to(root))] = digest(cycle / name)
    with np.load(cycle / "family_values.npz", allow_pickle=False) as data:
        values, ids, strata = data["values"], data["family_ids"], data["family_strata"]
        models, conditions, metrics = (
            data["model_ids"],
            data["condition_names"],
            data["metric_names"],
        )
    with np.load(cycle / "family_bootstrap_draws.npz", allow_pickle=False) as draws:
        bootstrap = make_bootstrap(ids, strata=strata, indices=draws["all"])
    expected = json.loads((cycle / "condition_summaries.json").read_text())["models"]
    estimates, differences = 0, []
    for m, model in enumerate(models):
        for c, condition in enumerate(conditions):
            result = bootstrap.estimate(values[m, c])
            reference = expected[str(model)]["conditions"][str(condition)]["estimates"]["all"]
            for index, metric in enumerate(metrics):
                estimates += 1
                equal = (
                    result["mean"][index] == reference[str(metric)]["mean"]
                    and [result["ci95"][0][index], result["ci95"][1][index]]
                    == reference[str(metric)]["ci95"]
                )
                if not equal:
                    differences.append(
                        {"model": str(model), "condition": str(condition), "metric": str(metric)}
                    )
    return {
        "schema": "trainlab.latent-archive-regression.v1",
        "atlas_views": comparisons,
        "atlas_views_matched": sum(row["matched"] for row in comparisons),
        "position_estimates_checked": estimates,
        "position_mismatches": differences,
        "source_artifact_sha256": inputs,
        "model_forwards": 0,
        "training_updates": 0,
        "scientific_qualification": "NOT_QUALIFIED",
        "passed": all(row["matched"] for row in comparisons) and not differences,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise LabError("archive regression output must be new")
    result = check(args.archive_root)
    write_json(args.output, result)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "atlas_views_matched",
                    "position_estimates_checked",
                    "position_mismatches",
                    "passed",
                )
            },
            indent=2,
        )
    )
    return int(not result["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
