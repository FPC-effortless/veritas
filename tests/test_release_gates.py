from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.build_release_manifest import main as build_manifest
from tools.build_release_manifest import verify_image_evidence, verify_published_image
from tools.verify_release_gates import (
    REQUIRED_JOBS,
    ReleaseGateError,
    ReleaseGatesPending,
    check_workflows,
    verify_source,
)

HEAD = "a" * 40
REPOSITORY = "example/veritas"
IMAGE_ID = "sha256:" + "d" * 64


class ConstructedGitHub:
    def __init__(self) -> None:
        self.runs = {}
        self.jobs = {}
        for number, (workflow, names) in enumerate(REQUIRED_JOBS.items(), 1):
            run = {
                "id": number,
                "head_sha": HEAD,
                "head_branch": "main",
                "path": f".github/workflows/{workflow}",
                "event": "push",
                "status": "completed",
                "conclusion": "success",
                "run_attempt": 1,
            }
            self.runs[workflow] = [run]
            self.jobs[number] = [
                {"name": name, "status": "completed", "conclusion": "success"}
                for name in names
            ]

    def _request(self, path):
        if "/workflows/" in path:
            workflow = path.split("/workflows/")[1].split("/")[0]
            rows = self.runs[workflow]
            return {"workflow_runs": copy.deepcopy(rows), "total_count": len(rows)}, {}
        run_id = int(path.split("/runs/")[1].split("/")[0])
        if "/jobs?" in path:
            rows = self.jobs[run_id]
            return {"jobs": copy.deepcopy(rows), "total_count": len(rows)}, {}
        for rows in self.runs.values():
            for run in rows:
                if run["id"] == run_id:
                    return copy.deepcopy(run), {}
        raise AssertionError(path)


def test_exact_source_workflows_and_required_jobs_pass():
    evidence = check_workflows(ConstructedGitHub(), REPOSITORY, HEAD)
    assert set(evidence) == set(REQUIRED_JOBS)
    assert evidence["ci.yml"]["run_id"] == 1
    assert "Required" in evidence["ci.yml"]["jobs"]


@pytest.mark.parametrize("workflow", REQUIRED_JOBS)
@pytest.mark.parametrize(
    "mutation", ["missing", "wrong_sha", "wrong_path", "pr_event", "wrong_branch"],
)
def test_missing_or_unrelated_evidence_cannot_authorize_release(workflow, mutation):
    client = ConstructedGitHub()
    if mutation == "missing":
        client.runs[workflow] = []
    else:
        key, value = {
            "wrong_sha": ("head_sha", "b" * 40),
            "wrong_path": ("path", ".github/workflows/unrelated.yml"),
            "pr_event": ("event", "pull_request"),
            "wrong_branch": ("head_branch", "research"),
        }[mutation]
        client.runs[workflow][0][key] = value
    with pytest.raises(ReleaseGatesPending):
        check_workflows(client, REPOSITORY, HEAD)


def test_canonical_tag_dispatch_is_accepted_but_other_tag_is_not():
    client = ConstructedGitHub()
    for rows in client.runs.values():
        rows[0].update(event="workflow_dispatch", head_branch="v1.0.0")
    assert check_workflows(client, REPOSITORY, HEAD, "v1.0.0")
    with pytest.raises(ReleaseGatesPending):
        check_workflows(client, REPOSITORY, HEAD, "v1.1.0")


@pytest.mark.parametrize("target", ["workflow_runs", "jobs"])
@pytest.mark.parametrize("bad_payload", [None, [], {}, {"total_count": True}, {"items": []}])
def test_malformed_workflow_or_job_response_fails_closed(target, bad_payload):
    class MalformedResponse(ConstructedGitHub):
        def _request(self, path):
            if (target == "workflow_runs" and "/workflows/" in path) or (
                target == "jobs" and "/jobs?" in path
            ):
                return bad_payload, {}
            return super()._request(path)

    with pytest.raises(ReleaseGateError):
        check_workflows(MalformedResponse(), REPOSITORY, HEAD)


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", "neutral", None])
def test_newer_unsuccessful_workflow_does_not_reuse_old_success(conclusion):
    client = ConstructedGitHub()
    newer = {**client.runs["ci.yml"][0], "id": 99, "conclusion": conclusion}
    client.runs["ci.yml"].append(newer)
    with pytest.raises(ReleaseGateError):
        check_workflows(client, REPOSITORY, HEAD)


