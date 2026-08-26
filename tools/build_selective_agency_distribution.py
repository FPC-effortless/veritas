from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigation_world.foundry import (
    SelectiveAgencyDistributionConfig,
    compile_selective_agency_distribution,
    validate_selective_agency_distribution,
    write_selective_agency_distribution,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a procedural Veritas Selective Agency taskset and private oracle bundle."
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--train", type=int, default=96)
    parser.add_argument("--iid-test", type=int, default=48)
    parser.add_argument("--ood", type=int, default=48)
    parser.add_argument("--adversarial", type=int, default=48)
    parser.add_argument(
        "--public-output",
        type=Path,
        default=Path("selective_agency_public.json"),
    )
    parser.add_argument(
        "--oracle-output",
        type=Path,
        default=Path("selective_agency_private_oracles.json"),
    )
    args = parser.parse_args()

    config = SelectiveAgencyDistributionConfig(
        seed=args.seed,
        train_count=args.train,
        iid_test_count=args.iid_test,
        ood_count=args.ood,
        adversarial_count=args.adversarial,
    )
    bundle = compile_selective_agency_distribution(config)
    report = validate_selective_agency_distribution(bundle)
    write_selective_agency_distribution(
        bundle,
        public_path=args.public_output,
        oracle_path=args.oracle_output,
    )

    print(
        json.dumps(
            {
                "passed": report.passed,
                "tasks": report.total_tasks,
                "splits": report.split_counts,
                "decisions": report.decision_counts,
                "task_classes": report.task_class_counts,
                "contrast_groups": report.contrast_groups,
                "errors": report.errors,
                "warnings": report.warnings,
                "public_output": str(args.public_output),
                "oracle_output": str(args.oracle_output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
