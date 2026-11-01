"""Constructed multi-GiB ingestion/reproducibility check, never training evidence."""

from __future__ import annotations

import argparse
import json
import resource
import shutil
import time
from pathlib import Path

from forge_data.language import LanguageRelease, build_release, canonical, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--records", type=int, default=2051)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    root = args.directory
    root.mkdir(parents=True, exist_ok=False)
    source = root / "source.jsonl"
    content = "a" * (1024 * 1024 - 512)
    start = time.perf_counter()
    with source.open("wb") as f:
        for i in range(args.records):
            f.write(
                canonical(
                    {
                        "kind": "text",
                        "source_id": "constructed-stress",
                        "group": str(i),
                        "text": content + str(i),
                    }
                )
                + b"\n"
            )
    spec = {
        "schema": "forge.language-source.v1",
        "source_sha256": digest(source),
        "split_salt": "constructed-stress",
        "sources": {
            "constructed-stress": {
                "rights_reviewed": True,
                "license": "Apache-2.0",
                "provenance": "constructed memory-bound stress fixture; not useful language text",
                "source_kind": "CONSTRUCTED",
            }
        },
    }
    hashes = []
    durations = []
    for name in ("first", "repeat"):
        before = time.perf_counter()
        pin = build_release(source, spec, root / name)
        LanguageRelease(root / name, pin)
        hashes.append(pin)
        durations.append(time.perf_counter() - before)
    report = {
        "source_kind": "CONSTRUCTED",
        "input_bytes": source.stat().st_size,
        "input_sha256": spec["source_sha256"],
        "records": args.records,
        "release_manifest_sha256": hashes,
        "identical_releases": len(set(hashes)) == 1,
        "release_seconds": durations,
        "total_seconds": time.perf_counter() - start,
        "peak_process_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "scope": "streaming release + hash verification only; excludes tokenizer/training",
        "qualification": "NOT_QUALIFIED",
    }
    if not args.keep:
        for name in ("source.jsonl", "first", "repeat"):
            p = root / name
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    (root / "report.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True, indent=2))
    return int(not report["identical_releases"])


if __name__ == "__main__":
    raise SystemExit(main())
