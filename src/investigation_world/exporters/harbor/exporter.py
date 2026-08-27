from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from investigation_world.exporters.harbor.models import (
    HarborArtifactVisibility,
    HarborExportConfig,
    HarborExportError,
    HarborExportResult,
    HarborPackageFile,
)
from investigation_world.mcp_compiler import compile_mcp_surface
from investigation_world.portable_contract import PortableOperationalContract

HARBOR_TASK_SCHEMA_VERSION = "1.4"
HARBOR_EXPORT_SCHEMA_VERSION = "veritas-harbor-export-v1"
# This is a container-private ephemeral artifact, not a shared-host temp file.
_TRAJECTORY_PATH = "/tmp/veritas-runtime/trajectory.jsonl"  # nosec B108


@dataclass(frozen=True)
class _RenderedFile:
    payload: bytes
    visibility: HarborArtifactVisibility
    executable: bool = False


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: tuple[str, ...] | list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _instruction(contract: PortableOperationalContract) -> str:
    public = contract.public
    constraints = "\n".join(f"- {item}" for item in public.constraints) or "- None declared."
    return (
        f"# Objective\n\n{public.objective}\n\n"
        f"# Role\n\n{public.role}\n\n"
        "# Constraints\n\n"
        f"{constraints}\n\n"
        "# Success condition\n\n"
        f"{public.success_description}\n\n"
        "Use only the configured Veritas MCP tools for operational interaction. "
        "The runtime-control and verifier services are evaluator infrastructure and are not "
        "part of the agent interface.\n"
    )


def _task_toml(
    contract: PortableOperationalContract,
    config: HarborExportConfig,
    surface_id: str,
) -> str:
    public = contract.public
    keywords = ["veritas", "operational", "mcp", public.identity.domain]
    return (
        f"schema_version = {_toml_string(HARBOR_TASK_SCHEMA_VERSION)}\n"
        f"source = {_toml_string('veritas:' + public.public_id)}\n"
        "artifacts = [\n"
        f"  {{ source = {_toml_string(_TRAJECTORY_PATH)}, service = \"runtime-control\" }},\n"
        "]\n\n"
        "[task]\n"
        f"name = {_toml_string(config.task_name)}\n"
        'version = "1.0.0"\n'
        f"description = {_toml_string(public.objective)}\n"
        f"keywords = {_toml_array(keywords)}\n\n"
        "[metadata]\n"
        f"veritas_public_contract_id = {_toml_string(public.public_id)}\n"
        f"veritas_mcp_surface_id = {_toml_string(surface_id)}\n\n"
        "[agent]\n"
        f"timeout_sec = {config.agent_timeout_sec:.6f}\n\n"
        "[verifier]\n"
        f"timeout_sec = {config.verifier_timeout_sec:.6f}\n"
        'environment_mode = "separate"\n\n'
        "[verifier.environment]\n"
        'network_mode = "no-network"\n'
        f"build_timeout_sec = {config.build_timeout_sec:.6f}\n\n"
        "[environment]\n"
        f"build_timeout_sec = {config.build_timeout_sec:.6f}\n\n"
        "[[environment.mcp_servers]]\n"
        'name = "veritas-operational"\n'
        'transport = "streamable-http"\n'
        'url = "http://mcp-server:8000/mcp"\n'
    )


def _compose(config: HarborExportConfig) -> str:
    return f"""services:
  main:
    build:
      context: ./main
    depends_on:
      mcp-server:
        condition: service_healthy
    networks:
      - agent-mcp

  mcp-server:
    build:
      context: ./mcp-server
    depends_on:
      runtime-control:
        condition: service_healthy
    environment:
      VERITAS_RUNTIME_CONTROL_URL: http://runtime-control:8081
      VERITAS_PUBLIC_CONTRACT_PATH: /opt/veritas-harbor/public-contract.json
    expose:
      - \"8000\"
    healthcheck:
      test: [\"CMD\", \"python\", \"-c\", \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2).read()\"]
      interval: 2s
      timeout: 5s
      retries: 20
      start_period: 2s
    networks:
      - agent-mcp
      - runtime-control

  runtime-control:
    build:
      context: ./runtime-control
    environment:
      VERITAS_CONTRACT_PATH: /opt/veritas-harbor/contract.json
      VERITAS_RUNTIME_SEED: \"{config.seed}\"
      VERITAS_TRAJECTORY_PATH: {_TRAJECTORY_PATH}
    expose:
      - \"8081\"
    healthcheck:
      test: [\"CMD\", \"python\", \"-c\", \"import urllib.request; urllib.request.urlopen('http://localhost:8081/health', timeout=2).read()\"]
      interval: 2s
      timeout: 5s
      retries: 20
      start_period: 2s
    networks:
      - runtime-control

networks:
  agent-mcp:
    internal: true
  runtime-control:
    internal: true
"""


