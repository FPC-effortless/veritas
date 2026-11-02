"""CLI: python -m forge_data {release,verify,validate-evidence}."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import ForgeError, release, verify_release
from .evidence_receipt import validate_evidence_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Forge: provenance-preserving temporal dataset releases"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("release", help="Validate and freeze a JSONL source")
    build.add_argument("--input", required=True, type=Path)
    build.add_argument("--spec", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    check = commands.add_parser("verify", help="Verify immutable hashes and leakage groups")
    check.add_argument("--release", required=True, type=Path)
    evidence = commands.add_parser(
        "validate-evidence", help="Validate untrusted TrainLab receipt (never qualify)"
    )
    evidence.add_argument("--input", required=True, type=Path)
    language = commands.add_parser("language-release", help="Freeze a streaming language corpus")
    language.add_argument("--input", required=True, type=Path)
    language.add_argument("--spec", required=True, type=Path)
    language.add_argument("--output", required=True, type=Path)
    language_check = commands.add_parser("language-verify", help="Verify a pinned language release")
    language_check.add_argument("--release", required=True, type=Path)
    language_check.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "release":
            result = release(args.input, args.spec, args.output)
        elif args.command == "verify":
            result = verify_release(args.release)
        elif args.command == "language-release":
            from .language import build_release

            result = {
                "manifest_sha256": build_release(
                    args.input, json.loads(args.spec.read_bytes()), args.output
                )
            }
        elif args.command == "language-verify":
            from .language import LanguageRelease

            result = {"valid": LanguageRelease(args.release, args.manifest_sha256).verify()}
        else:
            result = validate_evidence_file(args.input)
    except (ForgeError, OSError, ValueError) as exc:
        parser.exit(2, f"forge error: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