def test_running_latest_attempt_remains_pending():
    client = ConstructedGitHub()
    client.runs["ci.yml"][0].update(status="in_progress", conclusion=None, run_attempt=2)
    with pytest.raises(ReleaseGatesPending):
        check_workflows(client, REPOSITORY, HEAD)


@pytest.mark.parametrize("mutation", ["skipped", "missing", "duplicate", "failed"])
@pytest.mark.parametrize("workflow", REQUIRED_JOBS)
def test_green_workflow_cannot_hide_invalid_required_job(workflow, mutation):
    client = ConstructedGitHub()
    rows = client.jobs[client.runs[workflow][0]["id"]]
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    else:
        rows[0]["conclusion"] = "failure" if mutation == "failed" else "skipped"
    with pytest.raises(ReleaseGateError):
        check_workflows(client, REPOSITORY, HEAD)


def test_rerun_during_job_read_is_not_accepted():
    class MovingAttempt(ConstructedGitHub):
        def _request(self, path):
            payload, headers = super()._request(path)
            if "/jobs?" in path:
                self.runs["ci.yml"][0].update(run_attempt=2, status="queued", conclusion=None)
            return payload, headers

    with pytest.raises(ReleaseGatesPending):
        check_workflows(MovingAttempt(), REPOSITORY, HEAD)


def test_truncated_workflow_history_fails_closed():
    class TruncatedHistory(ConstructedGitHub):
        def _request(self, path):
            payload, headers = super()._request(path)
            if "/workflows/" in path:
                payload["total_count"] = 1001
            return payload, headers

    with pytest.raises(ReleaseGateError):
        check_workflows(TruncatedHistory(), REPOSITORY, HEAD)


def test_latest_failure_on_second_history_page_blocks_release():
    class PagedHistory(ConstructedGitHub):
        def _request(self, path):
            if "/workflows/ci.yml/" in path:
                if path.endswith("&page=1"):
                    rows = [
                        {**self.runs["ci.yml"][0], "id": index}
                        for index in range(1, 101)
                    ]
                else:
                    rows = [{**self.runs["ci.yml"][0], "id": 101, "conclusion": "failure"}]
                return {"workflow_runs": rows, "total_count": 101}, {}
            if path.endswith("/runs/101"):
                return {**self.runs["ci.yml"][0], "id": 101, "conclusion": "failure"}, {}
            return super()._request(path)

    with pytest.raises(ReleaseGateError, match="did not pass"):
        check_workflows(PagedHistory(), REPOSITORY, HEAD)


@pytest.fixture
def image_evidence(tmp_path):
    inspection = tmp_path / "image-inspect.json"
    audit = tmp_path / "image-audit.json"
    sbom = tmp_path / "image-sbom.json"
    manifest = tmp_path / "image-manifest.json"
    inspection.write_text(json.dumps([{
        "Id": IMAGE_ID, "Config": {"Labels": {"org.opencontainers.image.revision": HEAD}},
    }]))
    audit.write_text(json.dumps({
        "SchemaVersion": 2, "ArtifactType": "container_image", "Metadata": {"ImageID": IMAGE_ID},
        "Results": [{"Packages": [{"Name": "constructed-package", "Version": "1"}]}],
    }))
    sbom.write_text(json.dumps({
        "bomFormat": "CycloneDX", "metadata": {"component": {
            "type": "container", "properties": [{
                "name": "aquasecurity:trivy:ImageID", "value": IMAGE_ID,
            }],
        }}, "components": [{"type": "library", "name": "constructed-package", "version": "1"}],
    }))
    manifest.write_text(json.dumps({"schemaVersion": 2, "config": {"digest": IMAGE_ID}}))
    return inspection, audit, sbom, manifest


