from __future__ import annotations

import json
from pathlib import Path

import typer

from .acquisition import (
    AcquisitionError,
    acquire_artifact,
    plan_artifact,
    verify_receipt,
)
from .catalog import catalog_digest, find_source, load_catalog
from .models import ArtifactReceipt
from .preparation import PreparationError, prepare_zip_artifact

app = typer.Typer(help="Acquire and prepare source data for Veritas investigation environments.")


@app.command("validate-catalog")
def validate_catalog(catalog: Path | None = None) -> None:
    loaded = load_catalog(catalog)
    typer.echo(
        json.dumps(
            {
                "valid": True,
                "schema_version": loaded.schema_version,
                "reviewed_at": loaded.reviewed_at.isoformat(),
                "sources": len(loaded.sources),
                "sha256": catalog_digest(catalog),
            },
            indent=2,
        )
    )


@app.command("list-sources")
def list_sources(catalog: Path | None = None) -> None:
    loaded = load_catalog(catalog)
    payload = [
        {
            "source_id": source.source_id,
            "domains": source.domains,
            "acquisition": source.rights.acquisition.value,
            "redistribution": source.rights.redistribution.value,
            "ai_use": source.rights.ai_use.value,
            "truth_strength": source.truth.strength.value,
            "artifacts": [item.artifact_id for item in source.artifacts],
            "target_episodes": sum(item.target_episodes for item in source.seed_selections),
        }
        for source in loaded.sources
    ]
    typer.echo(json.dumps(payload, indent=2))


@app.command("show-source")
def show_source(source_id: str, catalog: Path | None = None) -> None:
    source = find_source(load_catalog(catalog), source_id)
    typer.echo(source.model_dump_json(indent=2))


@app.command("plan")
def plan(
    source_id: str,
    artifact_id: str,
    catalog: Path | None = None,
    rights_review_id: str | None = None,
) -> None:
    result = plan_artifact(
        load_catalog(catalog), source_id, artifact_id, rights_review_id=rights_review_id
    )
    typer.echo(json.dumps(result.__dict__, indent=2))
    raise typer.Exit(0 if result.allowed else 2)


@app.command("acquire")
def acquire(
    source_id: str,
    artifact_id: str,
    output: Path = Path(".veritas-data"),
    catalog: Path | None = None,
    rights_review_id: str | None = None,
    identified_user_agent: str | None = typer.Option(
        None,
        envvar="VERITAS_DATA_USER_AGENT",
        help="Identified User-Agent required by sources such as SEC EDGAR.",
    ),
    max_bytes: int = 2 * 1024 * 1024 * 1024,
) -> None:
    try:
        receipt = acquire_artifact(
            load_catalog(catalog),
            source_id,
            artifact_id,
            output,
            catalog_path=catalog,
            rights_review_id=rights_review_id,
            identified_user_agent=identified_user_agent,
            max_bytes=max_bytes,
        )
    except (AcquisitionError, KeyError) as exc:
        typer.echo(f"acquisition refused: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(receipt.model_dump_json(indent=2))


@app.command("verify-receipt")
def verify_receipt_cmd(
    receipt: Path,
    root: Path = Path(".veritas-data"),
) -> None:
    loaded = ArtifactReceipt.model_validate_json(receipt.read_text(encoding="utf-8"))
    try:
        valid = verify_receipt(root, loaded)
    except AcquisitionError as exc:
        typer.echo(f"receipt verification refused: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(json.dumps({"valid": valid, "sha256": loaded.sha256}, indent=2))
    raise typer.Exit(0 if valid else 1)


@app.command("prepare-zip")
def prepare_zip_cmd(
    receipt: Path,
    acquisition_root: Path = Path(".veritas-data"),
    output: Path = Path(".veritas-prepared"),
    max_members: int = 100_000,
    max_uncompressed_bytes: int = 20 * 1024 * 1024 * 1024,
) -> None:
    try:
        manifest = prepare_zip_artifact(
            receipt,
            acquisition_root,
            output,
            max_members=max_members,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
    except (PreparationError, AcquisitionError, ValueError) as exc:
        typer.echo(f"preparation refused: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(json.dumps({"prepared": True, "manifest": str(manifest)}, indent=2))
