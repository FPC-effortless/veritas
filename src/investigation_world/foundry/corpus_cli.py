from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import typer

from investigation_world.foundry.public_investigation_corpus import (
    compile_structured_investigation_corpus,
    load_structured_source_profile,
    write_structured_investigation_corpus,
)
from investigation_world.foundry.public_investigation_data import write_dataset_projections
from investigation_world.foundry.public_investigation_sources import fetch_cdc_nors_csv
from investigation_world.foundry.sec_litigation_discovery import discover_sec_litigation_dataset

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
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))


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
                **result.model_dump(mode="json"),
                "source_byte_count": source_result["byte_count"],
                "source_sha256": source_result["sha256"],
                "raw_source_retained": False,
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
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