def test_image_scan_inventory_and_registry_identity_are_bound(image_evidence):
    inspection, audit, sbom, manifest = image_evidence
    result = verify_image_evidence(IMAGE_ID, HEAD, inspection, audit, sbom)
    assert result["image_id"] == IMAGE_ID
    assert result["audit_sha256"] == hashlib.sha256(audit.read_bytes()).hexdigest()
    verify_published_image(IMAGE_ID, manifest)


@pytest.mark.parametrize("target", ["inspection", "source_label", "audit", "sbom", "registry"])
def test_mismatched_image_evidence_is_rejected(image_evidence, target):
    inspection, audit, sbom, manifest = image_evidence
    wrong = "sha256:" + "e" * 64
    if target == "registry":
        manifest.write_text(json.dumps({"schemaVersion": 2, "config": {"digest": wrong}}))
        with pytest.raises(RuntimeError, match="scanned candidate"):
            verify_published_image(IMAGE_ID, manifest)
        return
    if target == "inspection":
        payload = json.loads(inspection.read_text())
        payload[0]["Id"] = wrong
        inspection.write_text(json.dumps(payload))
    elif target == "source_label":
        payload = json.loads(inspection.read_text())
        payload[0]["Config"]["Labels"]["org.opencontainers.image.revision"] = "b" * 40
        inspection.write_text(json.dumps(payload))
    elif target == "audit":
        payload = json.loads(audit.read_text())
        payload["Metadata"]["ImageID"] = wrong
        audit.write_text(json.dumps(payload))
    else:
        payload = json.loads(sbom.read_text())
        payload["metadata"]["component"]["properties"][0]["value"] = wrong
        sbom.write_text(json.dumps(payload))
    with pytest.raises(RuntimeError):
        verify_image_evidence(IMAGE_ID, HEAD, inspection, audit, sbom)


@pytest.mark.parametrize("defect", ["high", "critical", "no_inventory", "empty_sbom"])
def test_image_without_clean_complete_inventory_is_not_publishable(image_evidence, defect):
    inspection, audit, sbom, _ = image_evidence
    if defect == "empty_sbom":
        payload = json.loads(sbom.read_text())
        payload["components"] = []
        sbom.write_text(json.dumps(payload))
    else:
        payload = json.loads(audit.read_text())
        if defect == "no_inventory":
            payload["Results"][0].pop("Packages")
        else:
            payload["Results"][0]["Vulnerabilities"] = [{"Severity": defect.upper()}]
        audit.write_text(json.dumps(payload))
    with pytest.raises(RuntimeError):
        verify_image_evidence(IMAGE_ID, HEAD, inspection, audit, sbom)


@pytest.fixture
def manifest_inputs(tmp_path, monkeypatch, image_evidence):
    inspection, audit, sbom, manifest = image_evidence
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "constructed.whl").write_bytes(b"constructed archive bytes")
    for name in ("LICENSE", "LICENSING.md"):
        (tmp_path / name).write_text("constructed fixture\n")
    identities = tmp_path / "identities.json"
    identities.write_text(json.dumps({"veritas_version": "1.0.0", "release_tag": "v1.0.0"}))
    gates = tmp_path / "gates.json"
    payload = {
        "schema": "veritas.release-gates.v1", "status": "passed", "source_commit": HEAD,
        "tag": "v1.0.0", "repository": REPOSITORY,
        "workflows": check_workflows(ConstructedGitHub(), REPOSITORY, HEAD),
    }
    gates.write_text(json.dumps(payload))
    output = tmp_path / "provenance.json"
    monkeypatch.setattr(sys, "argv", [
        "build_release_manifest.py", "--version", "1.0.0", "--tag", "v1.0.0",
        "--source-commit", HEAD, "--repository", REPOSITORY,
        "--workflow-run", "https://github.com/example/veritas/actions/runs/3",
        "--container-image", "ghcr.io/example/veritas", "--container-digest", "sha256:" + "c" * 64,
        "--dist-dir", str(dist), "--sbom", str(sbom),
        "--container-image-id", IMAGE_ID, "--image-inspection", str(inspection),
        "--image-audit", str(audit), "--published-manifest", str(manifest),
        "--release-gates", str(gates), "--portability-identities", str(identities),
        "--license", str(tmp_path / "LICENSE"),
        "--licensing-policy", str(tmp_path / "LICENSING.md"),
        "--output", str(output),
    ])
    return gates, payload, output


