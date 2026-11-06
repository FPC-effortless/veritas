from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from investigation_world.integrations.woyengi.adapter import (
    WORLD_BUNDLE_ARTIFACT_CONTRACT,
    WorldBundleAdapterError,
)
from investigation_world.integrations.woyengi.pinned import adapt_pinned_world_bundle_fixture
from investigation_world.operational.models import OperationalEpisode, WorldDomain
from investigation_world.portable_contract import (
    PortableActionDefinition,
    PortableOperationalContract,
    PortablePublicContract,
    compile_operational_episode,
    serialize_public_contract,
)

WORLD_BUNDLE_ACTION_SCHEMA_KIND = "ACTION_SCHEMA"
WORLD_BUNDLE_ACTION_SCHEMA_CONTRACT = "woyengi.world-bundle.action-schema.v0.1"
WORLD_BUNDLE_JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
WOYENGI_ACTION_SCHEMA_SOURCE_COMMIT = "b3d51e446dc376cea57ebe3c9eec1a84b37de811"
VERITAS_PORTABLE_CONTRACT_SOURCE_COMMIT = "eac820395b69c2b2d3be593aa85760e61fb38b71"

_JSON_SCHEMA_TYPES = {
    "null",
    "boolean",
    "object",
    "array",
    "number",
    "string",
    "integer",
}
_ROOT_SCHEMA_KEYS = {
    "$schema",
    "additionalProperties",
    "items",
    "properties",
    "required",
    "type",
}
_NESTED_SCHEMA_KEYS = _ROOT_SCHEMA_KEYS - {"$schema"}
_SENSITIVE_SCHEMA_TOKENS = {
    "targetanswer",
    "targetanswers",
    "answerkey",
    "correctanswer",
    "correctanswers",
    "targetstate",
    "hiddenstate",
    "hiddenstateupdates",
}


@dataclass(frozen=True)
class WoyengiActionSchemaBinding:
    action_ref: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


def compile_pinned_world_bundle_contract(
    raw_fixture: bytes | str,
    *,
    expected_sha256: str,
    member_payloads: Mapping[str, Any] | None = None,
    domain: WorldDomain = WorldDomain.ENTERPRISE_OPERATIONS,
) -> PortableOperationalContract:
    """Compile a pinned WorldBundle into Veritas portable IR with exact public schemas.

    The existing adapter remains authoritative for the v0.1 OperationalEpisode/private
    projection. The canonical Portable Operational Contract compiler must first accept
    that episode without loss. This integration then replaces only the generic action
    schemas that A2 necessarily derived from ``PublicActionSpec.parameter_names`` with
    Woyengi's validated public ACTION_SCHEMA members.
    """

    episode = adapt_pinned_world_bundle_fixture(
        raw_fixture,
        expected_sha256=expected_sha256,
        member_payloads=member_payloads,
        domain=domain,
    )
    root = _decode_complete_artifact(raw_fixture)
    contract = _compile_action_schema_contract(episode, root)

    public_text = serialize_public_contract(contract).decode("utf-8")
    if expected_sha256 in public_text:
        raise WorldBundleAdapterError("fixture SHA-256 leaked into portable public contract")
    for private_ref in _private_reference_set(root):
        if private_ref in public_text:
            raise WorldBundleAdapterError(
                f"evaluator-private reference leaked into portable public contract: {private_ref}"
            )
    return contract


def _compile_action_schema_contract(
    episode: OperationalEpisode,
    root: Mapping[str, Any],
) -> PortableOperationalContract:
    bindings = _action_schema_bindings(root)

    # A2's canonical compiler independently proves that all pre-existing Veritas
    # operational semantics survive its projection before this integration changes
    # any action schema fields.
    baseline = compile_operational_episode(episode)
    contract = _overlay_action_schemas(baseline, bindings)
    _assert_action_schema_projection(episode, baseline, contract, bindings)
    return contract


