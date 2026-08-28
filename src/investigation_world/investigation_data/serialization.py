from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import InvestigationEpisodeBundle

_PRIVATE_KEYS = {
    "oracle",
    "private_truth",
    "ground_truth",
    "ground_truth_claims",
    "hidden_label",
    "actual_timeline",
    "causal_edges",
    "verifier_targets",
}


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _find_private_keys(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key.lower() in _PRIVATE_KEYS:
                findings.append(child_path)
            findings.extend(_find_private_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_find_private_keys(child, f"{path}[{index}]"))
    return findings


def write_episode_bundle(
    bundle: InvestigationEpisodeBundle,
    public_path: Path,
    oracle_path: Path,
) -> dict[str, str]:
    if public_path.resolve() == oracle_path.resolve():
        raise ValueError("public and oracle outputs must be different files")

    public_payload = bundle.public.model_dump(mode="json")
    leaks = _find_private_keys(public_payload)
    if leaks:
        raise ValueError(f"private fields detected in public payload: {leaks}")
    oracle_payload = bundle.oracle.model_dump(mode="json")

    public_path.parent.mkdir(parents=True, exist_ok=True)
    oracle_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_bytes(canonical_json_bytes(public_payload) + b"\n")
    oracle_path.write_bytes(canonical_json_bytes(oracle_payload) + b"\n")
    return {
        "public_sha256": canonical_sha256(public_payload),
        "oracle_sha256": canonical_sha256(oracle_payload),
    }
