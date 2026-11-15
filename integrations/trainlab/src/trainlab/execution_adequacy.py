"""Reconcile declared post-run observations with the frozen research contract.

Producer/source hashes bind declarations, not truthful instrumentation. This is a
necessary-condition check, never proof of scientific suitability or actual work.
"""

from __future__ import annotations

import copy
import json

from .prediction_artifacts import _bytes, _hash, _require, _text
from .runner import _finite

_DIMENSIONS = ("model_size", "training_duration", "datasets", "training_regime")


def validate_execution(contract, config):
    """Validate all four prospective post-run conditions and retained artifact path."""
    _bytes(contract)
    _require(
        type(contract) is dict and type(config) is dict, "execution contract and recipe required"
    )
    execution = contract.get("execution")
    _require(
        type(execution) is dict
        and set(execution) == {"artifact", "dimensions"}
        and _text(execution["artifact"])
        and type(config.get("artifacts")) is list
        and execution["artifact"] in config["artifacts"],
        "execution observations must be a declared retained artifact",
    )
    dimensions = execution["dimensions"]
    _require(
        type(dimensions) is dict and set(dimensions) == set(_DIMENSIONS),
        "all four execution adequacy dimensions required",
    )
    for criteria in dimensions.values():
        _require(
            type(criteria) is list and 1 <= len(criteria) <= 32,
            "bounded nonempty execution criteria required",
        )
        seen = set()
        for criterion in criteria:
            _require(
                type(criterion) is dict
                and set(criterion) == {"field", "operator", "threshold", "rationale"}
                and _text(criterion["field"])
                and _text(criterion["rationale"])
                and criterion["operator"] in ("eq", "ge", "le")
                and _finite(criterion["threshold"]),
                "invalid execution criterion",
            )
            key = (criterion["field"], criterion["operator"], criterion["threshold"])
            _require(key not in seen, "duplicate execution criterion")
            seen.add(key)


def assess_execution(contract, config, input_hashes, artifact_document):
    """Check pinned producer observations; missing numeric observations are UNKNOWN."""
    from .research_adequacy import recipe_identity

    validate_execution(contract, config)
    _bytes(artifact_document)
    _require(
        type(input_hashes) is dict
        and set(input_hashes) == set(config["inputs"])
        and all(_hash(value) for value in input_hashes.values()),
        "complete recorded execution input identities required",
    )
    identity = recipe_identity(config)
    _require(contract.get("recipe_sha256") == identity, "execution contract recipe changed")
    pointer = config.get("research_adequacy")
    _require(
        type(pointer) is dict
        and pointer.get("file") in input_hashes
        and input_hashes[pointer["file"]] == pointer.get("sha256"),
        "execution adequacy contract pin missing or changed",
    )
    _require(
        contract.get("inputs")
        == {name: pin for name, pin in input_hashes.items() if name != pointer["file"]},
        "execution contract input closure changed",
    )
    receipt = artifact_document
    _require(
        type(receipt) is dict
        and set(receipt) == {"schema", "recipe_sha256", "inputs", "producer", "observations"}
        and receipt["schema"] == "trainlab.execution-adequacy-observations.v1"
        and receipt["recipe_sha256"] == identity
        and receipt["inputs"] == input_hashes,
        "post-run receipt recipe or inputs changed",
    )
    producer = receipt["producer"]
    _require(
        type(producer) is dict
        and set(producer) == {"file", "sha256"}
        and _text(producer["file"])
        and producer["file"] in input_hashes
        and producer["file"] != pointer["file"]
        and producer["sha256"] == input_hashes[producer["file"]],
        "observation producer must bind a separate declared source input",
    )
    observations = receipt["observations"]
    _require(
        type(observations) is dict
        and len(observations) <= 512
        and all(_text(key) and _finite(value) for key, value in observations.items()),
        "post-run observations must be bounded finite scalar values, not booleans",
    )
    checks = []
    for dimension in _DIMENSIONS:
        for criterion in contract["execution"]["dimensions"][dimension]:
            field = criterion["field"]
            value = observations.get(field)
            status = "UNKNOWN"
            if value is not None:
                op, threshold = criterion["operator"], criterion["threshold"]
                passed = {
                    "eq": value == threshold,
                    "ge": value >= threshold,
                    "le": value <= threshold,
                }[op]
                status = "MET" if passed else "INADEQUATE"
            checks.append(
                {
                    "dimension": dimension,
                    "criterion": copy.deepcopy(criterion),
                    "observed": value,
                    "status": status,
                }
            )
    states = {check["status"] for check in checks}
    status = (
        "INADEQUATE" if "INADEQUATE" in states else ("UNKNOWN" if "UNKNOWN" in states else "MET")
    )
    report = {
        "schema": "trainlab.execution-adequacy-report.v1",
        "status": status,
        "recipe_sha256": identity,
        "input_hashes": dict(input_hashes),
        "artifact": contract["execution"]["artifact"],
        "producer": copy.deepcopy(producer),
        "observations": copy.deepcopy(observations),
        "checks": checks,
        "qualification": "NOT_QUALIFIED",
        "evidence_scope": "DECLARED_POST_RUN_OBSERVATIONS_NOT_INDEPENDENTLY_ATTESTED",
        "guarantee": "Frozen numeric conditions checked against pinned producer declarations; "
        "truthful instrumentation, actual work and scientific suitability unverified.",
    }

    _require(
        len((json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        <= 1024 * 1024,
        "execution adequacy report exceeds 1 MiB limit",
    )
    return report