def _decode_complete_artifact(raw_fixture: bytes | str) -> Mapping[str, Any]:
    raw_bytes = raw_fixture.encode("utf-8") if isinstance(raw_fixture, str) else raw_fixture
    try:
        root = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorldBundleAdapterError("pinned WorldBundle fixture is not valid UTF-8 JSON") from exc
    root = _mapping(root, "artifact")
    if root.get("contract") != WORLD_BUNDLE_ARTIFACT_CONTRACT:
        raise WorldBundleAdapterError(
            "typed action schemas require woyengi.world-bundle-artifact.v0.1"
        )
    return root


def _action_schema_bindings(
    root: Mapping[str, Any],
) -> dict[str, WoyengiActionSchemaBinding]:
    bundle = _mapping(root.get("bundle"), "artifact.bundle")
    public = _mapping(bundle.get("public"), "artifact.bundle.public")
    raw_actions = public.get("actionSurface")
    if not isinstance(raw_actions, list):
        raise WorldBundleAdapterError("artifact.bundle.public.actionSurface must be an array")

    actions: dict[str, tuple[str, ...]] = {}
    for index, raw_action in enumerate(raw_actions):
        action = _mapping(raw_action, f"actionSurface[{index}]")
        action_ref = _text(action.get("id"), f"actionSurface[{index}].id")
        if action_ref in actions:
            raise WorldBundleAdapterError(f"duplicate public action id: {action_ref}")
        raw_parameters = action.get("parameterNames")
        if not isinstance(raw_parameters, list) or not all(
            isinstance(value, str) and value.strip() and value == value.strip()
            for value in raw_parameters
        ):
            raise WorldBundleAdapterError(
                f"actionSurface[{index}].parameterNames must contain only non-empty trimmed strings"
            )
        if len(raw_parameters) != len(set(raw_parameters)):
            raise WorldBundleAdapterError(
                f"actionSurface[{index}].parameterNames contains duplicates"
            )
        actions[action_ref] = tuple(raw_parameters)

    raw_members = root.get("members")
    if not isinstance(raw_members, list):
        raise WorldBundleAdapterError("artifact.members must be an array")

    private_refs = _private_reference_set(root)
    bindings: dict[str, WoyengiActionSchemaBinding] = {}
    for index, raw_member in enumerate(raw_members):
        member = _mapping(raw_member, f"members[{index}]")
        if member.get("kind") != WORLD_BUNDLE_ACTION_SCHEMA_KIND:
            continue
        member_id = _text(member.get("id"), f"members[{index}].id")
        if member.get("partition") != "public":
            raise WorldBundleAdapterError(f"ACTION_SCHEMA must be public: {member_id}")
        payload = _exact_mapping(
            member.get("payload"),
            {"actionRef", "contract", "inputSchema", "outputSchema"},
            f"{member_id}.payload",
        )
        if payload.get("contract") != WORLD_BUNDLE_ACTION_SCHEMA_CONTRACT:
            raise WorldBundleAdapterError(
                f"{member_id}.payload.contract has unsupported value {payload.get('contract')!r}"
            )
        action_ref = _text(payload.get("actionRef"), f"{member_id}.payload.actionRef")
        if not action_ref.startswith("world-action:"):
            raise WorldBundleAdapterError(f"{member_id}.actionRef must start with world-action:")
        if action_ref not in actions:
            raise WorldBundleAdapterError(
                f"{member_id}.actionRef references unknown public action {action_ref}"
            )
        if action_ref in bindings:
            raise WorldBundleAdapterError(
                f"duplicate ACTION_SCHEMA binding for public action {action_ref}"
            )

        input_schema = _validate_json_schema(
            payload.get("inputSchema"),
            path=f"{member_id}.inputSchema",
            root=True,
            private_refs=private_refs,
        )
        if input_schema.get("type") != "object":
            raise WorldBundleAdapterError(f"{member_id}.inputSchema root type must be object")
        output_schema = _validate_json_schema(
            payload.get("outputSchema"),
            path=f"{member_id}.outputSchema",
            root=True,
            private_refs=private_refs,
        )

        properties = _mapping(input_schema.get("properties"), f"{member_id}.inputSchema.properties")
        actual_parameters = sorted(properties)
        expected_parameters = sorted(actions[action_ref])
        if actual_parameters != expected_parameters:
            raise WorldBundleAdapterError(
                f"{member_id}.inputSchema.properties must exactly match "
                f"{action_ref}.parameterNames ({', '.join(expected_parameters)})"
            )

        bindings[action_ref] = WoyengiActionSchemaBinding(
            action_ref=action_ref,
            input_schema=copy.deepcopy(input_schema),
            output_schema=copy.deepcopy(output_schema),
        )

    missing = [action_ref for action_ref in actions if action_ref not in bindings]
    if missing:
        raise WorldBundleAdapterError(
            f"public action {missing[0]} has no ACTION_SCHEMA binding"
        )
    return bindings


