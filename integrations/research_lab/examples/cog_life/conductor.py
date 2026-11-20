"""Exact-scope native stage runner for COG-LIFE (trusted, reviewed local code only)."""

from __future__ import annotations

import argparse
import json
import hashlib
from importlib.util import find_spec
import os
import platform
import re
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

from research_lab.core import Controller
from research_lab.evidence import link, put_node
from trainlab.execution_adequacy import validate_execution
from trainlab.research_adequacy import assess
from trainlab.runner import contained_file, digest, load_config, run_experiment, verify_run

PHASES = {
    "world-check": (),
    "fit": ("world-check",),
    "predict": ("fit",),
    "verify": ("predict",),
}
RUNTIME_SCHEMA = "coglife.runtime.v1"
TOKEN_SCHEMA = "coglife.stage-review.v1"
MAX_TIMEOUT_SECONDS = 900
SAFE_NAME = re.compile(r"cog(?:08[1-9]|090)\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
REVIEW_KEYS = {
    "schema", "decision", "study", "phase", "author", "reviewer",
    "recipe_sha256", "inputs", "input_roles", "runtime", "parent_receipt_sha256",
    "execution_root", "conductor_sha256",
}
ROLE_ALLOW = {
    "world-check": {"code", "protocol", "design", "world_spec", "forge_receipt"},
    "fit": {"code", "protocol", "world_spec", "design", "train", "cal", "forge_receipt"},
    "predict": {"code", "protocol", "world_spec", "request", "fit_artifact", "forge_receipt"},
    "verify": {"code", "protocol", "world_spec", "request", "truth", "prediction_artifact", "forge_receipt"},
}
MIN_ROLES = {
    "world-check": {"code", "protocol", "world_spec"},
    "fit": {"code", "protocol", "train", "cal", "forge_receipt"},
    "predict": {"code", "protocol", "request", "fit_artifact", "forge_receipt"},
    "verify": {"code", "protocol", "truth", "prediction_artifact", "forge_receipt"},
}
CPU_ENV = {
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "CUDA_VISIBLE_DEVICES": "",
}

def package_identity(name):
    spec = find_spec(name)
    if spec is None or spec.origin is None:
        raise ValueError(f"required native package missing: {name}")
    root = Path(spec.origin).resolve(strict=True).parent
    hashes = [(str(p.relative_to(root)), digest(p)) for p in sorted(root.rglob("*"))
              if p.is_file() and p.suffix in {".py", ".so"}]
    if not hashes:
        raise ValueError(f"native package source closure empty: {name}")
    return {"module_root": str(root), "files": len(hashes),
            "tree_sha256": hashlib.sha256(json.dumps(hashes).encode()).hexdigest()}


def runtime():
    exe = Path(sys.executable).resolve(strict=True)
    return {"schema": RUNTIME_SCHEMA, "executable": str(exe),
            "sha256": digest(exe), "python": platform.python_version(),
            "os": platform.platform(), "required_environment": CPU_ENV,
            "ecosystem_packages": {n: package_identity(n)
                                  for n in ("trainlab", "forge_data", "research_lab", "pydantic", "pydantic_core")}}


def decode(raw: bytes):
    def pairs(items):
        out = {}
        for key, val in items:
            if key in out:
                raise ValueError(f"duplicate document key: {key}")
            out[key] = val
        return out
    def constant(value):
        raise ValueError(f"nonfinite metadata: {value}")
    if len(raw) > 1_000_000:
        raise ValueError("metadata exceeds size limit")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def raw_metadata(path: Path):
    with path.open("rb") as stream:
        return stream.read(1_000_001)


def read(path: Path):
    return decode(raw_metadata(path))


def write_once(path: Path, value):
    with path.open("x", encoding="utf-8") as out:
        json.dump(value, out, sort_keys=True, indent=2, allow_nan=False)
        out.write("\n")


def check_name(value: str) -> str:
    if not isinstance(value, str) or not SAFE_NAME.fullmatch(value):
        raise ValueError("invalid study name")
    return value


def provenance(path: Path, phase: str, study: str):
    r = read(path)
    if (r.get("status") != "SUCCEEDED" or r.get("study") != study
            or r.get("phase") != phase or not r.get("verified_trainlab")):
        raise ValueError("predecessor is not a successful exact stage receipt")
    run_dir = (path.parent / "runs" / r["run_id"]).resolve(strict=True)
    if run_dir.parent != (path.parent / "runs").resolve(strict=True):
        raise ValueError("predecessor path outside stage")
    verification = verify_run(run_dir)
    native = contained_file(run_dir, "run.json")
    if not verification["valid"] or digest(native) != r["trainlab_sha256"]:
        raise ValueError("predecessor changed after completion")
    record = read(native)
    if (record.get("name") != f"{study}-{phase}" or record.get("status") != "succeeded"
            or record.get("id") != r["run_id"] or r["adequacy"] != record["research_adequacy"]
            or (phase != "world-check" and record["research_adequacy"] != "EXECUTED_CRITERIA_MET")):
        raise ValueError("native predecessor status mismatch")
    return record


def admission(bundle: Path, review: Path, root: Path, study: str, phase: str):
    if sys.flags.optimize:
        raise ValueError("optimized Python is not allowed")
    check_name(study)
    if phase not in PHASES:
        raise ValueError("unknown phase")
    review_bytes = raw_metadata(review)
    token = decode(review_bytes)
    if set(token) != REVIEW_KEYS or token["schema"] != TOKEN_SCHEMA:
        raise ValueError("unsupported review format")
    if (token["decision"] != "GO" or token["study"] != study
            or token["phase"] != phase
            or not all(isinstance(token[k], str) and token[k].strip()
                       for k in ("author", "reviewer"))
            or token["author"].strip().casefold() == token["reviewer"].strip().casefold()):
        raise ValueError("separate exact independent phase review required")
    if (token["execution_root"] != str(root.resolve())
            or token["conductor_sha256"] != digest(Path(__file__))):
        raise ValueError("execution root or conductor differs from exact review")
    if token["runtime"] != runtime():
        raise ValueError("runtime identity differs from reviewed runtime")
    recipe = contained_file(bundle, "recipe.json")
    if digest(recipe) != token["recipe_sha256"]:
        raise ValueError("recipe differs from reviewed bytes")
    config = load_config(recipe)
    if (config["source_kind"] != "CONSTRUCTED" or config["budget"] != {"cpu": 1}
            or config["timeout_seconds"] > MAX_TIMEOUT_SECONDS
            or config["name"] != f"{study}-{phase}"
            or config["execution_purpose"] != ("engineering_diagnostic" if phase == "world-check" else "research")
            or any(not re.fullmatch(r"[a-zA-Z0-9_./-]+", n)
                   or "test" in n.lower().split("/") for n in config["inputs"])):
        raise ValueError("recipe outside no-paid constructed cohort scope")
    cmd = config["command"]
    if (len(cmd) != 3 or not Path(cmd[0]).is_absolute() or Path(cmd[0]).resolve() != Path(sys.executable).resolve()
            or cmd[2] != phase or not cmd[1].endswith(".py")):
        raise ValueError("expected explicit local Python worker and phase")
    inputs = {n: digest(contained_file(bundle, n)) for n in config["inputs"]}
    if inputs != token["inputs"]:
        raise ValueError("input manifest differs from reviewed bytes")
    roles = token["input_roles"]
    if (not isinstance(roles, dict) or set(inputs) != set(roles)
            or roles.get(cmd[1]) != "code"
            or not MIN_ROLES[phase] <= set(roles.values()) <= ROLE_ALLOW[phase]):
        raise ValueError("unapproved roles in stage closure")
    for key, sha in token["parent_receipt_sha256"].items():
        if key not in PHASES[phase] or not SHA.fullmatch(sha):
            raise ValueError("unexpected predecessor")
    if set(token["parent_receipt_sha256"]) != set(PHASES[phase]):
        raise ValueError("incomplete predecessor binding")
    for key in PHASES[phase]:
        prior_study = "cog081" if key == "world-check" else study
        prior = root / prior_study / key / "stage-receipt.json"
        if digest(prior) != token["parent_receipt_sha256"][key]:
            raise ValueError("predecessor receipt differs from reviewed bytes")
        native = provenance(prior, key, prior_study)
        if key == "world-check":
            continue
        expected_role = "fit_artifact" if phase == "predict" else "prediction_artifact"
        seen = {n: inputs[n] for n, v in roles.items() if v == expected_role}
        if not seen or any(native["artifacts"].get(n) != h for n, h in seen.items()):
            raise ValueError("staged artifact name or bytes not from the verified predecessor")
    if phase != "world-check" and not config.get("research_adequacy"):
        raise ValueError("missing native research adequacy contract")
    assessment = assess(config, bundle, inputs) if config.get("research_adequacy") else None
    if assessment is not None and assessment["status"] != "DECLARED_CRITERIA_MET":
        raise ValueError("native adequate scope did not pass declaration")
    if assessment is not None and phase != "world-check":
        validate_execution(assessment["contract"], config)
    return config, token, inputs, review_bytes


@contextmanager
def worker_environment():
    # TrainLab passes its environment to trusted operator-selected subprocesses.
    # Do not forward ambient secrets or repository import paths to reviewed workers.
    # This is a single-process conductor, not an isolation/security sandbox.
    before = dict(os.environ)
    os.environ.clear()
    os.environ.update({k: before[k] for k in ("PATH", "LANG", "LC_ALL", "TZ") if k in before})
    os.environ.update(CPU_ENV)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(before)


def launch(bundle: Path, review: Path, execution: Path, study: str, phase: str):
    config, token, inputs, review_bytes = admission(bundle, review, execution, study, phase)
    stage = execution / study / phase
    stage.mkdir(parents=True, mode=0o700, exist_ok=False)
    staged = stage / "closure"
    record = {"study": study, "phase": phase, "status": "FAILED", "verified_trainlab": False}
    lab = None
    node_id = f"{study}.{phase}"
    try:
        staged.mkdir(mode=0o700)
        with (stage / "review.json").open("xb") as out:
            out.write(review_bytes)
        for name in ("recipe.json", *inputs):
            destination = staged / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(contained_file(bundle, name), destination)
        if (digest(staged / "recipe.json") != token["recipe_sha256"]
                or any(digest(staged / n) != sha for n, sha in inputs.items())):
            raise ValueError("inputs changed during staging")
        lab = Controller(execution / "ledger")
        lab.program("cog-life-081-090", "Constructed lifetime studies", 36_000, 0)
        put_node(lab, node_id + ".review", "experiment",
                 {"sha256": hashlib.sha256(review_bytes).hexdigest()})
        with worker_environment():
            result = run_experiment(staged / "recipe.json", stage / "runs", log_limit=512 * 1024)
        native = stage / "runs" / result["id"]
        verdict = verify_run(native)
        record.update(run_id=result["id"], verified_trainlab=verdict["valid"],
                      trainlab_sha256=digest(native / "run.json"),
                      native_status=result["status"], adequacy=result["research_adequacy"])
        if (result["status"] == "succeeded" and verdict["valid"]
                and (phase == "world-check" or result["research_adequacy"] == "EXECUTED_CRITERIA_MET")):
            record["status"] = "SUCCEEDED"
    except BaseException as exc:
        record["error_type"] = type(exc).__name__
        raise
    finally:
        write_once(stage / "stage-receipt.json", record)
        if lab is not None:
            put_node(lab, node_id + ".receipt", "evidence", record)
            link(lab, node_id + ".receipt", "tests", node_id + ".review")
    if record["status"] != "SUCCEEDED":
        raise RuntimeError("stage failed; retained receipt; no automatic rerun")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("runtime", "preflight", "run"))
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--execution", type=Path)
    parser.add_argument("--study")
    parser.add_argument("--phase", choices=tuple(PHASES))
    args = parser.parse_args()
    if args.mode == "runtime":
        print(json.dumps(runtime(), sort_keys=True))
        return
    if None in (args.bundle, args.review, args.execution, args.study, args.phase):
        parser.error("all exact stage paths and selectors are required")
    values = (args.bundle, args.review, args.execution, args.study, args.phase)
    if args.mode == "preflight":
        admission(*values)
        print("reviewed declared plan only; no execution")
    else:
        print(json.dumps(launch(*values), sort_keys=True))


if __name__ == "__main__":
    main()