def test_provenance_pins_verified_gate_bytes(manifest_inputs):
    gates, payload, output = manifest_inputs
    build_manifest()
    manifest = json.loads(output.read_text())
    assert manifest["release_gates"]["sha256"] == hashlib.sha256(gates.read_bytes()).hexdigest()
    assert manifest["release_gates"]["workflows"] == payload["workflows"]


@pytest.mark.parametrize("field", ["schema", "status", "source_commit", "tag", "repository"])
def test_provenance_rejects_unrelated_or_failed_gate_evidence(manifest_inputs, field):
    gates, payload, output = manifest_inputs
    payload[field] = "wrong"
    gates.write_text(json.dumps(payload))
    with pytest.raises(RuntimeError, match="exact release source"):
        build_manifest()
    assert not output.exists()


def _git(directory, *arguments):
    return subprocess.check_output(["git", "-C", str(directory), *arguments], text=True).strip()


@pytest.fixture
def release_repo(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "Constructed Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    (tmp_path / "file.txt").write_text("first\n")
    _git(tmp_path, "add", "file.txt")
    _git(tmp_path, "commit", "-m", "first")
    first = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", first)
    return tmp_path, first


def test_main_without_tag_and_matching_annotated_tag_are_accepted(release_repo):
    directory, head = release_repo
    assert verify_source(head, "v1.0.0", "refs/heads/main", directory) is None
    _git(directory, "tag", "-a", "v1.0.0", "-m", "annotated")
    assert verify_source(head, "v1.0.0", "refs/tags/v1.0.0", directory) == head


def test_existing_tag_cannot_identify_different_source(release_repo):
    directory, first = release_repo
    _git(directory, "tag", "v1.0.0")
    (directory / "file.txt").write_text("second\n")
    _git(directory, "commit", "-am", "second")
    second = _git(directory, "rev-parse", "HEAD")
    _git(directory, "update-ref", "refs/remotes/origin/main", second)
    with pytest.raises(ReleaseGateError, match="tag"):
        verify_source(second, "v1.0.0", "refs/heads/main", directory)
    assert second != first


def test_unpublished_branch_cannot_be_released(release_repo):
    directory, head = release_repo
    with pytest.raises(ReleaseGateError, match="ref"):
        verify_source(head, "v1.0.0", "refs/heads/research", directory)
    _git(directory, "checkout", "-b", "research")
    (directory / "file.txt").write_text("research\n")
    _git(directory, "commit", "-am", "research")
    candidate = _git(directory, "rev-parse", "HEAD")
    _git(directory, "tag", "v1.0.0")
    with pytest.raises(ReleaseGateError, match="main"):
        verify_source(candidate, "v1.0.0", "refs/tags/v1.0.0", directory)


def test_tag_event_requires_existing_matching_tag(release_repo):
    directory, head = release_repo
    with pytest.raises(ReleaseGateError, match="tag"):
        verify_source(head, "v1.0.0", "refs/tags/v1.0.0", directory)
    with pytest.raises(ReleaseGateError, match="checkout"):
        verify_source("b" * 40, "v1.0.0", "refs/heads/main", directory)


def test_publication_rechecks_gates_before_registry_write():
    workflow = Path(".github/workflows/release.yml").read_text()
    publish = workflow.split("  publish-release:", 1)[1]
    assert "- release-gates" in publish
    assert publish.index("tools.verify_release_gates") < publish.index("docker/login-action")
    assert "--release-gates release-gates.json" in publish
    assert "release-gates.json" in publish.split("assets=(", 1)[1]
    assert publish.count("uses: docker/build-push-action") == 1
    assert "push: true" not in publish
    assert "load: true" in publish and "push: false" in publish
    assert publish.index("Build candidate image without publishing") < publish.index("trivy-action")
    assert publish.index("trivy convert") < publish.index("docker/login-action")
    assert publish.index("verify_image_evidence") < publish.index("docker push")
    assert '.release-sbom' not in publish
    assert 'docker tag "$IMAGE_ID"' in publish
    assert 'verify_published_image' in publish