def _validate_json_schema(
    value: Any,
    *,
    path: str,
    root: bool,
    private_refs: frozenset[str],
) -> dict[str, Any]:
    schema = _mapping(value, path)
    allowed = _ROOT_SCHEMA_KEYS if root else _NESTED_SCHEMA_KEYS
    unknown = sorted(set(schema) - allowed)
    if unknown:
        raise WorldBundleAdapterError(
            f"{path} contains unsupported JSON Schema keyword {unknown[0]}"
        )
    if "type" not in schema:
        raise WorldBundleAdapterError(f"{path} is missing required field type")
    if root:
        if "$schema" not in schema:
            raise WorldBundleAdapterError(f"{path} is missing required field $schema")
        if schema.get("$schema") != WORLD_BUNDLE_JSON_SCHEMA_DIALECT:
            raise WorldBundleAdapterError(
                f"{path}.$schema must equal {WORLD_BUNDLE_JSON_SCHEMA_DIALECT}"
            )
    elif "$schema" in schema:
        raise WorldBundleAdapterError(f"{path} contains unsupported JSON Schema keyword $schema")

    schema_type = _text(schema.get("type"), f"{path}.type")
    if schema_type not in _JSON_SCHEMA_TYPES:
        raise WorldBundleAdapterError(
            f"{path}.type has unsupported JSON Schema type {schema_type}"
        )

    if schema_type == "object":
        for required_key in ("properties", "required", "additionalProperties"):
            if required_key not in schema:
                raise WorldBundleAdapterError(f"{path} is missing required field {required_key}")
        if schema.get("additionalProperties") is not False:
            raise WorldBundleAdapterError(f"{path}.additionalProperties must be false")
        if "items" in schema:
            raise WorldBundleAdapterError(f"{path}.items is not valid for object schemas")
        properties = _mapping(schema.get("properties"), f"{path}.properties")
        for property_name, property_schema in properties.items():
            _safe_property_name(property_name, f"{path}.properties")
            _validate_json_schema(
                property_schema,
                path=f"{path}.properties.{property_name}",
                root=False,
                private_refs=private_refs,
            )
        required = _string_array(schema.get("required"), f"{path}.required")
        if required != sorted(set(required)):
            raise WorldBundleAdapterError(
                f"{path}.required must be unique and lexicographically sorted"
            )
        for required_name in required:
            _safe_property_name(required_name, f"{path}.required")
            if required_name not in properties:
                raise WorldBundleAdapterError(
                    f"{path}.required references unknown property {required_name}"
                )
    else:
        for key in ("properties", "required", "additionalProperties"):
            if key in schema:
                raise WorldBundleAdapterError(
                    f"{path}.{key} is only valid for object schemas"
                )
        if schema_type == "array":
            if "items" not in schema:
                raise WorldBundleAdapterError(f"{path}.items is required for array schemas")
            _validate_json_schema(
                schema.get("items"),
                path=f"{path}.items",
                root=False,
                private_refs=private_refs,
            )
        elif "items" in schema:
            raise WorldBundleAdapterError(f"{path}.items is only valid for array schemas")

    _assert_no_private_schema_semantics(schema, path, private_refs)
    return copy.deepcopy(dict(schema))


