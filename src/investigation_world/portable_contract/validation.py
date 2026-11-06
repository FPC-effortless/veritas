from __future__ import annotations

from typing import Any

from investigation_world.operational.models import OperationalEpisode
from investigation_world.portable_contract.errors import SemanticRoundTripError
from investigation_world.portable_contract.identity import normalize_json_value
from investigation_world.portable_contract.models import PortableOperationalContract


def _semantic_payload(contract: PortableOperationalContract) -> dict[str, Any]:
    payload = contract.model_dump(mode="python", exclude={"contract_id"})
    public = dict(payload["public"])
    public.pop("public_id", None)
    payload["public"] = public
    return normalize_json_value(payload, path="contract", allow_tuples=True)


def _first_difference(
    expected: Any,
    actual: Any,
    *,
    path: str = "$",
) -> tuple[str, Any, Any] | None:
    if type(expected) is not type(actual):
        return path, expected, actual
    if isinstance(expected, dict):
        expected_keys = set(expected)
        actual_keys = set(actual)
        if expected_keys != actual_keys:
            return (
                path,
                sorted(expected_keys),
                sorted(actual_keys),
            )
        for key in sorted(expected):
            difference = _first_difference(
                expected[key],
                actual[key],
                path=f"{path}.{key}",
            )
            if difference is not None:
                return difference
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}.length", len(expected), len(actual)
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            difference = _first_difference(
                expected_item,
                actual_item,
                path=f"{path}[{index}]",
            )
            if difference is not None:
                return difference
        return None
    if expected != actual:
        return path, expected, actual
    return None


def assert_operational_semantic_equivalence(
    episode: OperationalEpisode,
    contract: PortableOperationalContract,
) -> None:
    """Fail if a portable contract differs from the canonical episode projection."""
    from investigation_world.portable_contract.compiler import (
        _compile_operational_episode_unchecked,
    )

    expected = _semantic_payload(_compile_operational_episode_unchecked(episode))
    actual = _semantic_payload(contract)
    difference = _first_difference(expected, actual)
    if difference is None:
        return
    path, expected_value, actual_value = difference
    raise SemanticRoundTripError(
        path=path,
        expected=expected_value,
        actual=actual_value,
    )
