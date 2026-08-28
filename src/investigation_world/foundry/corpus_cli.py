from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import typer

from investigation_world.foundry.document_depth_corpus import (
    load_document_depth_plan,
    materialize_document_depth_case,
)
from investigation_world.foundry.public_investigation_corpus import (
    StructuredCorpusWriteResult,
    compile_structured_investigation_corpus,
    load_structured_source_profile,
    write_structured_investigation_corpus,
)
from investigation_world.foundry.public_investigation_data import write_dataset_projections
from investigation_world.foundry.public_investigation_sources import fetch_cdc_nors_csv
from investigation_world.foundry.sec_litigation_discovery import discover_sec_litigation_dataset
from investigation_world.foundry.uscg_cgmix_source import (
    discover_uscg_iir_records,
    write_uscg_iir_staging,
)

app = typer.Typer(
    help=(
        "Build provenance-first high-stakes investigation corpora with explicit "
        "agent-visible and verifier-only boundaries."
    )
)


def _resolve_date(value: str | None) -> date:
    if value is None:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("date values must use YYYY-MM-DD") from exc


def _public_structured_result(result: StructuredCorpusWriteResult) -> dict[str, object]:
    return {
        "dataset_id": result.dataset_id,
        "cases": result.cases,
        "public_output": result.public_output,
        "manifest_output": result.manifest_output,
        "public_hash": result.public_hash,
        "sealed_materialized": True,
    }


@app.command("compile-structured")
def compile_structured_cmd(
    profile: Path,
    input_path: Path,
    dataset_id: str,
    version: str,
    as_of: str | None = None,
    output_root: Path = Path("investigation_corpus"),
) -> None:
    """Compile a local CSV/JSON/JSONL/XLSX source through a fail-closed field policy."""

    source_profile = load_structured_source_profile(profile)
    corpus = compile_structured_investigation_corpus(
        source_profile,
        input_path,
        dataset_id=dataset_id,
        version=version,
        as_of=_resolve_date(as_of),
    )
    result = write_structured_investigation_corpus(
        corpus,
        source_profile,
        public_output=output_root / "public.jsonl",
        verifier_output=output_root / "sealed" / "verifier.jsonl",
        manifest_output=output_root / "manifest.json",
    )
    typer.echo(json.dumps(_public_structured_result(result), indent=2))


@app.command("materialize-document-depth")
def materialize_document_depth_cmd(
    plan: Path,
    source_pdf: Path,
    public_root: Path = Path("investigation_corpus/document/public"),
    verifier_root: Path | None = None,
    max_bytes: int = 256 * 1024 * 1024,
    max_pages: int = 1000,
) -> None:
    """Physically split one approved investigation PDF into public and sealed page sets."""

    depth_plan = load_document_depth_plan(plan)
    result = materialize_document_depth_case(
        depth_plan,
        source_pdf,
        public_root=public_root,
        verifier_root=verifier_root,
        max_bytes=max_bytes,
        max_pages=max_pages,
    )
    typer.echo(
        json.dumps(
            {
                "plan_id": result.plan_id,
                "case_id": result.public_case_id,
                "source_id": result.source_id,
                "source_page_count": result.source_page_count,
                "public_slices": len(result.public_slices),
                "ignored_page_count": result.ignored_page_count,
                "public_manifest": result.public_manifest,
                "sealed_materialized": verifier_root is not None,
            },
            indent=2,
        )
    )