def _overlay_action_schemas(
    baseline: PortableOperationalContract,
    bindings: Mapping[str, WoyengiActionSchemaBinding],
) -> PortableOperationalContract:
    actions: list[PortableActionDefinition] = []
    for action in baseline.public.actions:
        binding = bindings.get(action.name)
        if binding is None:
            raise WorldBundleAdapterError(
                f"PortableOperationalContract action has no Woyengi schema: {action.name}"
            )
        actions.append(
            PortableActionDefinition(
                visibility=action.visibility,
                name=action.name,
                kind=action.kind,
                system=action.system,
                description=action.description,
                parameter_names=action.parameter_names,
                input_schema=copy.deepcopy(binding.input_schema),
                output_schema=copy.deepcopy(binding.output_schema),
                cost=action.cost,
                charges=action.charges,
                interaction_mode=action.interaction_mode,
                missing_parameter_behavior="reject_missing_json_schema_required_properties",
                additional_parameters_allowed=False,
            )
        )

    public = PortablePublicContract(
        schema_version=baseline.public.schema_version,
        visibility=baseline.public.visibility,
        identity=baseline.public.identity,
        provenance=baseline.public.provenance,
        objective=baseline.public.objective,
        role=baseline.public.role,
        permitted_systems=baseline.public.permitted_systems,
        constraints=baseline.public.constraints,
        success_description=baseline.public.success_description,
        task_metadata=baseline.public.task_metadata,
        episode_metadata=baseline.public.episode_metadata,
        state=baseline.public.state,
        actions=tuple(actions),
        evidence=baseline.public.evidence,
        runtime=baseline.public.runtime,
    )
    return PortableOperationalContract(
        schema_version=baseline.schema_version,
        public=public,
        private=baseline.private,
    )


def _assert_action_schema_projection(
    episode: OperationalEpisode,
    baseline: PortableOperationalContract,
    contract: PortableOperationalContract,
    bindings: Mapping[str, WoyengiActionSchemaBinding],
) -> None:
    if contract.private != baseline.private:
        raise WorldBundleAdapterError(
            "loss during PortableOperationalContract compilation: private contract changed"
        )

    before = baseline.public.model_dump(mode="python", exclude={"public_id", "actions"})
    after = contract.public.model_dump(mode="python", exclude={"public_id", "actions"})
    if before != after:
        raise WorldBundleAdapterError(
            "loss during PortableOperationalContract compilation: non-action public contract changed"
        )

    source_actions = {action.name: action for action in episode.task.available_actions}
    if set(source_actions) != set(bindings):
        raise WorldBundleAdapterError(
            "loss during PortableOperationalContract compilation: actionRef correspondence changed"
        )
    if len(contract.public.actions) != len(baseline.public.actions):
        raise WorldBundleAdapterError(
            "loss during PortableOperationalContract compilation: action count changed"
        )

    baseline_actions = {action.name: action for action in baseline.public.actions}
    for action in contract.public.actions:
        binding = bindings.get(action.name)
        source = source_actions.get(action.name)
        prior = baseline_actions.get(action.name)
        if binding is None or source is None or prior is None:
            raise WorldBundleAdapterError(
                f"loss during PortableOperationalContract compilation: unknown action {action.name}"
            )
        if tuple(source.parameter_names) != action.parameter_names:
            raise WorldBundleAdapterError(
                f"loss during PortableOperationalContract compilation: parameter names changed for {action.name}"
            )
        if action.input_schema != binding.input_schema:
            raise WorldBundleAdapterError(
                f"loss during PortableOperationalContract compilation: input schema changed for {action.name}"
            )
        if action.output_schema != binding.output_schema:
            raise WorldBundleAdapterError(
                f"loss during PortableOperationalContract compilation: output schema changed for {action.name}"
            )
        if action.additional_parameters_allowed:
            raise WorldBundleAdapterError(
                f"loss during PortableOperationalContract compilation: additional parameters widened for {action.name}"
            )

        prior_payload = prior.model_dump(
            mode="python",
            exclude={
                "input_schema",
                "output_schema",
                "missing_parameter_behavior",
                "additional_parameters_allowed",
            },
        )
        action_payload = action.model_dump(
            mode="python",
            exclude={
                "input_schema",
                "output_schema",
                "missing_parameter_behavior",
                "additional_parameters_allowed",
            },
        )
        if prior_payload != action_payload:
            raise WorldBundleAdapterError(
                f"loss during PortableOperationalContract compilation: non-schema action semantics changed for {action.name}"
            )


