"""Fail-closed structural verifier for Forge's offline demo evidence pair.

This validates untrusted JSON claims and a CI-generated sandbox record. It is
not an attestation service and never qualifies source rights, science, devices,
external developers, or commercial release.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path

from .core import ForgeError

MEASUREMENT_SCHEMA = "forge.offline-demo-measurement.v1"
EXECUTION_SCHEMA = "forge.offline-demo-ci-execution.v1"
VERIFICATION_SCHEMA = "forge.offline-demo-verification.v1"
LIMIT_MS = 600_000
MAX_JSON_BYTES = 256 * 1024
SHA256 = re.compile(r"^[a-f0-9]{64}$")
COMMIT = re.compile(r"^[a-f0-9]{40}$")
RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")
IMAGE_ID = re.compile(r"^sha256:[a-f0-9]{64}$")
SAFE_CHILD_KEYS = {
    "PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG", "LC_ALL",
    "PYTHONPATH", "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE",
}
TIMER = (
    "time.perf_counter_ns around child interpreter startup, imports and quickstart"
)
MEASUREMENT_SCOPE = "excludes checkout, runner provisioning and container-image acquisition"
NETWORK_NOTE = (
    "This measurer does not disable OS networking; the CI workflow runs it in a "
    "Docker --network=none container."
)
TEMPORARY_STORAGE = "isolated tmpfs and receipt mount"


def _exact(value: object, names: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != names:
        raise ForgeError(f"{label}: required-only fields mismatch")
    return value


def _json_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ForgeError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ForgeError(f"non-finite JSON number is forbidden: {value}")


def _decode_json(raw: bytes, label: str) -> object:
    if not isinstance(raw, bytes) or len(raw) > MAX_JSON_BYTES:
        raise ForgeError(f"{label}: JSON bytes are missing or exceed size limit")
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_json_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ForgeError(f"{label}: invalid UTF-8 JSON") from exc
    except RecursionError as exc:
        raise ForgeError(f"{label}: JSON nesting exceeds parser limit") from exc


def _read_bytes(path: Path, label: str) -> bytes:
    """Read one bounded regular file without following a final symlink or blocking on a FIFO."""
    source = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        # O_NOFOLLOW closes the final-component symlink race on platforms that support it.
        # The pre-open check is the portable fallback; fstat below still verifies the opened
        # object itself is a regular file.
        if not nofollow and source.is_symlink():
            raise ForgeError(f"{label}: regular, non-symlink file required")
        descriptor = os.open(source, flags | nofollow)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ForgeError(f"{label}: regular, non-symlink file required")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1  # fdopen now owns and closes the descriptor.
            raw = stream.read(MAX_JSON_BYTES + 1)
    except ForgeError:
        raise
    except OSError as exc:
        raise ForgeError(f"{label}: regular, non-symlink file required") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > MAX_JSON_BYTES:
        raise ForgeError(f"{label}: JSON file exceeds size limit")
    return raw


def _text(value: object, name: str, expected: str | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ForgeError(f"{name}: bounded nonempty string required")
    if expected is not None and value != expected:
        raise ForgeError(f"{name}: expected {expected!r}")
    return value


def _int(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ForgeError(f"{name}: integer >= {minimum} required")
    return value


def _bool(value: object, name: str, expected: bool) -> bool:
    if type(value) is not bool or value is not expected:
        raise ForgeError(f"{name}: expected {expected}")
    return value


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ForgeError(f"{name}: lowercase SHA-256 required")
    return value


def _validate_measurement(receipt: object, expected_commit: str) -> dict:
    d = _exact(
        receipt,
        {"schema", "result", "commit", "measurement", "environment", "network",
         "child_exit_code", "failure_reason", "quickstart", "qualification"},
        "measurement receipt",
    )
    _text(d["schema"], "measurement.schema", MEASUREMENT_SCHEMA)
    _text(d["result"], "measurement.result", "PASS")
    commit = _text(d["commit"], "measurement.commit")
    if COMMIT.fullmatch(commit) is None or commit != expected_commit:
        raise ForgeError("measurement.commit: exact expected source commit required")
    if d["failure_reason"] is not None:
        raise ForgeError("measurement.failure_reason: successful receipt must be null")
    _int(d["child_exit_code"], "measurement.child_exit_code")
    if d["child_exit_code"] != 0:
        raise ForgeError("measurement.child_exit_code: successful receipt must be zero")

    m = _exact(
        d["measurement"],
        {"elapsed_ms", "limit_ms", "within_ten_minutes", "timer", "scope"},
        "measurement.measurement",
    )
    elapsed = _int(m["elapsed_ms"], "measurement.elapsed_ms")
    if elapsed > LIMIT_MS:
        raise ForgeError("measurement.elapsed_ms: ten-minute limit exceeded")
    if _int(m["limit_ms"], "measurement.limit_ms") != LIMIT_MS:
        raise ForgeError("measurement.limit_ms: unexpected limit")
    _bool(m["within_ten_minutes"], "measurement.within_ten_minutes", True)
    _text(m["timer"], "measurement.timer", TIMER)
    _text(m["scope"], "measurement.scope", MEASUREMENT_SCOPE)

    env = _exact(
        d["environment"],
        {"child_environment_keys", "secret_environment_forwarding"},
        "measurement.environment",
    )
    keys = env["child_environment_keys"]
    if (
        not isinstance(keys, list)
        or any(not isinstance(key, str) for key in keys)
        or keys != sorted(set(keys))
        or not set(keys).issubset(SAFE_CHILD_KEYS)
        or "PATH" not in keys
        or "PYTHONPATH" not in keys
    ):
        raise ForgeError("measurement.environment: child keys exceed the safe allowlist")
    _text(env["secret_environment_forwarding"], "measurement.secret_environment_forwarding",
          "DISABLED_BY_ALLOWLIST")

    network = _exact(d["network"], {"enforcement", "note"}, "measurement.network")
    _text(network["enforcement"], "measurement.network.enforcement", "EXTERNAL_SANDBOX_REQUIRED")
    _text(network["note"], "measurement.network.note", NETWORK_NOTE)

    quick = _exact(
        d["quickstart"],
        {"demo", "records", "subject_split_isolation", "point_in_time_masking", "rights",
         "authentic_dataset", "scientific_qualification", "model_training", "outcomes",
         "hidden_labels", "physical_offline_inference", "trainlab_receipt_structural",
         "trainlab_receipt_science", "trainlab_receipt_device"},
        "measurement.quickstart",
    )
    expected = {
        "demo": "CONSTRUCTED_ONLY",
        "subject_split_isolation": "PASS_CONSTRUCTED",
        "point_in_time_masking": "PASS_CONSTRUCTED",
        "rights": "FIXTURE_DECLARATIONS_NOT_VERIFIED",
        "authentic_dataset": "NOT_USED",
        "scientific_qualification": "NOT_PERFORMED",
        "model_training": "NOT_PERFORMED",
        "outcomes": "UNKNOWN_UNVERIFIED_ONLY",
        "hidden_labels": "NOT_USED",
        "physical_offline_inference": "NOT_RUN",
        "trainlab_receipt_structural": "PASS",
        "trainlab_receipt_science": "NOT_QUALIFIED",
        "trainlab_receipt_device": "NOT_QUALIFIED",
    }
    for key, value in expected.items():
        _text(quick[key], f"measurement.quickstart.{key}", value)
    if _int(quick["records"], "measurement.quickstart.records") != 12:
        raise ForgeError("measurement.quickstart.records: expected constructed fixture size 12")

    qualification = _exact(
        d["qualification"],
        {"scientific", "source_rights", "physical_device", "commercial_release"},
        "measurement.qualification",
    )
    for key, value in {
        "scientific": "NOT_QUALIFIED",
        "source_rights": "NOT_VERIFIED",
        "physical_device": "NOT_RUN",
        "commercial_release": "NOT_AUTHORIZED",
    }.items():
        _text(qualification[key], f"measurement.qualification.{key}", value)
    return {"commit": commit, "elapsed_ms": elapsed}


def _validate_execution(execution: object, expected_commit: str,
                        measurement: dict, receipt_bytes: bytes) -> None:
    d = _exact(
        execution,
        {"schema", "run_id", "source_commit", "container_image", "container_image_id",
         "network_mode", "container_root_filesystem", "checkout_mount", "temporary_storage",
         "secrets_passed_to_container", "model_training", "hidden_labels", "demo_elapsed_ms",
         "demo_limit_ms", "receipt_sha256", "scientific_qualification",
         "physical_offline_inference"},
        "CI execution record",
    )
    _text(d["schema"], "execution.schema", EXECUTION_SCHEMA)
    run_id = _text(d["run_id"], "execution.run_id")
    if RUN_ID.fullmatch(run_id) is None:
        raise ForgeError("execution.run_id: positive decimal GitHub run ID required")
    _text(d["source_commit"], "execution.source_commit", expected_commit)
    _text(d["container_image"], "execution.container_image", "python:3.13-slim")
    image_id = _text(d["container_image_id"], "execution.container_image_id")
    if IMAGE_ID.fullmatch(image_id) is None:
        raise ForgeError("execution.container_image_id: immutable image ID required")
    _text(d["network_mode"], "execution.network_mode", "none")
    _text(d["container_root_filesystem"], "execution.container_root_filesystem", "read-only")
    _text(d["checkout_mount"], "execution.checkout_mount", "read-only")
    _text(d["temporary_storage"], "execution.temporary_storage", TEMPORARY_STORAGE)
    _bool(d["secrets_passed_to_container"], "execution.secrets_passed_to_container", False)
    _text(d["model_training"], "execution.model_training", "NOT_PERFORMED")
    _text(d["hidden_labels"], "execution.hidden_labels", "NOT_USED")
    if _int(d["demo_elapsed_ms"], "execution.demo_elapsed_ms") != measurement["elapsed_ms"]:
        raise ForgeError("execution.demo_elapsed_ms: must match the measurement receipt")
    if _int(d["demo_limit_ms"], "execution.demo_limit_ms") != LIMIT_MS:
        raise ForgeError("execution.demo_limit_ms: unexpected limit")
    digest = _sha(d["receipt_sha256"], "execution.receipt_sha256")
    if digest != hashlib.sha256(receipt_bytes).hexdigest():
        raise ForgeError("execution.receipt_sha256: receipt byte binding mismatch")
    _text(d["scientific_qualification"], "execution.scientific_qualification", "NOT_PERFORMED")
    _text(d["physical_offline_inference"], "execution.physical_offline_inference", "NOT_RUN")


def validate_offline_demo(receipt_bytes: bytes, execution_bytes: bytes,
                          expected_commit: str) -> dict:
    """Verify raw receipt bytes and return a redacted nonqualifying verdict."""
    if not isinstance(expected_commit, str) or COMMIT.fullmatch(expected_commit) is None:
        raise ForgeError("expected_commit: lowercase 40-character commit SHA required")
    receipt = _decode_json(receipt_bytes, "measurement receipt")
    execution = _decode_json(execution_bytes, "CI execution record")
    measurement = _validate_measurement(receipt, expected_commit)
    _validate_execution(execution, expected_commit, measurement, receipt_bytes)
    return {
        "schema": VERIFICATION_SCHEMA,
        "structural_validation": "PASS",
        "expected_source_commit": expected_commit,
        "reported_elapsed_ms": measurement["elapsed_ms"],
        "claimed_network_mode": "none",
        "claimed_secrets_passed_to_container": False,
        "model_training": "NOT_PERFORMED",
        "hidden_labels": "NOT_USED",
        "scientific_qualification": "NOT_QUALIFIED",
        "source_rights": "NOT_VERIFIED",
        "physical_device": "NOT_RUN",
        "external_developer_acceptance": "NOT_ESTABLISHED",
        "commercial_release": "NOT_AUTHORIZED",
    }


def validate_offline_demo_files(receipt_path: Path, execution_path: Path,
                                expected_commit: str) -> dict:
    """Read bounded, strict JSON files and verify their cross-bound receipt identity."""
    receipt_bytes = _read_bytes(Path(receipt_path), "measurement receipt")
    execution_bytes = _read_bytes(Path(execution_path), "CI execution record")
    return validate_offline_demo(receipt_bytes, execution_bytes, expected_commit)
