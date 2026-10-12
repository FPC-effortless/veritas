"""Executable Veritas environment-authoring examples."""

from .authority_sensitive import run_demo as run_authority_sensitive
from .file_backed import run_demo as run_file_backed
from .hierarchical_observation import run_demo as run_hierarchical_observation
from .long_horizon_budgeted import run_demo as run_long_horizon_budgeted
from .machine_experience_ready import run_demo as run_machine_experience_ready
from .minimal_typed_tool import run_demo as run_minimal_typed_tool
from .native_artifact_backed import run_demo as run_native_artifact_backed
from .network_api_backed import run_demo as run_network_api_backed
from .sealed_private_evaluator import run_demo as run_sealed_private_evaluator
from .sql_backed import run_demo as run_sql_backed
from .structured_grader import run_demo as run_structured_grader

__all__ = [
    "run_authority_sensitive",
    "run_file_backed",
    "run_hierarchical_observation",
    "run_long_horizon_budgeted",
    "run_machine_experience_ready",
    "run_minimal_typed_tool",
    "run_native_artifact_backed",
    "run_network_api_backed",
    "run_sealed_private_evaluator",
    "run_sql_backed",
    "run_structured_grader",
]
