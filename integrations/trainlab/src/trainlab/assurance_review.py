"""Authenticate an explicit review of one exact, independently selected assurance.

Signature validity is necessary, not scientific qualification or promotion. The
caller must recompute capture, replay and claim prerequisites before supplying the
expected evidence hash. This layer never executes evidence or selects its own trust.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from pathlib import Path

from .diagnostic_bundle import _parse, _verified
from .prediction_artifacts import _hash, _require, _text
from .runner import LabError, _finite
from .signed_bundle_review import verify_review

SCHEMA = "research_lab.claim-assurance.v1"
REPLAY_SCOPE = "CLEAN_DIRECTORY_SAME_HOST_AND_RUNTIME"
EVALUATION_SCOPE = "TRAIN_ONLY_OBSERVED_CLASSIFICATION"
MAX_MATERIAL_BYTES = 8 * 1024 * 1024
MAX_ASSURANCE_BYTES = 16 * 1024 * 1024
_RUN_FIELDS = {
    "task_id",
    "run_id",
    "record_sha256",
    "contract_sha256",
    "capture_sha256",
    "execution_sha256",
}


def _assurance(document, author):
    """Validate binding shape, not the truth or scientific meaning of synthesis."""
    _require(
        type(document) is dict
        and set(document)
        == {
            "schema",
            "status",
            "claim",
            "evidence_pin",
            "synthesis",
            "runs",
            "replay_scope",
            "author",
            "scientific_qualification",
            "review_materials",
        }
        and document["schema"] == SCHEMA
        and document["status"] == "TESTED"
        and document["author"] == author
        and document["scientific_qualification"] == "NOT_QUALIFIED"
        and document["replay_scope"] == REPLAY_SCOPE
        and _hash(document["evidence_pin"])
        and type(document["synthesis"]) is dict
        and document["synthesis"],
        "tested claim-assurance evidence with capture/replay scope required",
    )
    claim = document["claim"]
    _require(
        type(claim) is dict
        and set(claim)
        == {
            "protocol_id",
            "protocol_sha256",
            "scope",
            "metric",
            "direction",
            "minimum_effect",
            "seeds",
            "conclusion",
            "evaluation_scope",
        }
        and all(_text(claim[key]) for key in ("protocol_id", "scope", "metric", "conclusion"))
        and claim["evaluation_scope"] == EVALUATION_SCOPE
        and _hash(claim["protocol_sha256"])
        and claim["direction"] in ("min", "max")
        and _finite(claim["minimum_effect"])
        and claim["minimum_effect"] >= 0,
        "exact claim, protocol, criterion and conclusion required",
    )
    seeds = claim["seeds"]
    _require(
        type(seeds) is list
        and 1 <= len(seeds) <= 100
        and all(type(seed) is int and 0 <= seed <= 2**32 - 1 for seed in seeds)
        and len(set(seeds)) == len(seeds),
        "distinct declared claim seeds required",
    )
    runs = document["runs"]
    _require(
        type(runs) is list and 1 <= len(runs) <= 1000, "bounded nonempty assured run list required"
    )
    tasks, identities = set(), set()
    for run in runs:
        _require(
            type(run) is dict
            and set(run) == _RUN_FIELDS
            and _text(run["task_id"])
            and type(run["run_id"]) is str
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run["run_id"])
            and run["run_id"] != "source"
            and all(_hash(run[key]) for key in _RUN_FIELDS - {"task_id", "run_id"}),
            "each assured run requires record, contract, capture and execution identities",
        )
        _require(
            run["task_id"] not in tasks and run["run_id"] not in identities,
            "assured tasks and run identities must be unique",
        )
        tasks.add(run["task_id"])
        identities.add(run["run_id"])

    materials = document["review_materials"]
    _require(
        type(materials) is dict and 7 <= len(materials) <= 8192,
        "bounded substantive review materials required",
    )
    decoded, total = {}, 0
    for name, item in materials.items():
        _require(
            type(name) is str
            and 0 < len(name) <= 500
            and re.fullmatch(r"[A-Za-z0-9_./-]+", name)
            and not name.startswith("/")
            and all(part not in ("", ".", "..") for part in name.split("/"))
            and type(item) is dict
            and set(item) == {"sha256", "base64"}
            and _hash(item["sha256"])
            and type(item["base64"]) is str
            and len(item["base64"]) <= 4 * ((MAX_MATERIAL_BYTES + 2) // 3),
            "safe material path, exact hash and bounded base64 required",
        )
        try:
            raw = base64.b64decode(item["base64"], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise LabError("invalid strict material base64") from exc
        _require(
            base64.b64encode(raw).decode("ascii") == item["base64"],
            "canonical material base64 required",
        )
        total += len(raw)
        _require(total <= MAX_MATERIAL_BYTES, "review materials exceed aggregate 8 MiB limit")
        _require(
            hashlib.sha256(raw).hexdigest() == item["sha256"],
            "review material source bytes changed",
        )
        decoded[name] = raw
    _require(
        any(name.startswith("source/") for name in materials),
        "complete declared source snapshot materials required",
    )
    expected = {name for name in materials if name.startswith("source/")}
    for run in runs:
        prefix = run["run_id"] + "/"
        roles = {
            "run.json": "record_sha256",
            "contract.json": "contract_sha256",
            "capture.json": "capture_sha256",
            "execution_adequacy.json": "execution_sha256",
        }
        required = {prefix + name for name in (*roles, "experiment.json", "plan.json")}
        _require(required <= set(materials), "assured run is missing substantive review material")
        expected.update(required)
        for name in required:
            _require(
                type(_parse(decoded[name])) is dict, "run review material must be a JSON object"
            )
        for filename, field in roles.items():
            _require(
                materials[prefix + filename]["sha256"] == run[field],
                "assured run/material hash correspondence changed",
            )
        record = _parse(decoded[prefix + "run.json"])
        _require(record.get("id") == run["run_id"], "assured record identity mismatch")
        for section in ("inputs", "files", "artifacts"):
            entries = record.get(section)
            _require(
                type(entries) is dict and entries and len(entries) <= 256,
                "record must retain bounded input/file/artifact closure",
            )
            for name, pin in entries.items():
                _require(
                    type(name) is str
                    and name
                    and not name.startswith("/")
                    and re.fullmatch(r"[A-Za-z0-9_./-]+", name)
                    and all(part not in ("", ".", "..") for part in name.split("/"))
                    and _hash(pin),
                    "invalid recorded material path or hash",
                )
                key = (
                    "source/" + name
                    if section == "inputs"
                    else prefix + ("output/" if section == "artifacts" else "") + name
                )
                _require(
                    key in materials and materials[key]["sha256"] == pin,
                    "recorded source/file/artifact material missing or changed",
                )
                expected.add(key)
        _require(
            materials[prefix + "plan.json"]["sha256"]
            == record["files"].get("research_adequacy.json"),
            "plan alias lacks recorded binding",
        )
        _require(
            materials[prefix + "experiment.json"]["sha256"]
            == record["files"].get("experiment.json"),
            "recipe lacks recorded binding",
        )
        _require(
            run["capture_sha256"] in record["artifacts"].values()
            and record["files"].get("execution_adequacy.json") == run["execution_sha256"],
            "capture and execution evidence lack recorded bindings",
        )
        recipe = _parse(decoded[prefix + "experiment.json"])
        pointer = recipe.get("research_adequacy")
        _require(
            type(pointer) is dict
            and _text(pointer.get("file"))
            and pointer.get("sha256") == run["contract_sha256"]
            and record["inputs"].get(pointer["file"]) == run["contract_sha256"],
            "contract lacks recipe/input binding",
        )
        plan = _parse(decoded[prefix + "plan.json"])
        contract = _parse(decoded[prefix + "contract.json"])
        _require(plan.get("contract") == contract, "reviewed plan and criteria contract differ")
    _require(set(materials) == expected, "unmapped review material is unsupported")


def verify_assurance_review(
    root,
    manifest_sha256,
    envelope_path,
    *,
    expected_evidence_sha256,
    author,
    signer,
    trusted_signers,
    trusted_signers_sha256,
    assurance_pack_id="research-assurance",
    assurance_finding_id="research-assurance",
):
    """Verify an explicit accept over exact expected claim/criteria/run evidence.

    The expected hash and trust pin must come from the consumer, not the imported
    bundle. Author/signer labels must differ; that does not prove different humans
    or sessions control the keys. A valid bounded negative conclusion is allowed.
    """
    _require(
        _hash(expected_evidence_sha256)
        and _text(author)
        and _text(signer)
        and author != signer
        and _text(assurance_pack_id)
        and _text(assurance_finding_id),
        "external evidence pin and distinct expected author/reviewer required",
    )
    root = Path(root)
    _require(
        not Path(trusted_signers).resolve().is_relative_to(root.resolve()),
        "recipient trust must be supplied separately from the reviewed bundle",
    )
    snapshot, _ = _verified(root, manifest_sha256)
    bundle = _parse(snapshot["bundle.json"])
    _require(
        type(bundle) is dict
        and bundle.get("schema") == "trainlab.diagnostic-bundle.v1"
        and bundle.get("scientific_qualification") == "NOT_QUALIFIED",
        "diagnostic assurance bundle required",
    )
    packs = bundle.get("packs")
    _require(
        type(packs) is list
        and sum(
            type(pack) is dict
            and pack.get("id") == assurance_pack_id
            and pack.get("version") == "1"
            for pack in packs
        )
        == 1,
        "exact assurance pack version required",
    )
    findings = bundle.get("findings")
    _require(
        type(findings) is list
        and 1 <= len(findings) <= 200
        and all(type(finding) is dict and _text(finding.get("id")) for finding in findings)
        and len({finding["id"] for finding in findings}) == len(findings),
        "bounded unique bundle findings required",
    )
    matches = [finding for finding in findings if finding["id"] == assurance_finding_id]
    _require(len(matches) == 1, "expected assurance finding absent")
    finding = matches[0]
    evidence = finding.get("evidence")
    _require(
        finding.get("pack_id") == assurance_pack_id
        and finding.get("kind") == "conclusion"
        and finding.get("status") == "TESTED"
        and type(evidence) is dict
        and evidence.get("pointer") == []
        and evidence.get("sha256") == expected_evidence_sha256
        and type(evidence.get("artifact")) is str
        and evidence["artifact"].startswith("evidence/")
        and evidence["artifact"] in snapshot,
        "assurance finding must bind the entire exact expected evidence document",
    )
    raw = snapshot[evidence["artifact"]]
    _require(
        len(raw) <= MAX_ASSURANCE_BYTES
        and hashlib.sha256(raw).hexdigest() == expected_evidence_sha256,
        "assurance source byte identity or size mismatch",
    )
    document = _parse(raw)
    _assurance(document, author)
    authenticated = verify_review(
        root,
        manifest_sha256,
        envelope_path,
        signer=signer,
        trusted_signers=trusted_signers,
        trusted_signers_sha256=trusted_signers_sha256,
    )
    _require(
        authenticated["receipt"]["verdict"] == "accept",
        "authenticated explicit accept required; signature validity alone is insufficient",
    )
    return {
        "schema": "trainlab.assurance-review.v1",
        "status": "AUTHENTICATED_ACCEPT",
        "manifest_sha256": manifest_sha256,
        "evidence_sha256": expected_evidence_sha256,
        "pack_id": assurance_pack_id,
        "finding_id": assurance_finding_id,
        "author": author,
        "signer": signer,
        "claim": document["claim"],
        "evidence_pin": document["evidence_pin"],
        "trusted_signers_sha256": trusted_signers_sha256,
        "signed_receipt": authenticated["receipt"],
        "scientific_qualification": "NOT_QUALIFIED",
        "automatic_admission": False,
        "scope": "Exact bundle/evidence bytes and explicit trusted-key accept authenticated; "
        "capture/replay correctness, scientific truth and human/session independence "
        "must be verified separately by the consuming admission policy.",
    }