def _agent_dockerfile(config: HarborExportConfig) -> str:
    return f"FROM {config.agent_image}\nWORKDIR /workspace\n"


def _mcp_dockerfile(config: HarborExportConfig) -> str:
    return (
        f"FROM {config.runtime_image}\n"
        "WORKDIR /opt/veritas-harbor\n"
        "COPY public-contract.json /opt/veritas-harbor/public-contract.json\n"
        'ENTRYPOINT ["python", "-m", "investigation_world.exporters.harbor.mcp_service"]\n'
    )


def _runtime_dockerfile(config: HarborExportConfig) -> str:
    return (
        f"FROM {config.runtime_image}\n"
        "WORKDIR /opt/veritas-harbor\n"
        "COPY contract.json /opt/veritas-harbor/contract.json\n"
        'ENTRYPOINT ["python", "-m", "investigation_world.exporters.harbor.runtime_service"]\n'
    )


def _verifier_dockerfile(config: HarborExportConfig) -> str:
    return (
        f"FROM {config.verifier_image}\n"
        "WORKDIR /tests\n"
        "COPY contract.json /tests/contract.json\n"
        "COPY test.sh /tests/test.sh\n"
    )


def _test_script() -> str:
    return f"""#!/bin/sh
set -eu
python -m investigation_world.exporters.harbor.verifier \\
  --contract /tests/contract.json \\
  --trajectory {_TRAJECTORY_PATH} \\
  --reward /logs/verifier/reward.txt \\
  --details /logs/verifier/veritas-verifier.json
"""


def _provenance(
    contract: PortableOperationalContract,
    config: HarborExportConfig,
    surface_id: str,
    catalog_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": HARBOR_EXPORT_SCHEMA_VERSION,
        "harbor_task_schema_version": HARBOR_TASK_SCHEMA_VERSION,
        "task_name": config.task_name,
        "contract_id": contract.contract_id,
        "public_contract_id": contract.public.public_id,
        "reset_identity": contract.private.reset_identity,
        "mcp_surface_id": surface_id,
        "mcp_catalog_id": catalog_id,
        "portable_schema_version": contract.schema_version,
        "source_commit": contract.public.provenance.source_commit,
        "portable_compiler": contract.public.provenance.compiler,
        "portable_compiler_version": contract.public.provenance.compiler_version,
        "images": {
            "agent": config.agent_image,
            "runtime": config.runtime_image,
            "verifier": config.verifier_image,
        },
        "seed": config.seed,
        "network_boundaries": {
            "agent_network": "agent-mcp",
            "control_network": "runtime-control",
            "main_on_control_network": False,
            "runtime_control_host_ports": [],
            "verifier_lifecycle": "harbor-separate-after-environment-collection",
        },
    }


