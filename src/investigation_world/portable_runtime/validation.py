from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any


class SchemaValidationError(ValueError):
    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


class UnsupportedSchemaError(ValueError):
    def __init__(self, path: str, detail: str):
        self.path = path
        self.detail = detail
        super().__init__(f"{path}: {detail}")


_ANNOTATION_KEYWORDS = {
    "$schema",
    "$id",
    "$anchor",
    "$comment",
    "title",
    "description",
    "default",
    "examples",
    "deprecated",
    "readOnly",
    "writeOnly",
    "format",
}
_SUPPORTED_KEYWORDS = _ANNOTATION_KEYWORDS | {
    "$ref",
    "$defs",
    "definitions",
    "nullable",
    "type",
    "enum",
    "const",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "required",
    "properties",
    "patternProperties",
    "additionalProperties",
    "propertyNames",
    "minProperties",
    "maxProperties",
    "dependentRequired",
    "dependentSchemas",
    "items",
    "prefixItems",
    "minItems",
    "maxItems",
    "uniqueItems",
    "contains",
    "minContains",
    "maxContains",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
}
_SUPPORTED_TYPES = {"null", "boolean", "integer", "number", "string", "array", "object"}


def ensure_supported_schema(schema: Any) -> None:
    """Fail closed when a contract schema uses an assertion this runtime cannot enforce."""

    _walk_schema(schema, root=schema, path="$", ref_stack=())


def validate_json_instance(instance: Any, schema: Any) -> None:
    """Validate a JSON value without coercion against the supported JSON Schema subset."""

    _ensure_json_value(instance, path="$input")
    ensure_supported_schema(schema)
    _validate(instance, schema, root=schema, path="$input")


def _walk_schema(schema: Any, *, root: Any, path: str, ref_stack: tuple[str, ...]) -> None:
    if isinstance(schema, bool):
        return
    if not isinstance(schema, Mapping):
        raise UnsupportedSchemaError(path, "schema must be an object or boolean")

    unknown = sorted(set(schema) - _SUPPORTED_KEYWORDS)
    if unknown:
        raise UnsupportedSchemaError(path, f"unsupported schema keywords: {unknown}")

    type_spec = schema.get("type")
    if type_spec is not None:
        types = [type_spec] if isinstance(type_spec, str) else type_spec
        if not isinstance(types, (list, tuple)) or not types:
            raise UnsupportedSchemaError(path, "type must be a string or non-empty array")
        if any(item not in _SUPPORTED_TYPES for item in types):
            raise UnsupportedSchemaError(path, f"unsupported JSON Schema type: {types!r}")

    ref = schema.get("$ref")
    if ref is not None:
        if not isinstance(ref, str):
            raise UnsupportedSchemaError(path, "$ref must be a string")
        if ref in ref_stack:
            raise UnsupportedSchemaError(path, "recursive local $ref is not supported")
        resolved = _resolve_ref(root, ref, path=path)
        _walk_schema(
            resolved,
            root=root,
            path=f"{path}.$ref",
            ref_stack=(*ref_stack, ref),
        )

    for keyword in ("$defs", "definitions", "properties", "patternProperties", "dependentSchemas"):
        value = schema.get(keyword)
        if value is None:
            continue
        if not isinstance(value, Mapping):
            raise UnsupportedSchemaError(path, f"{keyword} must be an object")
        for key, child in value.items():
            if not isinstance(key, str):
                raise UnsupportedSchemaError(path, f"{keyword} keys must be strings")
            if keyword == "patternProperties":
                try:
                    re.compile(key)
                except re.error as exc:
                    raise UnsupportedSchemaError(path, f"invalid regex {key!r}: {exc}") from exc
            _walk_schema(child, root=root, path=f"{path}.{keyword}.{key}", ref_stack=ref_stack)

    for keyword in (
        "additionalProperties",
        "propertyNames",
        "items",
        "contains",
        "not",
        "if",
        "then",
        "else",
    ):
        value = schema.get(keyword)
        if value is not None:
            _walk_schema(value, root=root, path=f"{path}.{keyword}", ref_stack=ref_stack)

    for keyword in ("prefixItems", "allOf", "anyOf", "oneOf"):
        value = schema.get(keyword)
        if value is None:
            continue
        if not isinstance(value, (list, tuple)):
            raise UnsupportedSchemaError(path, f"{keyword} must be an array")
        for index, child in enumerate(value):
            _walk_schema(
                child,
                root=root,
                path=f"{path}.{keyword}[{index}]",
                ref_stack=ref_stack,
            )


