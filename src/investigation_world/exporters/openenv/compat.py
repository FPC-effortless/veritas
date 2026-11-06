from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

try:  # pragma: no cover - exercised only when the optional OpenEnv package is installed.
    from openenv.core.env_server import create_app as _create_app
    from openenv.core.env_server.interfaces import Environment as OpenEnvEnvironmentBase
    from openenv.core.env_server.types import Action as OpenEnvActionBase
    from openenv.core.env_server.types import EnvironmentMetadata
    from openenv.core.env_server.types import Observation as OpenEnvObservationBase
    from openenv.core.env_server.types import State as OpenEnvStateBase

    OPENENV_AVAILABLE = True
except ImportError:  # Keep the Veritas core package importable without OpenEnv installed.
    _create_app = None
    OPENENV_AVAILABLE = False

    class OpenEnvActionBase(BaseModel):
        model_config = ConfigDict(extra="forbid", validate_assignment=True)
        metadata: dict[str, Any] = Field(default_factory=dict)

    class OpenEnvObservationBase(BaseModel):
        model_config = ConfigDict(extra="forbid", validate_assignment=True)
        done: bool = False
        reward: bool | int | float | None = None
        metadata: dict[str, Any] = Field(default_factory=dict)

    class OpenEnvStateBase(BaseModel):
        model_config = ConfigDict(extra="allow", validate_assignment=True)
        episode_id: str | None = None
        step_count: int = Field(default=0, ge=0)

    class EnvironmentMetadata(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str
        description: str
        readme_content: str | None = None
        version: str | None = None
        author: str | None = None
        documentation_url: str | None = None

    class OpenEnvEnvironmentBase:
        SUPPORTS_CONCURRENT_SESSIONS = False
        REQUIRES_SINGLE_THREAD_EXECUTOR = False

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def close(self) -> None:
            pass


def create_openenv_app(*args: Any, **kwargs: Any) -> Any:
    if not OPENENV_AVAILABLE or _create_app is None:
        raise RuntimeError(
            "OpenEnv is not installed. Install a compatible openenv package before "
            "creating the OpenEnv HTTP/WebSocket application."
        )
    return _create_app(*args, **kwargs)
