from __future__ import annotations

from pathlib import Path
from types import ModuleType

import investigation_world.core.models as core_models_module
import investigation_world.exporters.hud.adapter as hud_adapter_module
import investigation_world.mcp_compiler.compiler as mcp_compiler_compiler_module
import investigation_world.mcp_compiler.dispatch as mcp_compiler_dispatch_module
import investigation_world.mcp_compiler.models as mcp_compiler_models_module
import investigation_world.operational.models as operational_models_module
import investigation_world.operational.runtime as operational_runtime_module
import investigation_world.operational.substrate as operational_substrate_module
import investigation_world.operational.verifier as operational_verifier_module
import investigation_world.portable_contract.compiler as portable_contract_compiler_module
import investigation_world.portable_contract.errors as portable_contract_errors_module
import investigation_world.portable_contract.identity as portable_contract_identity_module
import investigation_world.portable_contract.models as portable_contract_models_module
import investigation_world.portable_contract.serialization as portable_contract_serialization_module
import investigation_world.portable_contract.validation as portable_contract_validation_module
import investigation_world.portable_runtime.models as portable_runtime_models_module
import investigation_world.portable_runtime.protocol as portable_runtime_protocol_module
import investigation_world.portable_runtime.runtime as portable_runtime_runtime_module
import investigation_world.portable_runtime.validation as portable_runtime_validation_module


def _module_text(module: ModuleType) -> str:
    path = Path(str(module.__file__)).resolve()
    if path.suffix != ".py":
        raise RuntimeError(f"HUD export requires source .py module, got {path}")
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def vendor_files() -> dict[str, str]:
    modules: dict[str, ModuleType] = {
        "vendor/investigation_world/core/models.py": core_models_module,
        "vendor/investigation_world/operational/models.py": operational_models_module,
        "vendor/investigation_world/operational/runtime.py": operational_runtime_module,
        "vendor/investigation_world/operational/substrate.py": operational_substrate_module,
        "vendor/investigation_world/operational/verifier.py": operational_verifier_module,
        "vendor/investigation_world/portable_contract/compiler.py": (
            portable_contract_compiler_module
        ),
        "vendor/investigation_world/portable_contract/errors.py": portable_contract_errors_module,
        "vendor/investigation_world/portable_contract/identity.py": (
            portable_contract_identity_module
        ),
        "vendor/investigation_world/portable_contract/models.py": portable_contract_models_module,
        "vendor/investigation_world/portable_contract/serialization.py": (
            portable_contract_serialization_module
        ),
        "vendor/investigation_world/portable_contract/validation.py": (
            portable_contract_validation_module
        ),
        "vendor/investigation_world/portable_runtime/models.py": portable_runtime_models_module,
        "vendor/investigation_world/portable_runtime/protocol.py": portable_runtime_protocol_module,
        "vendor/investigation_world/portable_runtime/runtime.py": portable_runtime_runtime_module,
        "vendor/investigation_world/portable_runtime/validation.py": (
            portable_runtime_validation_module
        ),
        "vendor/investigation_world/mcp_compiler/compiler.py": mcp_compiler_compiler_module,
        "vendor/investigation_world/mcp_compiler/dispatch.py": mcp_compiler_dispatch_module,
        "vendor/investigation_world/mcp_compiler/models.py": mcp_compiler_models_module,
        "vendor/investigation_world/exporters/hud/adapter.py": hud_adapter_module,
    }
    files = {path: _module_text(module) for path, module in modules.items()}

    for path in (
        "vendor/investigation_world/__init__.py",
        "vendor/investigation_world/core/__init__.py",
        "vendor/investigation_world/operational/__init__.py",
        "vendor/investigation_world/exporters/__init__.py",
        "vendor/investigation_world/exporters/hud/__init__.py",
    ):
        files[path] = ""

    files["vendor/investigation_world/portable_contract/__init__.py"] = (
        "from .compiler import compile_operational_episode\n"
        "from .models import *\n"
        "from .serialization import serialize_portable_contract, serialize_public_contract\n"
    )
    files["vendor/investigation_world/portable_runtime/__init__.py"] = (
        "from .models import *\n"
        "from .protocol import PortableRuntimeProtocol\n"
        "from .runtime import PortableOperationalRuntime\n"
    )
    files["vendor/investigation_world/mcp_compiler/__init__.py"] = (
        "from .compiler import compile_mcp_surface\n"
        "from .dispatch import dispatch_mcp_tool, resolve_mcp_tool_call\n"
        "from .models import *\n"
    )
    return files