def _resolve_ref(root: Any, ref: str, *, path: str) -> Any:
    if ref == "#":
        return root
    if not ref.startswith("#/"):
        raise UnsupportedSchemaError(path, "only local JSON Pointer $ref values are supported")
    node = root
    for raw_token in ref[2:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, Mapping) and token in node:
            node = node[token]
            continue
        if isinstance(node, (list, tuple)):
            try:
                node = node[int(token)]
                continue
            except (ValueError, IndexError):
                pass
        raise UnsupportedSchemaError(path, f"unresolvable local $ref: {ref}")
    return node


def _ensure_json_value(value: Any, *, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SchemaValidationError(path, "non-finite numbers are not valid JSON values")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise SchemaValidationError(path, "JSON object keys must be strings")
            _ensure_json_value(item, path=f"{path}.{key}")
        return
    raise SchemaValidationError(path, f"unsupported non-JSON value type: {type(value).__name__}")


def _validate(instance: Any, schema: Any, *, root: Any, path: str) -> None:
    if schema is True:
        return
    if schema is False:
        raise SchemaValidationError(path, "value is rejected by a false schema")
    if not isinstance(schema, Mapping):
        raise UnsupportedSchemaError(path, "schema must be an object or boolean")

    if instance is None and schema.get("nullable") is True:
        return

    ref = schema.get("$ref")
    if ref is not None:
        _validate(instance, _resolve_ref(root, ref, path=path), root=root, path=path)

    if "const" in schema and instance != schema["const"]:
        raise SchemaValidationError(path, "value does not match const")
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, (list, tuple)):
            raise UnsupportedSchemaError(path, "enum must be an array")
        if instance not in enum:
            raise SchemaValidationError(path, "value is not one of the allowed enum values")

    for child in schema.get("allOf", ()):
        _validate(instance, child, root=root, path=path)

    any_of = schema.get("anyOf")
    if any_of is not None:
        if not any(_matches(instance, child, root=root, path=path) for child in any_of):
            raise SchemaValidationError(path, "value does not satisfy anyOf")

    one_of = schema.get("oneOf")
    if one_of is not None:
        matches = sum(_matches(instance, child, root=root, path=path) for child in one_of)
        if matches != 1:
            raise SchemaValidationError(path, f"value satisfies {matches} oneOf branches, expected 1")

    if "not" in schema and _matches(instance, schema["not"], root=root, path=path):
        raise SchemaValidationError(path, "value satisfies a forbidden not schema")

    if_schema = schema.get("if")
    if if_schema is not None:
        branch = "then" if _matches(instance, if_schema, root=root, path=path) else "else"
        if branch in schema:
            _validate(instance, schema[branch], root=root, path=path)

    type_spec = schema.get("type")
    if type_spec is not None:
        types = [type_spec] if isinstance(type_spec, str) else list(type_spec)
        if not any(_matches_type(instance, item) for item in types):
            raise SchemaValidationError(path, f"expected type {types!r}")

    if isinstance(instance, str):
        _validate_string(instance, schema, path=path)
    if _is_number(instance):
        _validate_number(instance, schema, path=path)
    if isinstance(instance, list):
        _validate_array(instance, schema, root=root, path=path)
    if isinstance(instance, Mapping):
        _validate_object(instance, schema, root=root, path=path)


def _matches(instance: Any, schema: Any, *, root: Any, path: str) -> bool:
    try:
        _validate(instance, schema, root=root, path=path)
    except SchemaValidationError:
        return False
    return True


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return _is_number(value)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, Mapping)
    return False


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_string(value: str, schema: Mapping[str, Any], *, path: str) -> None:
    minimum = schema.get("minLength")
    maximum = schema.get("maxLength")
    if minimum is not None and len(value) < minimum:
        raise SchemaValidationError(path, f"string length is less than minLength {minimum}")
    if maximum is not None and len(value) > maximum:
        raise SchemaValidationError(path, f"string length exceeds maxLength {maximum}")
    pattern = schema.get("pattern")
    if pattern is not None and re.search(pattern, value) is None:
        raise SchemaValidationError(path, f"string does not match pattern {pattern!r}")


