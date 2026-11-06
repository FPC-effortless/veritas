from __future__ import annotations

import hashlib
import json
from enum import Enum
from math import isfinite
from typing import Any

from pydantic import BaseModel

from investigation_world.portable_contract.errors import UnsupportedOperationalSemanticError


def normalize_json_value(
    value: Any,
    *,
    path: str = "$",
    allow_tuples: bool = False,
) -> Any:
    """Return strict JSON data without silently coercing source semantics."""
    if isinstance(value, Enum):
        return normalize_json_value(
            value.value,
            path=path,
            allow_tuples=allow_tuples,
        )
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise UnsupportedOperationalSemanticError(
                code="NON_FINITE_NUMBER",
                path=path,
                detail="portable contract identity does not permit NaN or infinity",
            )
        return 0.0 if value == 0.0 else value
    if isinstance(value, list):
        return [
            normalize_json_value(
                item,
                path=f"{path}[{index}]",
                allow_tuples=allow_tuples,
            )
            for index, item in enumerate(value)
        ]
    if isinstance(value, tuple):
        if not allow_tuples:
            raise UnsupportedOperationalSemanticError(
                code="NON_JSON_SEMANTIC",
                path=path,
                detail=(
                    "tuple cannot be represented without coercion; "
                    "use explicit JSON-compatible operational semantics"
                ),
            )
        return [
            normalize_json_value(
                item,
                path=f"{path}[{index}]",
                allow_tuples=allow_tuples,
            )
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise UnsupportedOperationalSemanticError(
                    code="NON_STRING_KEY",
                    path=path,
                    detail=f"JSON object key must be a string, got {type(key).__name__}",
                )
            normalized[key] = normalize_json_value(
                item,
                path=f"{path}.{key}",
                allow_tuples=allow_tuples,
            )
        return normalized
    if isinstance(value, BaseModel):
        return normalize_json_value(
            value.model_dump(mode="python"),
            path=path,
            allow_tuples=allow_tuples,
        )
    raise UnsupportedOperationalSemanticError(
        code="NON_JSON_SEMANTIC",
        path=path,
        detail=(
            f"{type(value).__name__} cannot be represented without coercion; "
            "use explicit JSON-compatible operational semantics"
        ),
    )


def canonical_json_bytes(value: Any) -> bytes:
    normalized = normalize_json_value(value, allow_tuples=True)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def content_id(prefix: str, value: Any) -> str:
    digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return f"{prefix}-sha256:{digest}"
