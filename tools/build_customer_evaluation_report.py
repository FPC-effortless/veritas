from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigation_world.commercial import build_customer_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a buyer-facing Veritas evaluation report")
    parser.add_argument("inputs", nargs="+", type=Path, help="Calibration JSON reports")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--customer-name")
    parser.add_argument("--title", default="Veritas Enterprise Agent Evaluation")
    parser.add_argument("--benchmark-version", default="CompanyWorld")
    args = parser.parse_args()

    reports = [json.loads(path.read_text()) for path in args.inputs]
    rendered = build_customer_report(
        reports,
        title=args.title,
        customer_name=args.customer_name,
        benchmark_version=args.benchmark_version,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(args.output)


if __name__ == "__main__":
    main()
