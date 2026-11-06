"""Narrow source/compute adapters; no remote credentials or publication authority."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from trainlab.runner import contained_file, digest, read_json, verify_run, write_json

from .core import LabError, identity, name
from .evidence import link, put_node, retrieve


def import_trainlab(lab, directory):
    directory = Path(directory).resolve()
    if not verify_run(directory)["valid"]:
        raise LabError("TrainLab receipt integrity failed")
    record = read_json(contained_file(directory, "run.json"))
    return put_node(
        lab,
        "trainlab." + record["id"],
        "evidence",
        {
            "source": "TrainLab",
            "run": record,
            "receipt_sha256": digest(directory / "run.json"),
            "status": "RECORDED_FILE_INTEGRITY_ONLY",
            "scientific_qualification": "NOT_QUALIFIED",
        },
    )


def import_forge(lab, directory, manifest_sha256):
    try:
        from forge_data.dataset import Dataset
    except ImportError as exc:
        raise LabError("install the sibling Forge package for dataset validation") from exc
    dataset = Dataset(Path(directory), manifest_sha256=manifest_sha256)
    manifest = read_json(Path(directory) / "manifest.json")
    return put_node(
        lab,
        "forge." + manifest_sha256[:24],
        "evidence",
        {
            "source": "Forge",
            "manifest": manifest,
            "manifest_sha256": manifest_sha256,
            "status": "SCHEMA_AND_SPLIT_INTEGRITY_ONLY",
            "scientific_qualification": "NOT_QUALIFIED",
            "reader": type(dataset).__name__,
        },
    )


def woyengi_handoff(lab, destination):
    """A proposal envelope for a separately authenticated Woyengi host to review."""
    destination = Path(destination)
    if destination.exists():
        raise LabError("handoff destination must be new")
    write_json(
        destination,
        {
            "schema": "research_lab.woyengi_handoff.v1",
            "knowledge": retrieve(lab),
            "created_at": time.time(),
            "authority": "UNVERIFIED_CLAIM_PROPOSALS_ONLY",
            "ingestion": "NOT_PERFORMED",
            "source_rights": "NOT_ATTESTED",
        },
    )
    return {"path": str(destination), "sha256": digest(destination), "ingestion": "NOT_PERFORMED"}


def compute_observation():
    observation = {
        "at": time.time(),
        "host_cpus": os.cpu_count(),
        "host_load": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        "gpu_utilization": None,
        "gpu_observation": "UNAVAILABLE",
    }
    executable = shutil.which("nvidia-smi")
    if executable:
        try:
            result = subprocess.run(
                [
                    executable,
                    "--query-gpu=index,utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
            rows = [
                [float(v.strip()) for v in line.split(",")] for line in result.stdout.splitlines()
            ]
            if not all(len(row) == 4 for row in rows):
                raise ValueError("unexpected GPU observation")
            observation.update(gpu_utilization=rows, gpu_observation="LOCAL_NVIDIA_SMI")
        except (OSError, ValueError, subprocess.SubprocessError):
            observation["gpu_observation"] = "PROBE_FAILED"
    return observation


def import_catalog(lab, path):
    catalog = read_json(Path(path))
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"schema", "papers"}
        or catalog["schema"] != "research_lab.literature.v1"
    ):
        raise LabError("unsupported literature catalog")
    if not isinstance(catalog["papers"], list) or len(catalog["papers"]) > 200:
        raise LabError("bounded literature catalog required")
    pins = []
    catalog_pin = digest(Path(path))
    catalog_id = "catalog." + catalog_pin[:24]
    put_node(
        lab,
        catalog_id,
        "evidence",
        {
            "sha256": catalog_pin,
            "catalog": catalog,
            "trust": "RETRIEVED_METADATA_NOT_SCIENTIFIC_TRUTH",
        },
    )
    for paper in catalog["papers"]:
        if not isinstance(paper, dict) or not {
            "id",
            "title",
            "url",
            "retrieved_at",
            "summary",
            "relevance",
            "limitations",
        } <= set(paper):
            raise LabError("paper requires source, retrieval time, relevance and limitations")
        name(paper["id"])
        if not isinstance(paper["url"], str) or not paper["url"].startswith("https://"):
            raise LabError("paper source must be an HTTPS URI")
        node_id = "paper." + paper["id"][:36] + "." + identity(paper)[:20]
        pins.append(
            put_node(
                lab,
                node_id,
                "paper",
                {
                    **paper,
                    "trust": "RETRIEVED_METADATA_AND_RESEARCHER_SUMMARY",
                    "novelty": "NOT_ESTABLISHED",
                },
            )
        )
        link(lab, node_id, "derived_from", catalog_id)
    return {"papers": len(pins), "pins": pins, "novelty": "NOT_ESTABLISHED"}
