from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_image_evidence(
    image_id: str, source_commit: str, inspection: Path, audit: Path, sbom: Path,
) -> dict[str, Any]:
    """Bind Docker, Trivy JSON, and its converted CycloneDX inventory.

    Field contracts: Trivy v0.76 reporting and supply-chain/SBOM documentation.
    This validates a scan receipt; it does not claim scanners detect every defect.
    """
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise RuntimeError("candidate image ID must be a complete SHA256 digest")
    inspected = json.loads(inspection.read_text(encoding="utf-8"))
    if not isinstance(inspected, list) or len(inspected) != 1:
        raise RuntimeError("image inspection must identify exactly one image")
    candidate = inspected[0]
    if not isinstance(candidate, dict) or candidate.get("Id") != image_id:
        raise RuntimeError("image inspection does not match the candidate image ID")
    labels = candidate.get("Config", {}).get("Labels", {})
    if (
        not isinstance(labels, dict)
        or labels.get("org.opencontainers.image.revision") != source_commit
    ):
        raise RuntimeError("candidate image source label does not match the release source")
    report = json.loads(audit.read_text(encoding="utf-8"))
    if (
        not isinstance(report, dict) or report.get("SchemaVersion") != 2
        or report.get("ArtifactType") != "container_image"
        or report.get("Metadata", {}).get("ImageID") != image_id
    ):
        raise RuntimeError("vulnerability report does not identify the candidate image")
    results = report.get("Results")
    if not isinstance(results, list) or not results or any(
        not isinstance(row, dict) for row in results
    ):
        raise RuntimeError("image scan results are missing")
    package_count = 0
    for row in results:
        packages = row.get("Packages") or []
        vulnerabilities = row.get("Vulnerabilities") or []
        if not isinstance(packages, list) or not isinstance(vulnerabilities, list):
            raise RuntimeError("image scan package/vulnerability records are malformed")
        package_count += len(packages)
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict) or not vulnerability.get("Severity"):
                raise RuntimeError("image vulnerability severity is missing")
            if vulnerability["Severity"] in {"HIGH", "CRITICAL"}:
                raise RuntimeError("candidate image has a high or critical vulnerability")
    if not package_count:
        raise RuntimeError("image scan must include its package inventory")
    inventory = json.loads(sbom.read_text(encoding="utf-8"))
    if not isinstance(inventory, dict) or inventory.get("bomFormat") != "CycloneDX":
        raise RuntimeError("image inventory is not CycloneDX")
    component = inventory.get("metadata", {}).get("component", {})
    properties = component.get("properties", [])
    if not isinstance(properties, list) or any(not isinstance(p, dict) for p in properties):
        raise RuntimeError("image inventory properties are malformed")
    identities = [
        p.get("value") for p in properties if p.get("name") == "aquasecurity:trivy:ImageID"
    ]
    components = inventory.get("components")
    if (
        component.get("type") != "container" or identities != [image_id]
        or not isinstance(components, list) or not components
    ):
        raise RuntimeError("CycloneDX inventory does not identify the candidate image")
    return {
        "status": "passed", "image_id": image_id, "source_commit": source_commit,
        "package_records": package_count, "sbom_components": len(components),
        "inspection_sha256": _sha256(inspection), "audit_sha256": _sha256(audit),
        "sbom_sha256": _sha256(sbom),
    }


def verify_published_image(image_id: str, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict) or manifest.get("schemaVersion") != 2
        or manifest.get("config", {}).get("digest") != image_id
    ):
        raise RuntimeError("registry manifest does not identify the scanned candidate image")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build buyer-facing Veritas release provenance")
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run", required=True)
    parser.add_argument("--container-image", required=True)
    parser.add_argument("--container-digest", required=True)
    parser.add_argument("--container-image-id", required=True)
    parser.add_argument("--image-inspection", type=Path, required=True)
    parser.add_argument("--image-audit", type=Path, required=True)
    parser.add_argument("--published-manifest", type=Path, required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--release-gates", type=Path, required=True)
    parser.add_argument("--portability-identities", type=Path, required=True)
    parser.add_argument("--license", dest="license_path", type=Path, required=True)
    parser.add_argument("--licensing-policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    portability = json.loads(args.portability_identities.read_text(encoding="utf-8"))
    if portability.get("veritas_version") != args.version:
        raise RuntimeError("portability identity version does not match release version")
    if portability.get("release_tag") != args.tag:
        raise RuntimeError("portability identity tag does not match release tag")
    gates = json.loads(args.release_gates.read_text(encoding="utf-8"))
    expected_gates = {
        "schema": "veritas.release-gates.v1", "status": "passed",
        "source_commit": args.source_commit, "tag": args.tag, "repository": args.repository,
    }
    if any(gates.get(key) != value for key, value in expected_gates.items()):
        raise RuntimeError("release-gate evidence does not match this exact release source")
    image_evidence = verify_image_evidence(
        args.container_image_id, args.source_commit,
        args.image_inspection, args.image_audit, args.sbom,
    )
    verify_published_image(args.container_image_id, args.published_manifest)

    distributions = []
    for path in sorted(args.dist_dir.iterdir()):
        if not path.is_file():
            continue
        distributions.append(
            {
                "name": path.name,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    if not distributions:
        raise RuntimeError("no Python release distributions found")

    payload = {
        "schema_version": "1.0",
        "release": {
            "product": "Veritas",
            "version": args.version,
            "tag": args.tag,
            "repository": args.repository,
            "source_commit": args.source_commit,
            "workflow_run": args.workflow_run,
        },
        "python_distributions": distributions,
        "container": {
            "image": args.container_image,
            "digest": args.container_digest,
            "immutable_reference": f"{args.container_image}@{args.container_digest}",
            "scanned_image_id": args.container_image_id,
            "registry_manifest_sha256": _sha256(args.published_manifest),
        },
        "image_verification": image_evidence,
        "sbom": {
            "format": "CycloneDX JSON",
            "name": args.sbom.name,
            "sha256": _sha256(args.sbom),
            "bytes": args.sbom.stat().st_size,
        },
        "release_gates": {
            "name": args.release_gates.name,
            "sha256": _sha256(args.release_gates),
            "bytes": args.release_gates.stat().st_size,
            "workflows": gates.get("workflows"),
        },
        "licensing": {
            "public_framework": "Apache-2.0",
            "license_file_sha256": _sha256(args.license_path),
            "licensing_policy_sha256": _sha256(args.licensing_policy),
            "private_benchmark": "Veritas Commercial Restricted Assets — All Rights Reserved",
        },
        "qualification_and_portability": portability,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