def _private_reference_set(root: Mapping[str, Any]) -> frozenset[str]:
    bundle = _mapping(root.get("bundle"), "artifact.bundle")
    partition = bundle.get("privateEvaluator")
    if partition is None:
        return frozenset()
    private = _mapping(partition, "artifact.bundle.privateEvaluator")
    refs: set[str] = set()
    for field in (
        "targetAssertionRefs",
        "invariantRefs",
        "hiddenEffectRefs",
        "evidenceLocatorRefs",
    ):
        value = private.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise WorldBundleAdapterError(
                f"artifact.bundle.privateEvaluator.{field} must be an array of strings"
            )
        refs.update(value)
    return frozenset(refs)


def _assert_no_private_schema_semantics(
    value: Any,
    path: str,
    private_refs: frozenset[str],
) -> None:
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        normalized = value.strip().lower()
        if (
            value in private_refs
            or normalized.startswith(("private://", "evaluator-private://", "sealed-private://"))
            or normalized.startswith(
                (
                    "private-assertion:",
                    "private-invariant:",
                    "private-effect:",
                    "private-evidence:",
                    "private-byte:",
                    "hidden-effect:",
                    "oracle:",
                )
            )
        ):
            raise WorldBundleAdapterError(
                f"{path} contains evaluator-private schema value {value}"
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_private_schema_semantics(item, f"{path}[{index}]", private_refs)
        return
    if not isinstance(value, Mapping):
        raise WorldBundleAdapterError(f"{path} must be JSON-compatible")
    for key, nested in value.items():
        if _sensitive_schema_key(key):
            raise WorldBundleAdapterError(
                f"{path} contains evaluator-private schema field {key}"
            )
        _assert_no_private_schema_semantics(nested, f"{path}.{key}", private_refs)


def _sensitive_schema_key(value: str) -> bool:
    token = "".join(character for character in value.lower() if character.isalnum())
    return (
        token.startswith("private")
        or "evaluator" in token
        or "oracle" in token
        or "hiddeneffect" in token
        or "hiddentransition" in token
        or "targetassertion" in token
        or token in _SENSITIVE_SCHEMA_TOKENS
    )


def _safe_property_name(value: Any, path: str) -> str:
    name = _text(value, path)
    if name != name.strip():
        raise WorldBundleAdapterError(f"{path} contains an invalid property name")
    if name in {"__proto__", "prototype", "constructor"}:
        raise WorldBundleAdapterError(f"{path} contains unsafe property name {name}")
    if _sensitive_schema_key(name):
        raise WorldBundleAdapterError(
            f"{path} contains evaluator-private schema property {name}"
        )
    return name


def _string_array(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise WorldBundleAdapterError(f"{path} must be an array")
    return [_text(item, f"{path}[{index}]") for index, item in enumerate(value)]


def _exact_mapping(value: Any, keys: set[str], path: str) -> Mapping[str, Any]:
    mapping = _mapping(value, path)
    unknown = sorted(set(mapping) - keys)
    if unknown:
        raise WorldBundleAdapterError(f"{path} contains unknown field {unknown[0]}")
    missing = sorted(keys - set(mapping))
    if missing:
        raise WorldBundleAdapterError(f"{path} is missing required field {missing[0]}")
    return mapping


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorldBundleAdapterError(f"{field} must be an object")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldBundleAdapterError(f"{field} must be a non-empty string")
    return value
