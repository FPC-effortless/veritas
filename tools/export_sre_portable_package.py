from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigation_world.commercial.sre_release import load_sealed_sre_release
from investigation_world.portability.hud import build_hud_sre_package
from investigation_world.portability.models import PortableVisibility
from investigation_world.portability.prime import build_prime_sre_package
from investigation_world.portability.sre import build_sre_portable_manifest
from investigation_world.portability.sre_private import build_sre_private_portable_tasks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export the exact sealed Veritas SRE private panel as a HUD or Prime package"
    )
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--adapter", choices=("hud", "prime", "both"), default="both")
    parser.add_argument("--source-bundle-sha256")
    parser.add_argument("--expected-candidate-id")
    parser.add_argument("--expected-evidence-manifest-id")
    parser.add_argument("--expected-report-id")
    parser.add_argument("--expected-panel-id")
    parser.add_argument("--expected-private-release-manifest-id")
    args = parser.parse_args()

    identity_kwargs = {
        "expected_candidate_id": args.expected_candidate_id,
        "expected_evidence_manifest_id": args.expected_evidence_manifest_id,
        "expected_report_id": args.expected_report_id,
        "expected_panel_id": args.expected_panel_id,
        "expected_private_release_manifest_id": args.expected_private_release_manifest_id,
    }
    release = load_sealed_sre_release(args.qualification, **identity_kwargs)
    manifest = build_sre_portable_manifest(
        args.qualification,
        visibility=PortableVisibility.BUYER_SAFE,
        public_sample_limit=8,
        source_bundle_sha256=args.source_bundle_sha256,
        **identity_kwargs,
    )
    private_tasks = build_sre_private_portable_tasks(release)

    results = []
    if args.adapter in {"hud", "both"}:
        results.append(
            build_hud_sre_package(
                args.output / "hud",
                manifest=manifest,
                private_tasks=private_tasks,
            )
        )
    if args.adapter in {"prime", "both"}:
        results.append(
            build_prime_sre_package(
                args.output / "prime",
                manifest=manifest,
                private_tasks=private_tasks,
            )
        )

    print(
        json.dumps(
            [result.model_dump(mode="json") for result in results],
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
