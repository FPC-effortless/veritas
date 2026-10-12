from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from investigation_world.authoring import EnvironmentBuilder
from investigation_world.operational import ActionKind, WorldDomain

from ._common import execute_episode, require_perfect


def build_environment(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    current = str(payload["status"])
    expected = str(payload["expected_status"])
    return (
        EnvironmentBuilder(
            name="file-backed",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Reconcile a file-backed job record to its expected status.",
            role="file_workflow_operator",
        )
        .system("FILE")
        .action(
            "reconcile_file",
            kind=ActionKind.WRITE,
            system="FILE",
            description="Reconcile the file-backed status.",
            parameters=("path",),
        )
        .record(
            "file-rec-001",
            system="FILE",
            record_type="json_record",
            object_id="JOB-FILE",
            fields={"path": path.name, "status": current, "expected_status": expected},
            searchable_text=f"file job status {current} expected {expected}",
        )
        .initial_state(**{"JOB-FILE.status": current})
        .target("JOB-FILE", "status", expected)
        .transition(
            "reconcile_file",
            required_parameters={"path": path.name},
            set_state={"JOB-FILE.status": expected},
            observable_result={"written": True},
        )
        .require_action("reconcile_file")
        .require_evidence("file-rec-001")
        .metadata(public={"backend": "json_file"})
        .success("The file-backed state is reconciled.")
        .build()
    )


def run_demo():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "job.json"
        path.write_text(
            json.dumps({"status": "queued", "expected_status": "ready"}),
            encoding="utf-8",
        )
        result = execute_episode(
            build_environment(path),
            actions=(("reconcile_file", {"path": path.name}),),
            evidence_ids=("file-rec-001",),
            claimed_state={"JOB-FILE.status": "ready"},
            conclusion="The file-backed record was reconciled.",
        )
    return require_perfect(result)
