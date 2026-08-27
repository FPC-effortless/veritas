from __future__ import annotations

import json
from pathlib import Path

from investigation_world.portability.evidence import PortableQualificationEvidence
from investigation_world.portability.models import PortableEnvironmentManifest
from investigation_world.portability.package import PortablePackageBuildResult, write_portable_package
from investigation_world.portability.sre_private import SREPrivatePortableTask


def _render_env_module() -> str:
    return '''from __future__ import annotations

import json

from hud import Environment
from hud.graders import EvaluationResult


env = Environment(name="veritas-sre-v1")
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


@env.template(id="sre_causal_classification")
async def sre_causal_classification(prompt: str, expected_causal_class: str):
    answer = yield prompt
    prediction = _parse_prediction(answer)
    reward = float(prediction == expected_causal_class)
    yield EvaluationResult(
        reward=reward,
        content="deterministic causal-classification verifier",
        info={"parsed": prediction is not None},
    )
'''


def _render_tasks_module() -> str:
    return '''from __future__ import annotations

import json
from pathlib import Path

from env import env, sre_causal_classification


_records = json.loads(Path(__file__).with_name("private_tasks.json").read_text(encoding="utf-8"))
tasks = []
for record in _records:
    task = sre_causal_classification(
        prompt=record["prompt"],
        expected_causal_class=record["expected_causal_class"],
    )
    task.slug = record["task_id"].lower()
    task.columns = {
        "environment": "veritas-sre-v1",
        "portable_task_id": record["task_id"],
    }
    tasks.append(task)

__all__ = ["env", "tasks"]
'''


def _render_pyproject() -> str:
    return '''[project]
name = "veritas-sre-hud"
version = "0.11.0"
description = "Generated HUD package for the sealed Veritas SRE Evaluation Pack v1"
requires-python = ">=3.12,<3.13"
dependencies = ["hud>=0.6,<0.7"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
include = [
  "env.py",
  "tasks.py",
  "private_tasks.json",
  "portable_manifest.json",
  "qualification_evidence.json",
]
'''


def _render_dockerfile() -> str:
    return '''FROM python:3.12-slim

WORKDIR /app
COPY . /app
RUN python -m pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1
EXPOSE 8765
CMD ["hud", "serve", "env:env", "--host", "0.0.0.0", "--port", "8765"]
'''


def _render_readme(manifest: PortableEnvironmentManifest) -> str:
    return f'''# {manifest.sku} — HUD export

Generated from portable manifest `{manifest.manifest_id}`.

This directory is an **operator-private evaluation package**. `private_tasks.json` contains hidden
scoring truth and must not be published as a buyer-safe/public artifact. `qualification_evidence.json`
is buyer-safe and intentionally contains only release identities, aggregate counts, gate outcomes,
and policy anchors—not scenario IDs or hidden labels.

Build the HUD protocol server image:

```bash
docker build -f Dockerfile.hud -t veritas-sre-v1:local .
```

Then run it and use HUD's protocol client against port 8765:

```bash
docker run --rm -p 8765:8765 veritas-sre-v1:local
hud task start sre_causal_classification --url tcp://127.0.0.1:8765 --args '<task-args-json>'
hud task grade sre_causal_classification --url tcp://127.0.0.1:8765 --args '<task-args-json>' --answer '<answer>'
```

The package follows HUD's protocol-first v6 task-template model: the environment yields the prompt,
the harness produces an answer, and the environment returns deterministic reward.
'''


def build_hud_sre_package(
    output_dir: Path,
    *,
    manifest: PortableEnvironmentManifest,
    private_tasks: list[SREPrivatePortableTask],
    qualification_evidence: PortableQualificationEvidence | None = None,
) -> PortablePackageBuildResult:
    if not private_tasks:
        raise ValueError("HUD private SRE package requires at least one private task")
    if len(private_tasks) != manifest.taskset.private_task_count:
        raise ValueError(
            "HUD private task count must match the sealed private count declared by the manifest"
        )
    if qualification_evidence is not None and qualification_evidence.release != manifest.release:
        raise ValueError("HUD qualification evidence release identity must match portable manifest")

    private_payload = [record.model_dump(mode="json") for record in private_tasks]
    files = {
        "portable_manifest.json": json.dumps(
            manifest.model_dump(mode="json"), indent=2, sort_keys=True
        )
        + "\n",
        "private_tasks.json": json.dumps(private_payload, indent=2, sort_keys=True) + "\n",
        "env.py": _render_env_module(),
        "tasks.py": _render_tasks_module(),
        "pyproject.toml": _render_pyproject(),
        "Dockerfile.hud": _render_dockerfile(),
        "README.md": _render_readme(manifest),
    }
    if qualification_evidence is not None:
        files["qualification_evidence.json"] = json.dumps(
            qualification_evidence.model_dump(mode="json"), indent=2, sort_keys=True
        ) + "\n"
    return write_portable_package(
        output_dir,
        adapter="hud-v6",
        manifest_id=manifest.manifest_id,
        files=files,
    )
