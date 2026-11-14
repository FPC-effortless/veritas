"""Compare exact paired outcomes under a declared model intervention."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .prediction_artifacts import MAX_BYTES, _bytes, _hash, _request, _require, read_predictions
from .runner import LabError, _constant, _pairs

_ARMS = ("baseline", "treatment")
_ROLES = ("focal", "collateral")


def _encoded(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    except UnicodeError as exc:
        raise LabError("invalid Unicode in intervention evidence") from exc


def _document(spec, name):
    _require(
        type(spec) is dict and set(spec) == {"path", "sha256"} and _hash(spec["sha256"]),
        f"{name} requires a path and external pin",
    )
    path = Path(spec["path"])
    _require(
        path.is_file() and not any(p.is_symlink() for p in (path, *path.absolute().parents)),
        f"{name} requires a regular file",
    )
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    _require(
        len(raw) <= MAX_BYTES and hashlib.sha256(raw).hexdigest() == spec["sha256"],
        f"{name} size or pin mismatch",
    )
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LabError(f"invalid {name} document") from exc
    _bytes(value)
    return value


def _predictions(spec):
    _require(
        type(spec) is dict and set(spec) == {"path", "sha256", "request"} and _hash(spec["sha256"]),
        "prediction path, pin and request required",
    )
    _request(spec["request"])
    return spec["request"]


def compare(design, recipe, panel, baseline, treatment):
    """Verify pinned design and two prediction artifacts before scoring outcomes."""
    protocol = _document(design, "intervention design")
    _require(
        type(protocol) is dict
        and set(protocol)
        == {
            "schema",
            "mode",
            "recipe_sha256",
            "panel_sha256",
            "prediction_sha256",
            "training_run_sha256",
        }
        and protocol["schema"] == "trainlab.intervention-comparison.v1"
        and protocol["mode"] in ("frozen", "retrained"),
        "unsupported intervention design",
    )
    _require(
        type(_document(recipe, "intervention recipe")) is dict
        and protocol["recipe_sha256"] == recipe["sha256"],
        "intervention recipe pin differs from design",
    )
    labels = _document(panel, "intervention panel")
    _require(
        type(labels) is dict
        and set(labels) == {"labels"}
        and type(labels["labels"]) is dict
        and protocol["panel_sha256"] == panel["sha256"],
        "intervention panel pin or fields differ from design",
    )
    labels = labels["labels"]
    left, right = _predictions(baseline), _predictions(treatment)
    _require(
        protocol["prediction_sha256"]
        == {"baseline": baseline["sha256"], "treatment": treatment["sha256"]},
        "prediction artifact pins differ from design",
    )
    _require(
        all(_encoded(left[field]) == _encoded(right[field]) for field in ("rows", "task", "state"))
        and left["identities"]["dataset"] == right["identities"]["dataset"],
        "evaluation dataset, ordered inputs, task and state must match",
    )
    same_model = left["identities"]["model"] == right["identities"]["model"]
    training = protocol["training_run_sha256"]
    if protocol["mode"] == "frozen":
        _require(same_model and training is None, "frozen intervention requires the same model")
    else:
        _require(
            type(training) is dict
            and set(training) == set(_ARMS)
            and all(_hash(value) for value in training.values())
            and len(set(training.values())) == 2,
            "distinct declared retraining run hashes required",
        )
    _require(
        set(labels) == {row["id"] for row in left["rows"]}
        and all(
            type(row) is dict
            and set(row) == {"label", "labeled", "role"}
            and type(row["labeled"]) is bool
            and (row["labeled"] or row["label"] is None)
            and row["role"] in _ROLES
            for row in labels.values()
        ),
        "one labeled or unknown role binding required per evaluation row",
    )
    before = read_predictions(baseline["path"], baseline["sha256"], left)
    after = read_predictions(treatment["path"], treatment["sha256"], right)
    roles = {
        role: dict.fromkeys(
            (
                "expected",
                "labeled",
                "unknown_labels",
                "changed",
                "rescued",
                "harmed",
                "baseline_correct",
                "treatment_correct",
            ),
            0,
        )
        for role in _ROLES
    }
    witnesses = {"changed": [], "rescued": [], "harmed": []}
    for first, second in zip(before, after, strict=True):
        row_id = first["id"]
        row = labels[row_id]
        aggregate = roles[row["role"]]
        aggregate["expected"] += 1
        start, end = _encoded(first["output"]), _encoded(second["output"])
        if start != end:
            aggregate["changed"] += 1
            witnesses["changed"].append(row_id)
        if not row["labeled"]:
            aggregate["unknown_labels"] += 1
            continue
        aggregate["labeled"] += 1
        expected = _encoded(row["label"])
        baseline_correct, treatment_correct = start == expected, end == expected
        aggregate["baseline_correct"] += baseline_correct
        aggregate["treatment_correct"] += treatment_correct
        if baseline_correct != treatment_correct:
            kind = "rescued" if treatment_correct else "harmed"
            aggregate[kind] += 1
            witnesses[kind].append(row_id)
    counts = {key: sum(role[key] for role in roles.values()) for key in roles["focal"]}
    return {
        "schema": "trainlab.intervention-outcomes.v1",
        "status": "INCONCLUSIVE" if counts["unknown_labels"] else "TESTED",
        "mode": protocol["mode"],
        "same_model_identity": same_model,
        "design_sha256": design["sha256"],
        "recipe_sha256": recipe["sha256"],
        "panel_sha256": panel["sha256"],
        "prediction_sha256": protocol["prediction_sha256"],
        "training_run_sha256": training,
        "counts": counts,
        "roles": roles,
        "witnesses": witnesses,
        "scope": "Exact label comparison. Execution and training identities remain declared.",
        "scientific_qualification": "NOT_QUALIFIED",
    }
