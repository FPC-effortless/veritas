from __future__ import annotations

import json
from pathlib import Path

from investigation_world.portability.evidence import PortableQualificationEvidence
from investigation_world.portability.models import PortableEnvironmentManifest
from investigation_world.portability.package import PortablePackageBuildResult, write_portable_package
from investigation_world.portability.sre_private import SREPrivatePortableTask


def _render_taskset_module() -> str:
    return '''from __future__ import annotations

import json
from pathlib import Path

import verifiers.v1 as vf


_ALLOWED = {"regression", "infrastructure", "capacity", "transient"}


def _parse_prediction(raw: object) -> str | None:
    text = str(raw or "").strip()
    payload = None
    try:
        candidate = json.loads(text)
        if isinstance(candidate, dict):
            payload = candidate
    except json.JSONDecodeError:
        left = text.find("{")
        right = text.rfind("}")
        if left >= 0 and right > left:
            try:
                candidate = json.loads(text[left : right + 1])
                if isinstance(candidate, dict):
                    payload = candidate
            except json.JSONDecodeError:
                pass
    value = str(payload.get("causal_class", "")) if payload else text
    normalized = value.strip().casefold().strip("\\\"'` .")
    return normalized if normalized in _ALLOWED else None


class SREData(vf.TaskData):
    expected_causal_class: str
    portable_task_id: str


class SRETask(vf.Task[SREData, vf.State, vf.TaskConfig]):
    @vf.reward
    async def causal_classification(self, trace: vf.Trace) -> float:
        prediction = _parse_prediction(trace.last_reply)
        return float(prediction == self.data.expected_causal_class)


class SRETaskset(vf.Taskset[SRETask, vf.TasksetConfig]):
    def load(self) -> list[SRETask]:
        records = json.loads(
            Path(__file__).with_name("private_tasks.json").read_text(encoding="utf-8")
        )
        return [
            SRETask(
                SREData(
                    idx=index,
                    prompt=record["prompt"],
                    expected_causal_class=record["expected_causal_class"],
                    portable_task_id=record["task_id"],
                ),
                self.config.task,
            )
            for index, record in enumerate(records)
        ]
'''


def _render_init_module() -> str:
    return '''from veritas_sre_prime.taskset import SRETaskset

__all__ = ["SRETaskset"]
'''


def _render_pyproject() -> str:
    return '''[project]
name = "veritas-sre-prime-v1"
version = "0.11.0"
description = "Generated Prime Verifiers v1 taskset for the sealed Veritas SRE Evaluation Pack v1"
requires-python = ">=3.12,<3.13"
dependencies = ["verifiers>=0.2,<0.3"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["veritas_sre_prime"]
include = ["portable_manifest.json", "qualification_evidence.json"]

[tool.verifiers.eval]
num_examples = 30
rollouts_per_example = 1
'''


def _render_readme(manifest: PortableEnvironmentManifest) -> str:
    return f'''# {manifest.sku} — Prime Verifiers v1 export

Generated from portable manifest `{manifest.manifest_id}`.

This is an **operator-private taskset package**. The generated `private_tasks.json` contains hidden
scoring truth and must remain restricted. `qualification_evidence.json` is buyer-safe and contains
only aggregate qualification evidence and immutable release identities.

The package exports `SRETaskset` using `verifiers.v1`, separating the taskset (what is solved and
how it is scored) from the harness/runtime chosen by the evaluator or trainer.
'''


def build_prime_sre_package(
    output_dir: Path,
    *,
    manifest: PortableEnvironmentManifest,
    private_tasks: list[SREPrivatePortableTask],
    qualification_evidence: PortableQualificationEvidence | None = None,
) -> PortablePackageBuildResult:
    if not private_tasks:
        raise ValueError("Prime private SRE package requires at least one private task")
    if len(private_tasks) != manifest.taskset.private_task_count:
        raise ValueError(
            "Prime private task count must match the sealed private count declared by the manifest"
        )
    if qualification_evidence is not None and qualification_evidence.release != manifest.release:
        raise ValueError("Prime qualification evidence release identity must match portable manifest")

    private_payload = [record.model_dump(mode="json") for record in private_tasks]
    files = {
        "portable_manifest.json": json.dumps(
            manifest.model_dump(mode="json"), indent=2, sort_keys=True
        )
        + "\n",
        "pyproject.toml": _render_pyproject(),
        "README.md": _render_readme(manifest),
        "veritas_sre_prime/__init__.py": _render_init_module(),
        "veritas_sre_prime/taskset.py": _render_taskset_module(),
        "veritas_sre_prime/private_tasks.json": json.dumps(
            private_payload, indent=2, sort_keys=True
        )
        + "\n",
    }
    if qualification_evidence is not None:
        files["qualification_evidence.json"] = json.dumps(
            qualification_evidence.model_dump(mode="json"), indent=2, sort_keys=True
        ) + "\n"
    return write_portable_package(
        output_dir,
        adapter="prime-verifiers-v1",
        manifest_id=manifest.manifest_id,
        files=files,
    )
