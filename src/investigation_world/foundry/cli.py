from __future__ import annotations

import json
from pathlib import Path

import typer

from investigation_world.foundry.calibration_ingestion import (
    CalibrationIngestionPlan,
    fit_calibration_plan,
)
from investigation_world.foundry.capability_families import (
    external_investigation_capability_contract,
)
from investigation_world.foundry.expert_trajectories import DemonstrationSet
from investigation_world.foundry.external_distribution import (
    CalibrationBinding,
    ExternalInvestigationBuildPlan,
    default_external_investigation_build_plan,
    load_external_investigation_distribution,
    materialize_external_investigation_build_plan,
    write_external_investigation_distribution,
)
from investigation_world.foundry.models import stable_hash
from investigation_world.foundry.public_investigation_data import (
    load_public_investigation_dataset,
    write_dataset_projections,
)
from investigation_world.foundry.training_adapters import trainer_adapter_for
from investigation_world.foundry.training_corpus import (
    generate_training_demonstration_set,
)
from investigation_world.foundry.training_product import (
    TrainerKind,
    TrainingRecipe,
    TrainingRunManifest,
    compile_training_bundle,
)
from investigation_world.foundry.world_calibration import WorldCalibrationSpec


app = typer.Typer(
    help=(
        "Operational Veritas Capability Foundry: calibrate worlds, compile "
        "distributions, generate verified trajectories, and export training artifacts."
    )
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _load_calibration_bindings(path: Path) -> list[CalibrationBinding]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("bindings")
    if not isinstance(payload, list):
        raise typer.BadParameter(
            "calibration bindings must be a JSON list or an object with a 'bindings' list"
        )
    return [CalibrationBinding.model_validate(item) for item in payload]


@app.command("fit-calibration")
def fit_calibration_cmd(
    plan: Path,
    output: Path = Path("calibration_spec.json"),
    profile_output: Path | None = None,
):
    """Fit a WorldCalibrationSpec from mounted CSV/JSON/JSONL/Parquet datasets."""
    ingestion_plan = CalibrationIngestionPlan.model_validate_json(
        plan.read_text(encoding="utf-8")
    )
    result = fit_calibration_plan(ingestion_plan)
    _write_json(output, result.spec)
    if profile_output is not None:
        _write_json(
            profile_output,
            {
                "profiles": {
                    source_id: profile.model_dump(mode="json")
                    for source_id, profile in result.profiles.items()
                },
                "warnings": result.warnings,
                "plan_hash": result.plan_hash,
            },
        )
    typer.echo(
        json.dumps(
            {
                "calibration_id": result.spec.calibration_id,
                "sources": len(result.spec.sources),
                "distribution_targets": len(result.spec.distribution_targets),
                "dependency_targets": len(result.spec.dependency_targets),
                "warnings": result.warnings,
                "output": str(output),
            },
            indent=2,
        )
    )


@app.command("prepare-public-investigations")
def prepare_public_investigations_cmd(
    manifest: Path,
    public_output: Path = Path("public_investigations.json"),
    verifier_output: Path | None = None,
):
    """Validate a public-investigation manifest and emit separated projections."""
    dataset = load_public_investigation_dataset(manifest)
    result = write_dataset_projections(
        dataset,
        public_output=public_output,
        verifier_output=verifier_output,
    )
    typer.echo(json.dumps(result, indent=2))


@app.command("compile-external-foundry")
def compile_external_foundry_cmd(
    output: Path = Path("external_foundry.json"),
    private_output: Path | None = None,
    plan: Path | None = None,
    calibration: Path | None = None,
    bindings: Path | None = None,
    tasks_per_split: int = 48,
):
    """Compile disjoint train/IID/OOD/adversarial External Investigation worlds.

    `fit-calibration` output can be supplied directly with `--calibration`. Optional
    `--bindings` maps fitted numeric targets to generator/evidence parameters. A custom
    build plan may still embed calibration and bindings itself; explicit CLI inputs
    override the corresponding plan fields.
    """
    if plan is None:
        build_plan = default_external_investigation_build_plan(
            tasks_per_split=tasks_per_split
        )
    else:
        build_plan = ExternalInvestigationBuildPlan.model_validate_json(
            plan.read_text(encoding="utf-8")
        )

    updates = {}
    if calibration is not None:
        updates["calibration_spec"] = WorldCalibrationSpec.model_validate_json(
            calibration.read_text(encoding="utf-8")
        )
    if bindings is not None:
        updates["calibration_bindings"] = _load_calibration_bindings(bindings)
    if updates:
        build_plan = ExternalInvestigationBuildPlan.model_validate(
            build_plan.model_copy(update=updates).model_dump(mode="json")
        )

    distribution = materialize_external_investigation_build_plan(build_plan)
    result = write_external_investigation_distribution(
        distribution,
        output,
        private_output=private_output,
    )
    result["calibrated"] = build_plan.calibration_spec is not None
    result["calibration_id"] = (
        build_plan.calibration_spec.calibration_id
        if build_plan.calibration_spec is not None
        else None
    )
    result["calibration_bindings"] = len(build_plan.calibration_bindings)
    typer.echo(json.dumps(result, indent=2))


@app.command("generate-external-demos")
def generate_external_demos_cmd(
    private_distribution: Path,
    output: Path = Path("external_demonstrations.json"),
    maximum_episodes: int | None = None,
    expert_threshold: float = 0.8,
    include_counterfactuals: bool = True,
):
    """Generate verifier-qualified TRAIN demonstrations and counterfactuals.

    IID/OOD/adversarial episodes are intentionally excluded so the privileged reference
    policy cannot contaminate frozen evaluation worlds.
    """
    distribution = load_external_investigation_distribution(private_distribution)
    contract = external_investigation_capability_contract()
    demonstrations = generate_training_demonstration_set(
        distribution.episodes,
        capability_contract_id=contract.capability_id,
        expert_threshold=expert_threshold,
        include_counterfactuals=include_counterfactuals,
        maximum_episodes=maximum_episodes,
    )
    _write_json(output, demonstrations)
    expert_count = sum(
        trajectory.role.value in {"expert", "preference_chosen"}
        for trajectory in demonstrations.trajectories
    )
    typer.echo(
        json.dumps(
            {
                "dataset_id": demonstrations.dataset_id,
                "trajectories": len(demonstrations.trajectories),
                "expert_trajectories": expert_count,
                "preference_pairs": len(demonstrations.preference_pairs),
                "heldout_source_episodes_excluded": demonstrations.metadata.get(
                    "heldout_source_episodes_excluded",
                    0,
                ),
                "output": str(output),
            },
            indent=2,
        )
    )


def _trainer_selection(value: str) -> list[TrainerKind]:
    if value.casefold() == "all":
        return list(TrainerKind)
    try:
        return [TrainerKind(value.casefold())]
    except ValueError as error:
        allowed = ", ".join(["all", *(item.value for item in TrainerKind)])
        raise typer.BadParameter(f"trainer must be one of: {allowed}") from error


@app.command("export-training-artifacts")
def export_training_artifacts_cmd(
    demonstrations: Path,
    output_dir: Path = Path("training_artifacts"),
    trainer: str = "all",
    base_model: str = "unspecified",
    minimum_verifier_score: float = 0.8,
):
    """Export deterministic SFT/preference/RL/VOPSD artifacts from verified traces."""
    dataset = DemonstrationSet.model_validate_json(
        demonstrations.read_text(encoding="utf-8")
    )
    contract = external_investigation_capability_contract()
    if dataset.capability_contract_id != contract.capability_id:
        raise typer.BadParameter(
            "demonstration capability contract does not match External Investigation"
        )

    results = []
    for trainer_kind in _trainer_selection(trainer):
        recipe = TrainingRecipe(
            recipe_id=f"external-{trainer_kind.value}-v1",
            trainer=trainer_kind,
            capability_contract_id=contract.capability_id,
            minimum_verifier_score=minimum_verifier_score,
        )
        bundle = compile_training_bundle(
            contract,
            recipe,
            dataset.trajectories,
            preference_pairs=dataset.preference_pairs,
        )
        run_id = (
            "artifact-"
            + trainer_kind.value
            + "-"
            + stable_hash(
                {
                    "dataset": dataset.dataset_id,
                    "bundle": bundle.bundle_id,
                    "base_model": base_model,
                }
            )[:12]
        )
        manifest = TrainingRunManifest(
            run_id=run_id,
            bundle_id=bundle.bundle_id,
            trainer=trainer_kind,
            base_model=base_model,
            trainer_version="artifact-v1",
        )
        adapter = trainer_adapter_for(
            trainer_kind,
            output_dir,
            dataset.trajectories,
        )
        result = adapter.run(bundle, manifest)
        results.append(
            {
                "trainer": trainer_kind.value,
                "run_id": run_id,
                "artifact_ref": result.artifact_ref,
                "metrics": result.metrics,
            }
        )
    typer.echo(json.dumps({"runs": results}, indent=2))


if __name__ == "__main__":
    app()