def render_harbor_package(
    contract: PortableOperationalContract,
    config: HarborExportConfig,
) -> dict[str, _RenderedFile]:
    """Render a deterministic Harbor task package without touching the filesystem."""

    if not isinstance(contract, PortableOperationalContract):
        raise HarborExportError("PortableOperationalContract is required")
    surface = compile_mcp_surface(contract.public)
    public_contract = contract.public.canonical_bytes() + b"\n"
    full_contract = contract.canonical_bytes() + b"\n"

    files = {
        "instruction.md": _RenderedFile(
            _instruction(contract).encode("utf-8"), HarborArtifactVisibility.AGENT_PUBLIC
        ),
        "task.toml": _RenderedFile(
            _task_toml(contract, config, surface.surface_id).encode("utf-8"),
            HarborArtifactVisibility.AGENT_PUBLIC,
        ),
        "provenance.json": _RenderedFile(
            _canonical_json(
                _provenance(
                    contract,
                    config,
                    surface.surface_id,
                    surface.catalog.catalog_id,
                )
            ),
            HarborArtifactVisibility.PROVENANCE,
        ),
        "environment/main/Dockerfile": _RenderedFile(
            _agent_dockerfile(config).encode("utf-8"),
            HarborArtifactVisibility.AGENT_PUBLIC,
        ),
        "environment/docker-compose.yaml": _RenderedFile(
            _compose(config).encode("utf-8"), HarborArtifactVisibility.AGENT_PUBLIC
        ),
        "environment/mcp-server/Dockerfile": _RenderedFile(
            _mcp_dockerfile(config).encode("utf-8"), HarborArtifactVisibility.AGENT_PUBLIC
        ),
        "environment/mcp-server/public-contract.json": _RenderedFile(
            public_contract, HarborArtifactVisibility.AGENT_PUBLIC
        ),
        "environment/runtime-control/Dockerfile": _RenderedFile(
            _runtime_dockerfile(config).encode("utf-8"),
            HarborArtifactVisibility.OPERATIONAL_PRIVATE,
        ),
        "environment/runtime-control/contract.json": _RenderedFile(
            full_contract, HarborArtifactVisibility.OPERATIONAL_PRIVATE
        ),
        "tests/Dockerfile": _RenderedFile(
            _verifier_dockerfile(config).encode("utf-8"),
            HarborArtifactVisibility.EVALUATOR_PRIVATE,
        ),
        "tests/contract.json": _RenderedFile(
            full_contract, HarborArtifactVisibility.EVALUATOR_PRIVATE
        ),
        "tests/test.sh": _RenderedFile(
            _test_script().encode("utf-8"),
            HarborArtifactVisibility.EVALUATOR_PRIVATE,
            executable=True,
        ),
    }

    public_paths = [
        path
        for path, item in files.items()
        if item.visibility is HarborArtifactVisibility.AGENT_PUBLIC
    ]
    if any(files[path].payload == full_contract for path in public_paths):
        raise HarborExportError("full evaluator-private contract entered an agent-public artifact")
    if b'"visibility":"evaluator_private"' in b"\n".join(
        files[path].payload for path in public_paths
    ):
        raise HarborExportError("evaluator-private contract material entered agent-public files")
    return dict(sorted(files.items()))


def export_harbor_package(
    contract: PortableOperationalContract,
    output_dir: Path,
    config: HarborExportConfig,
) -> HarborExportResult:
    """Materialize an isolated Harbor package into a new or empty directory."""

    target = output_dir.resolve()
    if target.exists() and any(target.iterdir()):
        raise HarborExportError("output directory must be absent or empty")
    rendered = render_harbor_package(contract, config)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.harbor-", dir=target.parent))
    written: list[HarborPackageFile] = []
    try:
        for relative_path, item in rendered.items():
            relative = Path(relative_path)
            if relative.is_absolute() or ".." in relative.parts:
                raise HarborExportError(f"invalid package path: {relative_path}")
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(item.payload)
            os.chmod(destination, 0o755 if item.executable else 0o644)
            written.append(
                HarborPackageFile(
                    path=relative.as_posix(),
                    sha256=hashlib.sha256(item.payload).hexdigest(),
                    bytes=len(item.payload),
                    visibility=item.visibility,
                    mode="0755" if item.executable else "0644",
                )
            )
        if target.exists():
            target.rmdir()
        staging.replace(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    surface = compile_mcp_surface(contract.public)
    return HarborExportResult(
        task_name=config.task_name,
        contract_id=contract.contract_id,
        public_contract_id=contract.public.public_id,
        mcp_surface_id=surface.surface_id,
        output_dir=str(target),
        files=tuple(sorted(written, key=lambda item: item.path)),
    )
