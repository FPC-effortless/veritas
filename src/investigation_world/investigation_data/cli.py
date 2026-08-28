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
from .corpus import (
    corpus_digest,
    load_fusion_corpus,
    validate_fusion_corpus_sources,
)
from .fusion import FusionManifest, fuse_manifest, manifest_digest
from .models import ArtifactReceipt, DocumentPreparationPlan
from .preparation import (
    PreparationError,
    prepare_document_artifact,
    prepare_zip_artifact,
)
from .serialization import canonical_json_bytes, write_episode_bundle

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


@app.command("prepare-document")
def prepare_document_cmd(
    receipt: Path,
    plan: Path,
    acquisition_root: Path = Path(".veritas-data"),
    output: Path = Path(".veritas-prepared"),
    oracle_output: Path | None = None,
    catalog: Path | None = None,
    max_bytes: int = 512 * 1024 * 1024,
) -> None:
    """Split a receipt-verified PDF into public pages and an optional sealed oracle output."""
    try:
        loaded_plan = DocumentPreparationPlan.model_validate_json(
            plan.read_text(encoding="utf-8")
        )
        result = prepare_document_artifact(
            receipt,
            acquisition_root,
            output,
            loaded_plan,
            oracle_root=oracle_output,
            catalog=load_catalog(catalog),
            max_bytes=max_bytes,
        )
    except (OSError, PreparationError, AcquisitionError, KeyError, ValueError) as exc:
        typer.echo(f"document preparation refused: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(
        json.dumps(
            {
                "prepared": True,
                "plan_id": result.plan_id,
                "source_sha256": result.source_sha256,
                "public_manifest": result.public_manifest,
                "public_slices": len(result.public_slices),
                "oracle_materialized": result.oracle_manifest is not None,
                "ignored_page_count": result.ignored_page_count,
            },
            indent=2,
        )
    )


@app.command("validate-fusion-corpus")
def validate_fusion_corpus(
    index: Path,
    catalog: Path | None = None,
) -> None:
    try:
        loaded = load_fusion_corpus(index)
        validate_fusion_corpus_sources(loaded, load_catalog(catalog))
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(f"fusion corpus validation refused: {exc}", err=True)
        raise typer.Exit(2) from exc

    phases = {
        phase: sum(
            release.phase == phase
            for case in loaded.cases
            for release in case.evidence_releases
        )
        for phase in ("pre_final", "final", "post_final")
    }
    typer.echo(
        json.dumps(
            {
                "valid": True,
                "corpus_id": loaded.corpus_id,
                "source_id": loaded.source_id,
                "cases": len(loaded.cases),
                "evidence_releases": sum(
                    len(case.evidence_releases) for case in loaded.cases
                ),
                "phases": phases,
                "date_only_availability_policy": loaded.date_only_availability_policy,
                "sha256": corpus_digest(loaded),
            },
            indent=2,
        )
    )


@app.command("validate-fusion")
def validate_fusion(
    manifest: Path,
    catalog: Path | None = None,
) -> None:
    try:
        loaded = FusionManifest.model_validate_json(manifest.read_text(encoding="utf-8"))
        result = fuse_manifest(loaded, load_catalog(catalog))
    except (OSError, ValueError) as exc:
        typer.echo(f"fusion validation refused: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(
        json.dumps(
            {
                "valid": True,
                "episode_id": loaded.episode_id,
                "fragments": len(loaded.fragments),
                "relations": len(loaded.relations),
                "manifest_sha256": manifest_digest(loaded),
                "catalog_sha256": result.report.catalog_sha256,
            },
            indent=2,
        )
    )


@app.command("fuse")
def fuse(
    manifest: Path,
    output: Path = Path(".veritas-fused"),
    catalog: Path | None = None,
) -> None:
    try:
        loaded = FusionManifest.model_validate_json(manifest.read_text(encoding="utf-8"))
        result = fuse_manifest(loaded, load_catalog(catalog))
        episode_dir = output / loaded.episode_id
        public_path = episode_dir / "public.json"
        oracle_path = episode_dir / "oracle.json"
        report_path = episode_dir / "fusion_report.json"
        hashes = write_episode_bundle(result.bundle, public_path, oracle_path)
        report_payload = result.report.model_dump(mode="json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_bytes(canonical_json_bytes(report_payload) + b"\n")
    except (OSError, ValueError) as exc:
        typer.echo(f"fusion refused: {exc}", err=True)
        raise typer.Exit(2) from exc

    typer.echo(
        json.dumps(
            {
                "fused": True,
                "episode_id": loaded.episode_id,
                "public": str(public_path),
                "oracle": str(oracle_path),
                "report": str(report_path),
                **hashes,
            },
            indent=2,
        )
    )
