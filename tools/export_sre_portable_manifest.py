from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigation_world.portability import PortableVisibility, build_sre_portable_manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export the exact sealed Veritas SRE release as a portable environment manifest"
    )
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--visibility",
        choices=[item.value for item in PortableVisibility],
        default=PortableVisibility.BUYER_SAFE.value,
    )
    parser.add_argument("--public-sample-limit", type=int, default=8)
    parser.add_argument("--source-bundle-sha256")
    parser.add_argument("--expected-candidate-id")
    parser.add_argument("--expected-evidence-manifest-id")
    parser.add_argument("--expected-report-id")
    parser.add_argument("--expected-panel-id")
    parser.add_argument("--expected-private-release-manifest-id")
    args = parser.parse_args()

    manifest = build_sre_portable_manifest(
        args.qualification,
        visibility=PortableVisibility(args.visibility),
        public_sample_limit=args.public_sample_limit,
        source_bundle_sha256=args.source_bundle_sha256,
        expected_candidate_id=args.expected_candidate_id,
        expected_evidence_manifest_id=args.expected_evidence_manifest_id,
        expected_report_id=args.expected_report_id,
        expected_panel_id=args.expected_panel_id,
        expected_private_release_manifest_id=args.expected_private_release_manifest_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "manifest_id": manifest.manifest_id,
                "environment_id": manifest.environment_id,
                "environment_version": manifest.environment_version,
                "taskset_id": manifest.taskset.taskset_id,
                "visible_tasks": len(manifest.taskset.visible_tasks),
                "private_task_count": manifest.taskset.private_task_count,
                "visibility": manifest.visibility,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
