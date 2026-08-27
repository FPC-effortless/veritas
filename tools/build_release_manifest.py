from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build buyer-facing Veritas release provenance")
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run", required=True)
    parser.add_argument("--container-image", required=True)
    parser.add_argument("--container-digest", required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
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
        },
        "sbom": {
            "format": "CycloneDX JSON",
            "name": args.sbom.name,
            "sha256": _sha256(args.sbom),
            "bytes": args.sbom.stat().st_size,
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
