"""Optional offline, non-root PyTorch image and independent export-load acceptance."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
import uuid
from pathlib import Path

# Reuse the existing managed-daemon selector and preserve proxy/registry settings.
docker = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tests/container_smoke.py"))[
    "docker"
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    prefix = "trainlab-torch-" + uuid.uuid4().hex[:10]
    volume = prefix + "-data"
    containers = [prefix + "-fit", prefix + "-load"]
    docker("volume", "create", volume)
    try:
        isolation = [
            "--no-healthcheck",
            "--network",
            "none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=128",
            "--memory=2g",
            "--cpus=2",
            "--shm-size=128m",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=512m,uid=10001,gid=10001",
            "--entrypoint",
            "python",
        ]
        fit = """
import subprocess,sys
from pathlib import Path
from trainlab.runner import list_runs
result=subprocess.run([sys.executable,'/opt/forge/examples/torch_workflow.py',
    '--output','/data/acceptance'])
if result.returncode:
    root=Path('/data/acceptance/runs')
    for run in list_runs(root):
        if run['status']!='succeeded':
            path=root/run['id']/'stderr.log'
            if path.is_file():
                print(path.read_text(errors='replace')[-8192:],file=sys.stderr)
raise SystemExit(result.returncode)
"""
        result = json.loads(
            docker(
                "run",
                "--name",
                containers[0],
                *isolation,
                "-v",
                volume + ":/data",
                args.image,
                "-c",
                fit,
            )
        )
        assert result["cuda"] == "NOT_RUN" and len(result["run_ids"]) == 8
        # Fresh container: no recipe code or eager checkpoint is needed to load
        # the exported graph and check its previously pinned reference outputs.
        load = """
import importlib.metadata,importlib.util,json,os,torch
from pathlib import Path
from trainlab.runner import list_runs,read_json,verify_run
assert os.getuid()==10001
assert importlib.util.find_spec('pip') is None
assert importlib.util.find_spec('ensurepip') is None
assert importlib.metadata.version('torch')==str(torch.__version__)
inventory=Path('/lib/apk/db/installed').read_text().splitlines()
assert 'P:python-3.12-base' in inventory and any(p.startswith('P:glibc') for p in inventory)
assert torch.version.cuda is None
root=Path('/data/acceptance/runs')
runs=list_runs(root)
assert all(verify_run(root/run['id'])['valid'] for run in runs)
run=next(run for run in runs if run['workload']['kind']=='export')
output=root/run['id']/'output'
reference=read_json(output/'reference.json')
assert reference['source']=='CONSTRUCTED_ONLY'
module=torch.export.load(output/'model.pt2').module()
with torch.no_grad():
    actual=module(torch.tensor(reference['inputs']))
assert torch.isfinite(actual).all().item()
error=(actual-torch.tensor(reference['predictions'])).abs().max().item()
assert error<=1e-6,error
print(json.dumps({'uid':os.getuid(),'torch_version':str(torch.__version__),
 'verified_runs':len(runs),'export_max_error':error,'qualification':'NOT_QUALIFIED'}))
"""
        loaded = json.loads(
            docker(
                "run",
                "--name",
                containers[1],
                *isolation,
                "-v",
                volume + ":/data:ro",
                args.image,
                "-c",
                load,
            )
        )
        for container in containers:
            observed = json.loads(docker("inspect", container))[0]
            assert observed["Config"]["User"] == "10001:10001"
            assert observed["HostConfig"]["NetworkMode"] == "none"
            assert observed["HostConfig"]["ReadonlyRootfs"]
            assert observed["HostConfig"]["PidsLimit"] == 128
            assert observed["HostConfig"]["Memory"] == 2 * 1024**3
        print(
            json.dumps(
                {
                    "source": "CONSTRUCTED_ONLY",
                    "offline_containers": 2,
                    "workflow": result,
                    "fresh_export_load": loaded,
                },
                sort_keys=True,
            )
        )
    finally:
        for container in containers:
            try:
                docker("rm", "-f", container, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                pass
        docker("volume", "rm", volume)


if __name__ == "__main__":
    main()
