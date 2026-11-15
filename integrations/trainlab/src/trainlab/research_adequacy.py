"""Claim-specific necessary-condition gate, not scientific qualification.

Trusted reviewers define relevant criteria prospectively. Hashes attest byte identity,
not truthful observations, reviewer independence, convergence or causal validity.
"""

from __future__ import annotations

import copy
import hashlib
import json

from .prediction_artifacts import _bytes, _hash, _text
from .runner import LabError, _constant, _finite, _pairs, contained_file, digest, read_json

DIMENSIONS = ("model_size", "training_duration", "datasets", "training_regime")
CLAIMS = ("bounded_diagnostic", "fixed_budget_comparison", "generalization", "capacity_limit")


def _require(condition, message):
    if not condition:
        raise LabError(message)


def recipe_identity(config):
    """Exclude only the gate pointer to avoid a circular content hash."""
    return hashlib.sha256(
        _bytes({k: v for k, v in config.items() if k != "research_adequacy"})
    ).hexdigest()


def validate_pointer(pointer):
    _require(
        type(pointer) is dict
        and set(pointer) == {"file", "sha256"}
        and _text(pointer["file"])
        and _hash(pointer["sha256"]),
        "research adequacy requires a pinned contract",
    )


def _projections(contract):
    projections = contract.get("benchmark_projections", {})
    _require(
        type(projections) is dict and len(projections) <= 8,
        "bounded benchmark projection mapping required",
    )
    for report, references in projections.items():
        _require(
            _text(report)
            and type(references) is dict
            and set(references) == {"panel", "workbench"}
            and all(_text(v) for v in references.values())
            and len({report, *references.values()}) == 3,
            "distinct benchmark, panel and Workbench files required",
        )
    return projections


def evaluate(contract, config, evidence, input_hashes):
    """Recompute conditions from pinned, saved observations; missing values are UNKNOWN."""
    _bytes(contract)
    _require(
        type(contract) is dict
        and (set(contract) - {"benchmark_projections", "execution", "capture"})
        == {
            "schema",
            "claim",
            "claim_kind",
            "scope",
            "excluded_claims",
            "recipe_sha256",
            "inputs",
            "review",
            "dimensions",
        }
        and contract["schema"] == "trainlab.research-adequacy.v1",
        "invalid adequacy contract",
    )
    _require(
        contract["claim_kind"] in CLAIMS
        and _text(contract["claim"])
        and _text(contract["scope"])
        and _text(contract["excluded_claims"]),
        "claim, scope and excluded claims must be explicit",
    )
    _require(contract["recipe_sha256"] == recipe_identity(config), "adequacy recipe changed")
    pointer = config["research_adequacy"]
    expected = {k: v for k, v in input_hashes.items() if k != pointer["file"]}
    _require(
        contract["inputs"] == expected and expected and all(_hash(v) for v in expected.values()),
        "adequacy input closure changed",
    )
    review = contract["review"]
    _require(
        type(review) is dict
        and set(review) == {"author", "reviewer", "basis", "criteria_frozen_before_evaluation"}
        and all(_text(review[k]) for k in ("author", "reviewer", "basis"))
        and review["author"] != review["reviewer"]
        and review["criteria_frozen_before_evaluation"] is True,
        "distinct declared review and prospective criteria required",
    )
    if "capture" in contract:
        capture = contract["capture"]
        _require(
            type(capture) is dict
            and set(capture) == {"artifact", "adapter", "metric"}
            and capture["adapter"] == "pytorch_cpu_classification_v1"
            and capture["metric"] == "accuracy"
            and config["metrics"].get("accuracy") == "max"
            and capture["artifact"] in config["artifacts"],
            "supported capture must retain its declared artifact",
        )
    dimensions = contract["dimensions"]
    _require(
        type(dimensions) is dict and set(dimensions) == set(DIMENSIONS),
        "all four adequacy dimensions are mandatory",
    )
    checks = []
    projected = {}
    for source, references in _projections(contract).items():
        from .benchmark_adequacy import project_benchmark

        _require(
            all(n in expected and n in evidence for n in (source, *references.values())),
            "native benchmark source closure is incomplete",
        )
        projected[source] = project_benchmark(
            evidence[references["panel"]], evidence[source], evidence[references["workbench"]]
        )
        # Never let a caller's favorable count criterion erase native failures.
        checks.append(
            {
                "dimension": "datasets",
                "id": "native_benchmark_admissible:" + source,
                "status": (
                    "MET"
                    if projected[source]["admissible"] == 1
                    else "INADEQUATE"
                    if projected[source]["failed"]
                    else "UNKNOWN"
                ),
                "observed": projected[source]["admissible"],
                "criterion": {"operator": "eq", "threshold": 1, "evidence": source},
            }
        )
    for name in DIMENSIONS:
        dimension = dimensions[name]
        _require(
            type(dimension) is dict
            and set(dimension) == {"configuration", "justification", "limitations", "criteria"}
            and all(_text(dimension[k]) for k in ("configuration", "justification", "limitations")),
            "configuration, claim-specific justification and limits required",
        )
        criteria = dimension["criteria"]
        _require(
            type(criteria) is list and 1 <= len(criteria) <= 32,
            "each dimension needs bounded nonempty criteria",
        )
        ids = set()
        for criterion in criteria:
            _require(
                type(criterion) is dict
                and set(criterion)
                == {"id", "rationale", "evidence", "field", "operator", "threshold"}
                and _text(criterion["id"])
                and criterion["id"] not in ids
                and _text(criterion["rationale"]),
                "invalid or duplicate adequacy criterion",
            )
            ids.add(criterion["id"])
            source, field = criterion["evidence"], criterion["field"]
            _require(
                type(source) is str
                and source in expected
                and _text(field)
                and criterion["operator"] in ("ge", "le", "eq")
                and _finite(criterion["threshold"]),
                "invalid criterion evidence or threshold",
            )
            # Only top-level finite scalar observations are supported, never executable queries.
            document = projected.get(source, evidence.get(source))
            value = document.get(field) if type(document) is dict else None
            status = "UNKNOWN"
            if value is not None:
                _require(_finite(value), "criterion observation must be a finite number, not bool")
                threshold = criterion["threshold"]
                passed = {
                    "ge": value >= threshold,
                    "le": value <= threshold,
                    "eq": value == threshold,
                }[criterion["operator"]]
                status = "MET" if passed else "INADEQUATE"
            checks.append(
                {
                    "dimension": name,
                    "id": criterion["id"],
                    "status": status,
                    "observed": value,
                    "criterion": copy.deepcopy(criterion),
                }
            )
    statuses = {c["status"] for c in checks}
    status = (
        "INADEQUATE"
        if "INADEQUATE" in statuses
        else ("UNKNOWN" if "UNKNOWN" in statuses else "DECLARED_CRITERIA_MET")
    )
    return {
        "schema": "trainlab.research-adequacy-report.v1",
        "status": status,
        "claim": contract["claim"],
        "claim_kind": contract["claim_kind"],
        "checks": checks,
        "contract": copy.deepcopy(contract),
        "evidence": copy.deepcopy(evidence),
        "input_hashes": dict(input_hashes),
        "qualification": "NOT_QUALIFIED",
        "guarantee": "Only supplied numeric criteria and declared byte identities checked; "
        "scientific suitability and reviewer identity are not independently verified.",
    }


