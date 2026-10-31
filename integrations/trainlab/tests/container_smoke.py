"""Constructed installed-image, hardening, persistence and restore acceptance."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import time
import uuid


def docker(*arguments, **kwargs):
    environment = os.environ.copy()
    for name in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    ):
        environment.pop(name, None)
    return subprocess.check_output(
        ["docker", "--host=unix:///var/run/docker.sock", *arguments],
        env=environment,
        text=True,
        **kwargs,
    ).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    suffix = uuid.uuid4().hex[:10]
    volume = "trainlab-test-" + suffix
    container = "trainlab-test-" + suffix
    password = secrets.token_urlsafe(24)
    os.environ["TRAINLAB_TEST_PASSWORD"] = password
    docker("volume", "create", volume)
    try:
        setup = """
import os,shutil,subprocess,sys
from pathlib import Path
from trainlab.production import create_credentials
assert os.getuid() == 10001
create_credentials(Path('/data/auth.json'),'operator',os.environ['TRAINLAB_TEST_PASSWORD'])
subprocess.run([sys.executable,'/opt/forge/examples/dataset_quickstart.py',
    '--output','/data/forge-demo','--run'],check=True)
shutil.copytree('/data/forge-demo/runs','/data/runs')
"""
        docker(
            "run",
            "--rm",
            "--network",
            "none",
            "-e",
            "TRAINLAB_TEST_PASSWORD",
            "-v",
            volume + ":/data",
            "--entrypoint",
            "python",
            args.image,
            "-c",
            setup,
        )
        docker(
            "run",
            "-d",
            "--name",
            container,
            "--network",
            "none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=128",
            "--memory=256m",
            "--cpus=1",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m,uid=10001,gid=10001",
            "-e",
            "TRAINLAB_TEST_PASSWORD",
            "-v",
            volume + ":/data",
            "-v",
            volume + ":/recipes:ro",
            args.image,
            "serve",
            "--production",
            "--auth-file",
            "/data/auth.json",
            "--runs",
            "/data/runs",
            "--experiments",
            "/recipes/forge-demo",
            "--forge-workspace",
            "/data/forge-workspace",
        )
        deadline = time.monotonic() + 30
        while True:
            try:
                docker(
                    "exec",
                    container,
                    "python",
                    "-c",
                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz').read()",
                    stderr=subprocess.DEVNULL,
                )
                break
            except subprocess.CalledProcessError:
                if time.monotonic() > deadline:
                    raise AssertionError("container health failed startup") from None
                time.sleep(0.2)
        inspect = json.loads(docker("inspect", container))[0]
        assert inspect["Config"]["User"] == "10001:10001"
        assert inspect["HostConfig"]["ReadonlyRootfs"]
        assert inspect["HostConfig"]["PidsLimit"] == 128
        assert inspect["HostConfig"]["Memory"] == 256 * 1024 * 1024
        exercise = """
import base64,json,os,time,urllib.request,urllib.error
base='http://127.0.0.1:8765'
auth='Basic '+base64.b64encode(('operator:'+os.environ['TRAINLAB_TEST_PASSWORD']).encode()).decode()
def request(path,body=None,token=None,authenticated=True):
    headers={'Authorization':auth} if authenticated else {}
    if body is not None:
        headers.update({'Content-Type':'application/json','X-TrainLab-Token':token})
    req=urllib.request.Request(base+path,
        data=None if body is None else json.dumps(body).encode(),headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.load(r)
try:
    request('/api/state',authenticated=False)
    raise AssertionError('anonymous access allowed')
except urllib.error.HTTPError as e:
    assert e.code == 401
state=request('/api/state'); assert len(state['runs']) == 2
request('/api/run',{'experiment':'linear.json'},state['token'])
for _ in range(150):
    state=request('/api/state')
    if len(state['runs']) == 3 and not state['busy']: break
    time.sleep(.1)
assert len(state['runs']) == 3 and all(r['status']=='succeeded' for r in state['runs'])
for run in state['runs']: assert request('/api/verify?id='+run['id'])['valid']
print(json.dumps({'anonymous_denied':True,'verified_runs':len(state['runs'])}))
forge=request('/api/forge/state')
source=request('/api/forge/example')
request('/api/forge/releases',source,forge['token'])
for _ in range(150):
    forge=request('/api/forge/state')
    if len(forge['releases'])==1 and not forge['busy']: break
    time.sleep(.1)
assert len(forge['releases'])==1 and forge['releases'][0]['records']==30
print('PASS: installed Forge GUI creates a verified dataset inside hardened container')
"""
        print(docker("exec", container, "python", "-c", exercise))
        docker("stop", "--time", "15", container)
        docker("start", container)
        time.sleep(1)
        print(docker("exec", container, "trainlab", "health", "--runs", "/data/runs"))
        docker("stop", "--time", "15", container)
        restore = """
from pathlib import Path
from trainlab.operations import backup_runs,restore_runs
from trainlab.runner import list_runs,verify_run
b=backup_runs(Path('/data/runs'),Path('/data/backup.zip'))
r=restore_runs(Path('/data/backup.zip'),Path('/data/restored'),expected_sha256=b['sha256'])
assert r['runs']==3
assert all(verify_run(Path('/data/restored')/run['id'])['valid']
    for run in list_runs(Path('/data/restored')))
print('PASS: offline backup and clean restore of all three verified container runs')
"""
        print(
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "-v",
                volume + ":/data",
                "--entrypoint",
                "python",
                args.image,
                "-c",
                restore,
            )
        )
        print(
            "PASS: non-root/read-only/resource-limited image; Forge handoff; auth; "
            "recipe launch; restart persistence; backup/restore"
        )
    finally:
        try:
            docker("rm", "-f", container, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            pass
        docker("volume", "rm", volume)
        os.environ.pop("TRAINLAB_TEST_PASSWORD", None)


if __name__ == "__main__":
    main()
