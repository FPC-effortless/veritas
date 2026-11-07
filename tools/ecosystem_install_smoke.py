"""Build/install the four public wheels in a new venv and run the account-free demo."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def command(argv, *, cwd, env):
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f"command failed ({argv[0]}): {result.stderr[-4000:]}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.output.exists() or args.output.is_symlink():
        parser.error("output must be a new directory")
    output.mkdir(parents=True)
    wheels = output / "wheels"
    wheels.mkdir()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    command(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(wheels),
            str(ROOT),
            *[str(ROOT / "integrations" / name) for name in ("forge", "trainlab", "research_lab")],
        ],
        cwd=output,
        env=env,
    )
    archives = sorted(wheels.glob("*.whl"))
    if len(archives) != 4:
        raise RuntimeError("expected four independently built component wheels")
    license_text = (ROOT / "LICENSE").read_bytes()
    for wheel in archives:
        with zipfile.ZipFile(wheel) as bundle:
            if not any(
                name.endswith("/LICENSE") and bundle.read(name) == license_text
                for name in bundle.namelist()
            ):
                raise RuntimeError(f"full root Apache license missing from {wheel.name}")
    environment = output / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    command([str(executable), "-m", "pip", "install", *map(str, archives)], cwd=output, env=env)
    outside = output / "outside-checkout"
    outside.mkdir()
    check = """
import importlib,sys
from pathlib import Path
for name in ('investigation_world','forge_data','trainlab','research_lab'):
    module=importlib.import_module(name)
    if not Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise RuntimeError('component imported outside isolated installation: '+name)
if 'torch' in sys.modules:
    raise RuntimeError('base ecosystem import unexpectedly loaded torch')
"""
    command([str(executable), "-c", check], cwd=outside, env=env)
    script = environment / (
        "Scripts/veritas-ecosystem.exe" if os.name == "nt" else "bin/veritas-ecosystem"
    )
    workspace = outside / "comparison"
    first = json.loads(command([str(script), "run", str(workspace)], cwd=outside, env=env))
    replay = json.loads(command([str(script), "verify", str(workspace)], cwd=outside, env=env))
    if first != replay or first["promotion"]["decision"] != "NOT_PROMOTED":
        raise RuntimeError("installed comparison/reverification differs")
    result = {
        "python": sys.version.split()[0],
        "component_wheels": 4,
        "full_apache_license_texts": 4,
        "installed_outside_source_imports": True,
        "comparison_reverified": True,
        "results": {key: value["mean_reward"] for key, value in first["results"].items()},
        "source_kind": "CONSTRUCTED",
        "scientific_qualification": "NOT_QUALIFIED",
        "package_publication": "NOT_PERFORMED",
    }
    (output / "acceptance.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
