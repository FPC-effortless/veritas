from __future__ import annotations

from typing import Any

from investigation_world.foundry.models import stable_hash


def portable_task_id(
    *,
    environment_id: str,
    environment_version: str,
    source_digest: str,
    split: str,
    seed: int,
) -> str:
    payload = {
        "environment_id": environment_id,
        "environment_version": environment_version,
        "source_digest": source_digest,
        "split": split,
        "seed": seed,
    }
    return f"PTASK-{stable_hash(payload)[:24].upper()}"


def portable_run_id(
    *,
    environment_id: str,
    environment_version: str,
    task_id: str,
    seed: int,
    invocation: str,
) -> str:
    payload = {
        "environment_id": environment_id,
        "environment_version": environment_version,
        "task_id": task_id,
        "seed": seed,
        "invocation": invocation,
    }
    return f"PRUN-{stable_hash(payload)[:24].upper()}"


def state_digest(value: Any) -> str:
    return stable_hash(value)
