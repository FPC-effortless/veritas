from __future__ import annotations

import json
from pathlib import Path

from investigation_world.foundry import (
    CalibrationDataset,
    CalibrationIngestionPlan,
    CalibrationStatistic,
    DistributionFitRule,
    DistributionSplit,
    ExternalInvestigationBuildPlan,
    ExternalInvestigationWorldSpec,
    fit_calibration_plan,
)
from investigation_world.foundry.cli import compile_external_foundry_cmd
from investigation_world.world.generator import WorldGenerationConfig


def test_compile_cli_accepts_fitted_calibration_and_bindings(tmp_path: Path) -> None:
    dataset = tmp_path / "organizations.csv"
    dataset.write_text("employees\n10\n20\n30\n", encoding="utf-8")
    fitted = fit_calibration_plan(
        CalibrationIngestionPlan(
            calibration_id="cli-calibration-v1",
            domain="organizations",
            datasets=[
                CalibrationDataset(
                    source_id="organizations",
                    path=dataset,
                    name="organization scale",
                )
            ],
            distribution_rules=[
                DistributionFitRule(
                    target_id="mean-employees",
                    source_id="organizations",
                    object_type="organization",
                    attribute="employees",
                    statistic=CalibrationStatistic.MEAN,
                    column="employees",
                )
            ],
        )
    )
    calibration_path = tmp_path / "calibration_spec.json"
    calibration_path.write_text(fitted.spec.model_dump_json(indent=2), encoding="utf-8")
    bindings_path = tmp_path / "bindings.json"
    bindings_path.write_text(
        json.dumps(
            {
                "bindings": [
                    {
                        "target_id": "mean-employees",
                        "parameter": "num_people",
                        "minimum": 5,
                        "maximum": 100,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    plan = ExternalInvestigationBuildPlan(
        worlds=[
            ExternalInvestigationWorldSpec(
                split=DistributionSplit.TRAIN,
                world_seed=9901,
                evidence_seed=9902,
                task_seed=9903,
                task_count=1,
                config=WorldGenerationConfig(
                    num_people=8,
                    num_organizations=6,
                    num_addresses=6,
                    relationship_density=0.10,
                    alias_rate=0.20,
                    rename_rate=0.10,
                    ownership_chain_depth=2,
                ),
            )
        ]
    )
    plan_path = tmp_path / "build_plan.json"
    plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    public_output = tmp_path / "public.json"
    private_output = tmp_path / "private.json"

    compile_external_foundry_cmd(
        output=public_output,
        private_output=private_output,
        plan=plan_path,
        calibration=calibration_path,
        bindings=bindings_path,
        tasks_per_split=1,
    )

    public = json.loads(public_output.read_text(encoding="utf-8"))
    assert public["episode_count"] == 1
    assert public["worlds"][0]["config"]["num_people"] == 20
    assert public["worlds"][0]["calibration_fingerprint"]
    assert private_output.exists()