def assess(config, root, input_hashes):
    pointer = config["research_adequacy"]
    validate_pointer(pointer)
    _require(pointer["file"] in config["inputs"], "adequacy contract must be a declared input")
    path = contained_file(root, pointer["file"])
    _require(
        digest(path) == pointer["sha256"] == input_hashes[pointer["file"]],
        "adequacy contract changed",
    )
    contract = read_json(path)
    _require(
        type(contract) is dict and type(contract.get("dimensions")) is dict,
        "invalid adequacy contract",
    )
    evidence = {}
    sources = {pointer["file"]: path.read_bytes().decode("utf-8")}
    projections = _projections(contract)
    native_sources = {n for source, refs in projections.items() for n in (source, *refs.values())}
    selected = set(native_sources)
    for dimension in contract.get("dimensions", {}).values():
        if type(dimension) is not dict or type(dimension.get("criteria")) is not list:
            raise LabError("invalid adequacy dimension")
        for criterion in dimension["criteria"]:
            if type(criterion) is not dict or type(criterion.get("evidence")) is not str:
                raise LabError("invalid adequacy criterion")
            selected.add(criterion["evidence"])
    for source in selected:
        _require(
            source in input_hashes and source != pointer["file"],
            "evidence must be a separate declared input",
        )
        p = contained_file(root, source)
        _require(digest(p) == input_hashes[source], "adequacy evidence changed")
        evidence[source] = read_json(p)
        if source not in native_sources:
            _require(
                type(evidence[source]) is dict
                and all(_text(k) and _finite(v) for k, v in evidence[source].items()),
                "adequacy evidence must contain only public finite scalar summaries",
            )
        sources[source] = p.read_bytes().decode("utf-8")
    report = evaluate(contract, config, evidence, input_hashes)
    report["source_texts"] = sources
    _require(
        len((json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        <= 1024 * 1024,
        "adequacy report exceeds 1 MiB limit",
    )
    return report


def verify_report(report, config, input_hashes):
    """Stored status alone never authorizes admission or retrospective reporting."""
    _require(type(report) is dict, "adequacy report required")
    sources = report.get("source_texts")
    _require(type(sources) is dict, "retained adequacy sources required")
    parsed = {}
    for name, source in sources.items():
        _require(
            name in input_hashes
            and type(source) is str
            and hashlib.sha256(source.encode()).hexdigest() == input_hashes[name],
            "retained adequacy source bytes changed",
        )
        parsed[name] = json.loads(source, object_pairs_hook=_pairs, parse_constant=_constant)
    contract_name = config["research_adequacy"]["file"]
    _require(
        contract_name in parsed
        and input_hashes[contract_name] == config["research_adequacy"]["sha256"],
        "retained contract missing or changed",
    )
    contract = parsed.pop(contract_name)
    expected = evaluate(contract, config, parsed, input_hashes)
    expected["source_texts"] = sources
    _require(
        report == expected and expected["status"] == "DECLARED_CRITERIA_MET",
        "adequacy report is altered or not admitted",
    )
    return True
