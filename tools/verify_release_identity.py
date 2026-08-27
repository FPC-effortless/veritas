from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def _require(pattern: str, text: str, *, label: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        raise RuntimeError(f"could not resolve {label}")
    return match.group(1)


def main() -> None:
    version = _project_version()
    tag = f"v{version}"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    build_status = (ROOT / "BUILD_STATUS.md").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    readme_version = _require(
        r"^> Software version: ([0-9]+\.[0-9]+\.[0-9]+)\s{2}$",
        readme,
        label="README software version",
    )
    readme_tag = _require(r"^> Release tag: (v[^\s]+)\s{2}$", readme, label="README release tag")
    build_version = _require(
        r"^Current software version: \*\*([^*]+)\*\*\.$",
        build_status,
        label="BUILD_STATUS software version",
    )
    build_tag = _require(
        r"^Canonical release tag: \*\*([^*]+)\*\*\.$",
        build_status,
        label="BUILD_STATUS release tag",
    )

    expected = {
        "pyproject": version,
        "README": readme_version,
        "BUILD_STATUS": build_version,
    }
    if set(expected.values()) != {version}:
        raise RuntimeError(f"release version mismatch: {expected}")
    if readme_tag != tag or build_tag != tag:
        raise RuntimeError(
            f"release tag mismatch: expected {tag}, README={readme_tag}, BUILD_STATUS={build_tag}"
        )

    if 'license = {file = "LICENSE"}' not in pyproject:
        raise RuntimeError("pyproject.toml must package the root LICENSE")

    license_path = ROOT / "LICENSE"
    if not license_path.exists():
        raise RuntimeError("root LICENSE is missing")
    license_text = license_path.read_text(encoding="utf-8")
    if "Apache License" not in license_text or "Version 2.0" not in license_text:
        raise RuntimeError("root LICENSE is not Apache-2.0")

    licensing = (ROOT / "LICENSING.md").read_text(encoding="utf-8")
    required_licensing_terms = (
        "Apache License 2.0",
        "Veritas Commercial Restricted Assets",
        "Customer evaluation outputs",
        "Generated training data",
    )
    missing = [term for term in required_licensing_terms if term not in licensing]
    if missing:
        raise RuntimeError(f"LICENSING.md is missing required policy sections: {missing}")

    release_dir = ROOT / "release" / version
    identity_path = release_dir / "PORTABILITY_IDENTITIES.json"
    notes_path = release_dir / "RELEASE_NOTES.md"
    if not identity_path.exists() or not notes_path.exists():
        raise RuntimeError(f"release/{version} must contain portability identities and release notes")

    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if identity.get("veritas_version") != version:
        raise RuntimeError("PORTABILITY_IDENTITIES veritas_version does not match package version")
    if identity.get("release_tag") != tag:
        raise RuntimeError("PORTABILITY_IDENTITIES release_tag does not match package version")

    required_ids = (
        "portable_manifest_id",
        "portable_qualification_evidence_id",
        "hud_package_id",
        "prime_package_id",
    )
    missing_ids = [key for key in required_ids if not identity.get(key)]
    if missing_ids:
        raise RuntimeError(f"PORTABILITY_IDENTITIES is missing immutable IDs: {missing_ids}")

    # The public portability schema and both generated adapter distributions are part of the
    # software 0.11 contract. These literals are intentionally checked from source so a future
    # version bump cannot silently leave buyer-facing generated packages behind.
    models_source = (ROOT / "src/investigation_world/portability/models.py").read_text(encoding="utf-8")
    hud_source = (ROOT / "src/investigation_world/portability/hud.py").read_text(encoding="utf-8")
    prime_source = (ROOT / "src/investigation_world/portability/prime.py").read_text(encoding="utf-8")
    expected_literal = f'version = "{version}"'
    if f'schema_version: str = "{version}"' not in models_source:
        raise RuntimeError("portable manifest schema_version does not match software version")
    if expected_literal not in hud_source:
        raise RuntimeError("generated HUD package version does not match software version")
    if expected_literal not in prime_source:
        raise RuntimeError("generated Prime package version does not match software version")

    print(
        json.dumps(
            {
                "status": "release_identity_consistent",
                "version": version,
                "tag": tag,
                "license": "Apache-2.0",
                "portability_manifest_id": identity["portable_manifest_id"],
                "hud_package_id": identity["hud_package_id"],
                "prime_package_id": identity["prime_package_id"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