@app.command("acquire-cdc-nors")
def acquire_cdc_nors_cmd(
    profile: Path = Path("datasets/public_investigations/profiles/cdc_nors_v1.json"),
    as_of: str | None = None,
    output_root: Path = Path("investigation_corpus/cdc_nors"),
    timeout_seconds: float = 60.0,
    max_bytes: int = 256 * 1024 * 1024,
) -> None:
    """Fetch CDC NORS privately, then emit separated public and verifier corpora."""

    resolved_date = _resolve_date(as_of)
    source_profile = load_structured_source_profile(profile)
    if source_profile.source_id != "cdc_nors":
        raise typer.BadParameter("profile must target source_id=cdc_nors")

    with tempfile.TemporaryDirectory(prefix="veritas-nors-") as temporary_directory:
        raw_path = Path(temporary_directory) / "nors.csv"
        source_result = fetch_cdc_nors_csv(
            raw_path,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
        )
        corpus = compile_structured_investigation_corpus(
            source_profile,
            raw_path,
            dataset_id=f"cdc-nors-{resolved_date.isoformat()}",
            version=resolved_date.strftime("%Y.%m.%d"),
            as_of=resolved_date,
        )
        result = write_structured_investigation_corpus(
            corpus,
            source_profile,
            public_output=output_root / "public.jsonl",
            verifier_output=output_root / "sealed" / "verifier.jsonl",
            manifest_output=output_root / "manifest.json",
        )

    typer.echo(
        json.dumps(
            {
                **_public_structured_result(result),
                "source_byte_count": source_result["byte_count"],
                "source_sha256": source_result["sha256"],
                "raw_source_retained": False,
            },
            indent=2,
        )
    )


@app.command("acquire-uscg-iir")
def acquire_uscg_iir_cmd(
    profile: Path = Path("datasets/public_investigations/profiles/uscg_cgmix_iir_v1.json"),
    as_of: str | None = None,
    output_root: Path = Path("investigation_corpus/uscg_cgmix"),
    activity_id: int = 0,
    vessel_service: str = "",
    vessel_name: str = "",
    organization_name: str = "",
    involved_facility: str = "",
    keyword: str = "",
    maximum_cases: int = 25,
    timeout_seconds: float = 30.0,
) -> None:
    """Build a scoped, evidence-rich USCG IIR corpus through the sealed field policy."""

    resolved_date = _resolve_date(as_of)
    source_profile = load_structured_source_profile(profile)
    if source_profile.source_id != "uscg_cgmix":
        raise typer.BadParameter("profile must target source_id=uscg_cgmix")

    records = discover_uscg_iir_records(
        activity_id=activity_id,
        vessel_service=vessel_service,
        vessel_name=vessel_name,
        organization_name=organization_name,
        involved_facility=involved_facility,
        keyword=keyword,
        maximum_cases=maximum_cases,
        timeout_seconds=timeout_seconds,
    )
    with tempfile.TemporaryDirectory(prefix="veritas-uscg-") as temporary_directory:
        raw_path = Path(temporary_directory) / "uscg.json"
        write_uscg_iir_staging(records, raw_path)
        corpus = compile_structured_investigation_corpus(
            source_profile,
            raw_path,
            dataset_id=f"uscg-cgmix-{resolved_date.isoformat()}",
            version=resolved_date.strftime("%Y.%m.%d"),
            as_of=resolved_date,
        )
        result = write_structured_investigation_corpus(
            corpus,
            source_profile,
            public_output=output_root / "public.jsonl",
            verifier_output=output_root / "sealed" / "verifier.jsonl",
            manifest_output=output_root / "manifest.json",
        )

    typer.echo(
        json.dumps(
            {
                **_public_structured_result(result),
                "raw_source_retained": False,
                "source": "USCG CGMIX IIR XML web service",
            },
            indent=2,
        )
    )


@app.command("discover-sec-litigation")
def discover_sec_litigation_cmd(
    as_of: str | None = None,
    max_pages: int = 200,
    maximum_cases: int | None = None,
    delay_seconds: float = 0.15,
    public_output: Path = Path("investigation_corpus/sec_litigation/public.json"),
    verifier_output: Path | None = None,
) -> None:
    """Discover SEC complaint/disposition pairs without exposing outcome documents."""

    resolved_date = _resolve_date(as_of)
    dataset = discover_sec_litigation_dataset(
        as_of=resolved_date,
        max_pages=max_pages,
        maximum_cases=maximum_cases,
        delay_seconds=delay_seconds,
    )
    result = write_dataset_projections(
        dataset,
        public_output=public_output,
        verifier_output=verifier_output,
    )
    typer.echo(
        json.dumps(
            {
                "dataset_id": result["dataset_id"],
                "public_output": result["public_output"],
                "public_hash": result["public_hash"],
                "sealed_materialized": result["verifier_output"] is not None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
