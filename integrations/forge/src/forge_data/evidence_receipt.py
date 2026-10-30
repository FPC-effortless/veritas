"""TrainLab/Forge evidence-receipt *claim* validator, not an attestation service.

A locally supplied JSON receipt is untrusted. This validator checks structural
completeness and matching conditions but NEVER promotes self-reported evidence
to authentic science, physical-device qualification or a Veritas certificate.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from .core import ForgeError

SCHEMA = "trainlab.developer_evidence.v0.1"
MAX_RECEIPT_BYTES = 128 * 1024
SHA256 = re.compile(r"^[a-f0-9]{64}$")
LOCAL_STAGES = (
    "input",
    "preprocessing",
    "embeddings",
    "inference",
    "persistent_state",
    "output",
    "speech_if_used",
)


def _exact(value: object, names: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != names:
        raise ForgeError(f"{label}: required-only fields mismatch")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        raise ForgeError(f"{name}: nonempty bounded string required")
    return value


def _hash(value: object, name: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ForgeError(f"{name}: lowercase SHA256 required")
    return value


def _count(value: object, name: str, *, positive: bool = True) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        raise ForgeError(
            f"{name}: positive integer required"
            if positive
            else f"{name}: nonnegative integer required"
        )
    return value


def _number(value: object, name: str, *, positive: bool = False) -> float:
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value < 0
        or (positive and value == 0)
    ):
        raise ForgeError(f"{name}: finite nonnegative number required")
    return float(value)


def _not_run(obj: dict, keys: tuple[str, ...], name: str) -> None:
    if obj["status"] != "NOT_RUN":
        return
    for key in keys:
        if obj[key] is not None:
            raise ForgeError(f"{name}: NOT_RUN cannot carry {key}")


def validate_evidence(receipt: object) -> dict:
    """Check a developer claim and return only a redacted NONQUALIFYING verdict."""
    d = _exact(
        receipt,
        {
            "schema",
            "experiment_id",
            "track",
            "qualification",
            "source",
            "training",
            "device",
            "veritas",
        },
        "receipt",
    )
    if d["schema"] != SCHEMA:
        raise ForgeError("unsupported TrainLab evidence schema")
    _text(d["experiment_id"], "experiment_id")
    if d["track"] not in ("TAC_100K", "EXPLORATORY_500K", "OTHER"):
        raise ForgeError("unknown research parameter track")
    if d["qualification"] != "NOT_QUALIFIED":
        raise ForgeError("untrusted receipt may not claim scientific or device qualification")

    src = _exact(
        d["source"],
        {
            "kind",
            "dataset_id",
            "publisher_id",
            "original_sha256",
            "release_manifest_sha256",
            "rights_review",
            "point_in_time_review",
            "split_review",
        },
        "source",
    )
    _text(src["dataset_id"], "source.dataset_id")
    if src["kind"] not in ("CONSTRUCTED_FIXTURE", "AUTHENTIC_CANDIDATE"):
        raise ForgeError("source.kind unsupported")
    if src["kind"] == "CONSTRUCTED_FIXTURE":
        if src["publisher_id"] is not None or src["original_sha256"] is not None:
            raise ForgeError("constructed fixture cannot impersonate publisher original")
        if src["rights_review"] != "NOT_VERIFIED":
            raise ForgeError("constructed source cannot claim verified rights")
    else:
        _text(src["publisher_id"], "source.publisher_id")
        _hash(src["original_sha256"], "source.original_sha256")
    if src["release_manifest_sha256"] is not None:
        _hash(src["release_manifest_sha256"], "source.release_manifest_sha256")
    if src["rights_review"] not in ("NOT_VERIFIED", "REVIEW_PENDING"):
        raise ForgeError("receipt cannot attest rights")
    if src["point_in_time_review"] not in ("NOT_RUN", "CONSTRUCTED_CHECK", "INTERNAL_CHECK"):
        raise ForgeError("source.point_in_time_review invalid")
    if src["split_review"] not in ("NOT_RUN", "CONSTRUCTED_CHECK", "INTERNAL_CHECK"):
        raise ForgeError("source.split_review invalid")
    if src["kind"] == "CONSTRUCTED_FIXTURE" and (
        src["point_in_time_review"] == "INTERNAL_CHECK" or src["split_review"] == "INTERNAL_CHECK"
    ):
        raise ForgeError("constructed data cannot claim authentic-source checks")

    train = _exact(
        d["training"],
        {
            "status",
            "model_commit",
            "learned_parameters",
            "checkpoint_sha256",
            "optimizer_rng_replay_sha256",
            "data_split_identity",
            "train_tokens",
            "train_updates",
            "tuning_budget",
            "baselines",
        },
        "training",
    )
    if train["status"] not in ("NOT_RUN", "INTERNAL_MEASURED"):
        raise ForgeError("training status cannot promote untrusted report")
    _not_run(
        train,
        (
            "model_commit",
            "learned_parameters",
            "checkpoint_sha256",
            "optimizer_rng_replay_sha256",
            "data_split_identity",
            "train_tokens",
            "train_updates",
            "tuning_budget",
        ),
        "training",
    )
    if not isinstance(train["baselines"], list):
        raise ForgeError("training.baselines must be an array")
    if train["status"] == "NOT_RUN" and train["baselines"]:
        raise ForgeError("NOT_RUN training cannot carry baselines")
    if train["status"] == "INTERNAL_MEASURED":
        if src["kind"] != "AUTHENTIC_CANDIDATE":
            raise ForgeError("constructed fixtures cannot claim model training evidence")
        _text(train["model_commit"], "training.model_commit")
        _hash(train["checkpoint_sha256"], "training.checkpoint_sha256")
        _hash(train["optimizer_rng_replay_sha256"], "training.optimizer_rng_replay_sha256")
        _text(train["data_split_identity"], "training.data_split_identity")
        p = _count(train["learned_parameters"], "training.learned_parameters")
        if d["track"] == "TAC_100K" and not (95000 <= p <= 105000):
            raise ForgeError("TAC_100K parameter budget violated")
        if d["track"] == "EXPLORATORY_500K" and src["kind"] == "CONSTRUCTED_FIXTURE":
            raise ForgeError("exploratory work cannot promote constructed data")
        for key in ("train_tokens", "train_updates", "tuning_budget"):
            _count(train[key], "training." + key, positive=(key != "tuning_budget"))
        if d["track"] == "TAC_100K" and not train["baselines"]:
            raise ForgeError("matched TAC_100K research requires baseline controls")
        for arm in train["baselines"]:
            b = _exact(
                arm,
                {
                    "name",
                    "learned_parameters",
                    "data_split_identity",
                    "train_tokens",
                    "train_updates",
                    "tuning_budget",
                },
                "baseline",
            )
            _text(b["name"], "baseline.name")
            bp = _count(b["learned_parameters"], "baseline.learned_parameters")
            if abs(bp - p) > 0.01 * p:
                raise ForgeError("baseline learned parameters exceed 1 percent gap")
            for key in ("data_split_identity", "train_tokens", "train_updates", "tuning_budget"):
                if type(b[key]) is not type(train[key]) or b[key] != train[key]:
                    raise ForgeError(f"baseline {key} mismatched")

    device = _exact(
        d["device"],
        {
            "status",
            "model",
            "os",
            "export_format",
            "operator_support",
            "numerical_max_abs_error",
            "p50_ms",
            "p95_ms",
            "peak_ram_mb",
            "energy_mj",
            "airplane_mode",
            "network_trace_sha256",
            "state_replay",
            "delivery_sha256",
            "local_stages",
            "remote_fallback",
        },
        "device",
    )
    if device["status"] not in ("NOT_RUN", "INTERNAL_PHYSICAL_MEASURED"):
        raise ForgeError("device evidence cannot claim independent qualification")
    measured = tuple(k for k in device if k != "status")
    _not_run(device, measured, "device")
    if device["status"] == "INTERNAL_PHYSICAL_MEASURED":
        if src["kind"] == "CONSTRUCTED_FIXTURE" or train["status"] != "INTERNAL_MEASURED":
            raise ForgeError("constructed fixture or untrained model cannot claim device readiness")
        for key in ("model", "os", "export_format"):
            _text(device[key], "device." + key)
        for key in ("operator_support", "airplane_mode", "state_replay"):
            if device[key] is not True:
                raise ForgeError(f"device.{key}: required positive physical observation")
        if device["remote_fallback"] is not False:
            raise ForgeError("remote inference fallback is prohibited")
        stages = _exact(device["local_stages"], set(LOCAL_STAGES), "device.local_stages")
        if any(stages[stage] is not True for stage in LOCAL_STAGES):
            raise ForgeError("all stages including optional speech must stay on device")
        for key in ("numerical_max_abs_error", "p50_ms", "p95_ms", "peak_ram_mb", "energy_mj"):
            _number(
                device[key],
                "device." + key,
                positive=key in ("p50_ms", "p95_ms", "peak_ram_mb", "energy_mj"),
            )
        if device["p95_ms"] < device["p50_ms"]:
            raise ForgeError("p95 must not be less than p50")
        for key in ("network_trace_sha256", "delivery_sha256"):
            _hash(device[key], "device." + key)

    veritas = _exact(
        d["veritas"],
        {"status", "report_sha256", "protected_test_authorized", "independent_review"},
        "veritas",
    )
    if veritas["status"] not in ("NOT_RUN", "REVIEW_PENDING"):
        raise ForgeError("JSON cannot independently certify Veritas review")
    if veritas["report_sha256"] is not None:
        _hash(veritas["report_sha256"], "veritas.report_sha256")
    if (
        veritas["protected_test_authorized"] is not False
        or veritas["independent_review"] is not False
    ):
        raise ForgeError("untrusted receipt cannot authorize TEST or independent review")
    if veritas["status"] == "NOT_RUN" and veritas["report_sha256"] is not None:
        raise ForgeError("unrun verifier cannot carry report")

    return {
        "schema": SCHEMA,
        "structural_validation": "PASS",
        "source_classification": src["kind"],
        "training_claim": train["status"],
        "device_claim": device["status"],
        "veritas_claim": veritas["status"],
        "scientific_qualification": "NOT_QUALIFIED",
        "hardware_qualification": "NOT_QUALIFIED",
        "source_rights": "NOT_INDEPENDENTLY_VERIFIED",
        "commercial_release": "NOT_AUTHORIZED",
    }


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ForgeError("duplicate JSON key in evidence receipt")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ForgeError("nonfinite JSON number in evidence receipt")


def validate_evidence_file(path: Path) -> dict:
    with path.open("rb") as source:
        payload = source.read(MAX_RECEIPT_BYTES + 1)
    if len(payload) > MAX_RECEIPT_BYTES:
        raise ForgeError("evidence receipt exceeds size limit")
    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise ForgeError("malformed evidence receipt") from exc
    return validate_evidence(parsed)
