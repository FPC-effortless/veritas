"""CLI: python -m forge_data {release,verify}."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import ForgeError, release, verify_release


def main() -> int:
    parser = argparse.ArgumentParser(description="Forge: provenance-preserving temporal dataset releases")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("release", help="Validate and freeze a JSONL source")
    build.add_argument("--input", required=True, type=Path)
    build.add_argument("--spec", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    check = commands.add_parser("verify", help="Verify immutable hashes and leakage groups")
    check.add_argument("--release", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = (release(args.input, args.spec, args.output)
                  if args.command == "release" else verify_release(args.release))
    except (ForgeError, OSError, ValueError) as exc:
        parser.exit(2, f"forge error: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
