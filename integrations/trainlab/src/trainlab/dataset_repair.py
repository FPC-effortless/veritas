"""Connect pinned Forge dataset changes with bound TrainLab predictions."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from .prediction_artifacts import _bytes, _hash, _require, _text, make_request, read_predictions

STATE = {
    "mode": "stateless",
    "initial_state_sha256": hashlib.sha256(b"stateless").hexdigest(),
    "persists": "fixed fitted model",
    "query_mutates": False,
    "reset": "fresh independent row",
}


def _selected(view, row):
    return {
        name: row["features"][name] for name in view["feature_fields"] if name in row["features"]
    }


def _missing_features(view, rows, slice_field):
    fields = set(view["feature_fields"]) - {slice_field}
    return sum(any(row["features"].get(k) is None for k in fields) for row in rows)


def _disjoint(first_view, first, second_view, second, *, slice_field=None):
    left_fields = set(first_view["feature_fields"]) - {slice_field}
    right_fields = set(second_view["feature_fields"]) - {slice_field}
    _require(left_fields and left_fields == right_fields, "selected feature fields differ")
    _require(
        not ({r["id"] for r in first} & {r["id"] for r in second}), "panels share a row identity"
    )

    def signatures(rows):
        return {
            _bytes({k: r["features"][k] for k in left_fields if k in r["features"]}) for r in rows
        }

    _require(not (signatures(first) & signatures(second)), "panels share exact selected features")
    for field in set(first_view["group_fields"]) | set(second_view["group_fields"]):
        left = [r.get("groups", {}).get(field) for r in first]
        right = [r.get("groups", {}).get(field) for r in second]
        _require(all(v is not None for v in left + right), "declared group identity unavailable")
        _require(
            not ({_bytes(v) for v in left} & {_bytes(v) for v in right}),
            "panels share a declared group",
        )


def classification_request(
    view, *, dataset_sha256, model_sha256, code_sha256, configuration_sha256
):
    """Use the exact ordered validation features as the model input contract."""
    validation = [r for r in view["rows"] if r["split"] == "validation"]
    return make_request(
        {
            "model": model_sha256,
            "dataset": dataset_sha256,
            "code": code_sha256,
            "configuration": configuration_sha256,
        },
        [{"id": r["id"], "input": _selected(view, r)} for r in validation],
        task={"name": "forge-validation-classification", "output_schema": "finite-json-v1"},
        state=STATE,
    )


def _predictions(view, dataset_pin, artifact, code, configuration):
    _require(
        type(artifact) is dict
        and set(artifact) == {"path", "sha256", "model_sha256"}
        and _hash(artifact["sha256"])
        and _hash(artifact["model_sha256"]),
        "model and prediction artifact pins required",
    )
    request = classification_request(
        view,
        dataset_sha256=dataset_pin,
        model_sha256=artifact["model_sha256"],
        code_sha256=code,
        configuration_sha256=configuration,
    )
    answers = read_predictions(artifact["path"], artifact["sha256"], request)
    _require(
        all(a["output"] is None or _text(a["output"]) for a in answers),
        "classification outputs must be nonempty strings or null",
    )
    return answers


def _scope(rows, slice_field):
    if slice_field is not None:
        _require(_text(slice_field), "invalid slice field")
    data = defaultdict(list)
    for index, row in enumerate(rows):
        group = row["features"].get(slice_field) if slice_field else None
        _require(group is None or _text(group), "slice field must contain strings or null")
        data[group].append(index)
    return data


def _paired(rows, before, after, indices):
    baseline, repaired, rescued, damaged, unknown = 0, 0, [], [], 0
    for i in indices:
        truth, old, new = rows[i].get("label"), before[i]["output"], after[i]["output"]
        _require(truth is None or _text(truth), "label must be a nonempty string or null")
        if truth is None or old is None or new is None:
            unknown += 1
            continue
        baseline += old == truth
        repaired += new == truth
        if old != truth and new == truth:
            rescued.append(rows[i]["id"])
        if old == truth and new != truth:
            damaged.append(rows[i]["id"])
    count = len(indices) - unknown
    return {
        "rows": len(indices),
        "scored": count,
        "unknown": unknown,
        "before_correct": baseline,
        "after_correct": repaired,
        "before_accuracy": baseline / count if count else None,
        "after_accuracy": repaired / count if count else None,
        "net_accuracy_change": (repaired - baseline) / count if count else None,
        "rescued_ids": rescued,
        "damaged_ids": damaged,
    }


def compare_label_repair(
    parent_path,
    corrected_path,
    *,
    parent_sha256,
    corrected_sha256,
    reviews,
    baseline,
    repaired,
    code_sha256,
    configuration_sha256,
    slice_field=None,
):
    """Verify the reviewed dataset revision and compare its bound predictions."""
    from forge_data.quality_diagnostics import _load, adjudicate

    parent, corrected = _load(parent_path, parent_sha256), _load(corrected_path, corrected_sha256)
    result = adjudicate(parent_path, sha256=parent_sha256, reviews=reviews)
    revised = result["observations"]
    _require(
        _bytes(revised["document"]) == _bytes(corrected) and _bytes(parent) != _bytes(corrected),
        "corrected view is not the changed reviewed revision",
    )
    by_id = {row["id"]: row for row in parent["rows"]}
    corrected_by_id = {row["id"]: row for row in corrected["rows"]}
    changed = [
        i
        for i in revised["applied_ids"]
        if _bytes(by_id[i].get("label")) != _bytes(corrected_by_id[i].get("label"))
    ]
    _require(bool(changed), "review does not change any training label value")
    _require(
        all(by_id[i]["split"] == "train" for i in revised["applied_ids"]),
        "revisions may change only training labels",
    )
    validation = [r for r in parent["rows"] if r["split"] == "validation"]
    training = [r for r in parent["rows"] if r["split"] == "train"]
    _require(bool(validation) and bool(training), "train and validation rows required")
    _require(
        slice_field is None or (_text(slice_field) and slice_field in parent["feature_fields"]),
        "undeclared slice",
    )
    _require(
        not _missing_features(parent, training + validation, slice_field),
        "label repair requires complete selected model features",
    )
    _disjoint(parent, training, parent, validation, slice_field=slice_field)
    a = _predictions(parent, parent_sha256, baseline, code_sha256, configuration_sha256)
    b = _predictions(corrected, corrected_sha256, repaired, code_sha256, configuration_sha256)
    paired = _paired(validation, a, b, range(len(validation)))
    slices = _scope(validation, slice_field)
    return {
        "schema": "trainlab.dataset-repair.v1",
        "status": "INCONCLUSIVE" if paired["unknown"] or result["status"] != "TESTED" else "TESTED",
        "parent_sha256": parent_sha256,
        "corrected_sha256": corrected_sha256,
        "adjudication_sha256": result["input_sha256"],
        "prediction_sha256": [baseline["sha256"], repaired["sha256"]],
        "document_sha256": revised["document_sha256"],
        "accepted_review_ids": revised["applied_ids"],
        "changed_label_ids": changed,
        "unresolved_review_ids": [
            review["id"] for review in reviews if review["decision"] == "unresolved"
        ],
        "groups_declared": parent["group_fields"],
        "overall": paired,
        "slices": [
            {"value": key, **_paired(validation, a, b, indices)} for key, indices in slices.items()
        ],
        "scope": "Observed paired repair effects. Reviewer identity and selection are declared.",
        "scientific_qualification": "NOT_QUALIFIED",
    }


def compare_drift_performance(
    reference_path,
    current_path,
    *,
    reference_sha256,
    current_sha256,
    reference_predictions,
    current_predictions,
    code_sha256,
    configuration_sha256,
    fields,
    thresholds,
    slice_field=None,
):
    """Report descriptive feature drift beside performance on disjoint labeled panels."""
    from forge_data.quality_diagnostics import _load, distributions

    reference = _load(reference_path, reference_sha256)
    current = _load(current_path, current_sha256)
    panels = [
        [row for row in view["rows"] if row["split"] == "validation"]
        for view in (reference, current)
    ]
    _require(all(panels), "both evaluation panels must contain rows")
    _require(
        slice_field is None
        or (
            _text(slice_field)
            and all(slice_field in v["feature_fields"] for v in (reference, current))
        ),
        "undeclared slice",
    )
    _disjoint(reference, panels[0], current, panels[1], slice_field=slice_field)
    training = [r for r in reference["rows"] if r["split"] == "train"]
    current_training = [r for r in current["rows"] if r["split"] == "train"]
    _require(_bytes(training) == _bytes(current_training), "drift panels must share training rows")
    if training:
        _disjoint(reference, training, reference, panels[0], slice_field=slice_field)
        _disjoint(reference, training, current, panels[1], slice_field=slice_field)
    outputs = [
        _predictions(view, pin, artifact, code_sha256, configuration_sha256)
        for view, pin, artifact in (
            (reference, reference_sha256, reference_predictions),
            (current, current_sha256, current_predictions),
        )
    ]
    _require(
        reference_predictions["model_sha256"] == current_predictions["model_sha256"],
        "drift performance requires one fixed model",
    )
    drift = distributions(
        reference_path,
        current_path,
        reference_sha256=reference_sha256,
        current_sha256=current_sha256,
        reference_split="validation",
        current_split="validation",
        fields=fields,
        thresholds=thresholds,
    )
    tables = []
    for panel, output in zip(panels, outputs, strict=True):
        table = {}
        for label, indices in _scope(panel, slice_field).items():
            paired = _paired(panel, output, output, indices)
            table[label] = {
                "rows": paired["rows"],
                "scored": paired["scored"],
                "correct": paired["before_correct"],
                "accuracy": paired["before_accuracy"],
            }
        tables.append(table)
    slices = []
    for label in dict.fromkeys([*tables[0], *tables[1]]):
        old, new = tables[0].get(label), tables[1].get(label)
        values = [p["accuracy"] if p else None for p in (old, new)]
        slices.append(
            {
                "value": label,
                "reference": old,
                "current": new,
                "accuracy_difference": values[1] - values[0] if None not in values else None,
            }
        )
    info = drift["observations"]
    missing_features = [
        _missing_features(view, rows, slice_field)
        for view, rows in ((reference, panels[0]), (current, panels[1]))
    ]
    missing_training = _missing_features(reference, training, slice_field)
    incomplete = (
        any(missing_features)
        or missing_training > 0
        or info["partial"]
        or any(
            check["distance"] is None or any(check["missing"]) or any(check["invalid"])
            for check in info["checks"]
        )
        or any(
            cell is None or cell["rows"] != cell["scored"]
            for row in slices
            for cell in (row["reference"], row["current"])
        )
    )
    return {
        "schema": "trainlab.drift-performance.v1",
        "status": "INCONCLUSIVE" if incomplete else "TESTED",
        "distribution": drift,
        "incomplete_input_rows": {
            "reference": missing_features[0],
            "current": missing_features[1],
            "training": missing_training,
        },
        "accuracy_by_slice": slices,
        "reference_sha256": reference_sha256,
        "current_sha256": current_sha256,
        "prediction_sha256": [reference_predictions["sha256"], current_predictions["sha256"]],
        "scope": "Descriptive comparison on disjoint declared panels. No causal attribution.",
        "scientific_qualification": "NOT_QUALIFIED",
    }