def _validate_number(value: int | float, schema: Mapping[str, Any], *, path: str) -> None:
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    exclusive_minimum = schema.get("exclusiveMinimum")
    exclusive_maximum = schema.get("exclusiveMaximum")
    if minimum is not None and value < minimum:
        raise SchemaValidationError(path, f"number is less than minimum {minimum}")
    if maximum is not None and value > maximum:
        raise SchemaValidationError(path, f"number exceeds maximum {maximum}")
    if exclusive_minimum is not None and value <= exclusive_minimum:
        raise SchemaValidationError(path, f"number must be greater than {exclusive_minimum}")
    if exclusive_maximum is not None and value >= exclusive_maximum:
        raise SchemaValidationError(path, f"number must be less than {exclusive_maximum}")
    multiple = schema.get("multipleOf")
    if multiple is not None:
        if multiple <= 0:
            raise UnsupportedSchemaError(path, "multipleOf must be greater than zero")
        try:
            if Decimal(str(value)) % Decimal(str(multiple)) != 0:
                raise SchemaValidationError(path, f"number is not a multiple of {multiple}")
        except InvalidOperation as exc:
            raise UnsupportedSchemaError(path, "invalid multipleOf arithmetic") from exc


def _validate_array(
    value: list[Any],
    schema: Mapping[str, Any],
    *,
    root: Any,
    path: str,
) -> None:
    minimum = schema.get("minItems")
    maximum = schema.get("maxItems")
    if minimum is not None and len(value) < minimum:
        raise SchemaValidationError(path, f"array has fewer than minItems {minimum}")
    if maximum is not None and len(value) > maximum:
        raise SchemaValidationError(path, f"array has more than maxItems {maximum}")
    if schema.get("uniqueItems") is True:
        keys = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
        if len(keys) != len(set(keys)):
            raise SchemaValidationError(path, "array items are not unique")

    prefix = schema.get("prefixItems", ())
    for index, child in enumerate(prefix):
        if index >= len(value):
            break
        _validate(value[index], child, root=root, path=f"{path}[{index}]")

    items = schema.get("items")
    start = len(prefix)
    if items is not None:
        for index in range(start, len(value)):
            _validate(value[index], items, root=root, path=f"{path}[{index}]")

    contains = schema.get("contains")
    if contains is not None:
        matches = sum(
            _matches(item, contains, root=root, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
        minimum_contains = schema.get("minContains", 1)
        maximum_contains = schema.get("maxContains")
        if matches < minimum_contains:
            raise SchemaValidationError(path, f"contains matched {matches}, need {minimum_contains}")
        if maximum_contains is not None and matches > maximum_contains:
            raise SchemaValidationError(path, f"contains matched {matches}, max {maximum_contains}")


def _validate_object(
    value: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    root: Any,
    path: str,
) -> None:
    minimum = schema.get("minProperties")
    maximum = schema.get("maxProperties")
    if minimum is not None and len(value) < minimum:
        raise SchemaValidationError(path, f"object has fewer than minProperties {minimum}")
    if maximum is not None and len(value) > maximum:
        raise SchemaValidationError(path, f"object has more than maxProperties {maximum}")

    required = schema.get("required", ())
    if not isinstance(required, (list, tuple)) or any(not isinstance(item, str) for item in required):
        raise UnsupportedSchemaError(path, "required must be an array of strings")
    missing = [name for name in required if name not in value]
    if missing:
        raise SchemaValidationError(path, f"missing required properties: {missing}")

    property_names = schema.get("propertyNames")
    if property_names is not None:
        for key in value:
            _validate(key, property_names, root=root, path=f"{path}.<propertyName>")

    properties = schema.get("properties", {})
    patterns = schema.get("patternProperties", {})
    matched: set[str] = set()
    for key, child in properties.items():
        if key in value:
            matched.add(key)
            _validate(value[key], child, root=root, path=f"{path}.{key}")
    for pattern, child in patterns.items():
        for key, item in value.items():
            if re.search(pattern, key) is not None:
                matched.add(key)
                _validate(item, child, root=root, path=f"{path}.{key}")

    additional = schema.get("additionalProperties", True)
    for key, item in value.items():
        if key in matched:
            continue
        if additional is False:
            raise SchemaValidationError(path, f"unexpected property: {key}")
        if additional is not True:
            _validate(item, additional, root=root, path=f"{path}.{key}")

    dependent_required = schema.get("dependentRequired", {})
    if dependent_required:
        if not isinstance(dependent_required, Mapping):
            raise UnsupportedSchemaError(path, "dependentRequired must be an object")
        for key, required_names in dependent_required.items():
            if key not in value:
                continue
            if not isinstance(required_names, (list, tuple)):
                raise UnsupportedSchemaError(path, "dependentRequired values must be arrays")
            missing_names = [name for name in required_names if name not in value]
            if missing_names:
                raise SchemaValidationError(
                    path,
                    f"property {key!r} requires properties {missing_names}",
                )

    dependent_schemas = schema.get("dependentSchemas", {})
    for key, child in dependent_schemas.items():
        if key in value:
            _validate(value, child, root=root, path=path)
