from __future__ import annotations

import copy
import hashlib
import hmac
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import Field

from investigation_world.operational.models import (
    ActionKind,
    AssertionComparison,
    HiddenActionEffect,
    HiddenOracle,
    OperationalEpisode,
    OperationalInvariant,
    OperationalRecord,
    PublicActionSpec,
    StateAssertion,
    TaskContract,
    WorldDomain,
)

WORLD_BUNDLE_CONTRACT = "woyengi.world-bundle.v0.1"
WORLD_BUNDLE_VERSION = "0.1.0"
WORLD_BUNDLE_ARTIFACT_CONTRACT = "woyengi.world-bundle-artifact.v0.1"
WOYENGI_SYSTEM = "WOYENGI"
ADAPTER_RUNTIME_VERSION = "0.1.0"
_EFFECTIVELY_UNBOUNDED = 1_000_000


class WorldBundleAdapterError(ValueError):
    """Raised when a WorldBundle cannot be adapted without semantic or secrecy loss."""


class WoyengiHiddenOracle(HiddenOracle):
    """Evaluator-private Veritas projection with retained Woyengi source material.

    Woyengi remains the semantic authority. The inherited fields are populated only
    when a portable Woyengi member contains enough explicit structure for a lossless
    Veritas projection. Opaque private source material stays private here; unsupported
    mappings fail closed rather than being guessed into native Veritas semantics.
    """

    source_bundle_id: str
    source_artifact_id: str | None = None
    source_fixture_sha256: str | None = None
    private_partition_manifest: list[dict[str, Any]] = Field(default_factory=list)
    target_assertion_refs: list[str] = Field(default_factory=list)
    invariant_refs: list[str] = Field(default_factory=list)
    hidden_effect_refs: list[str] = Field(default_factory=list)
    evidence_locator_refs: list[str] = Field(default_factory=list)
    private_member_payloads: dict[str, Any] = Field(default_factory=dict)


def _as_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorldBundleAdapterError(f"{field} must be an object")
    return value


def _as_list(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise WorldBundleAdapterError(f"{field} must be an array")
    return value


def _as_string_list(value: Any, *, field: str) -> list[str]:
    items = _as_list(value, field=field)
    if not all(isinstance(item, str) for item in items):
        raise WorldBundleAdapterError(f"{field} must contain only strings")
    return list(items)


def _required_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldBundleAdapterError(f"{field} must be a non-empty string")
    return value


def _semver(value: Any, *, field: str) -> tuple[int, int, int]:
    text = _required_string(value, field=field)
    parts = text.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise WorldBundleAdapterError(f"{field} must use major.minor.patch")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def _manifest_index(
    bundle: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    raw_manifest = _as_list(bundle.get("partitionManifest"), field="partitionManifest")
    by_id: dict[str, dict[str, Any]] = {}
    public_members: list[dict[str, Any]] = []
    private_members: list[dict[str, Any]] = []
    for index, raw_member in enumerate(raw_manifest):
        member = dict(_as_mapping(raw_member, field=f"partitionManifest[{index}]"))
        member_id = _required_string(member.get("id"), field=f"partitionManifest[{index}].id")
        partition = member.get("partition")
        if partition not in {"public", "private-evaluator"}:
            raise WorldBundleAdapterError(
                f"partitionManifest[{index}].partition must be public or private-evaluator"
            )
        _required_string(member.get("kind"), field=f"partitionManifest[{index}].kind")
        if member_id in by_id:
            raise WorldBundleAdapterError(f"duplicate partition member id: {member_id}")
        by_id[member_id] = copy.deepcopy(member)
        if partition == "public":
            public_members.append(copy.deepcopy(member))
        else:
            private_members.append(copy.deepcopy(member))
    return by_id, public_members, private_members


def _private_partition_refs(bundle: Mapping[str, Any]) -> dict[str, list[str]]:
    raw_private = bundle.get("privateEvaluator")
    if raw_private is None:
        return {
            "targetAssertionRefs": [],
            "invariantRefs": [],
            "hiddenEffectRefs": [],
            "evidenceLocatorRefs": [],
        }
    private = _as_mapping(raw_private, field="privateEvaluator")
    return {
        "targetAssertionRefs": _as_string_list(
            private.get("targetAssertionRefs", []), field="privateEvaluator.targetAssertionRefs"
        ),
        "invariantRefs": _as_string_list(
            private.get("invariantRefs", []), field="privateEvaluator.invariantRefs"
        ),
        "hiddenEffectRefs": _as_string_list(
            private.get("hiddenEffectRefs", []), field="privateEvaluator.hiddenEffectRefs"
        ),
        "evidenceLocatorRefs": _as_string_list(
            private.get("evidenceLocatorRefs", []), field="privateEvaluator.evidenceLocatorRefs"
        ),
    }


def _validate_legacy_partition_boundary(
    *,
    bundle: Mapping[str, Any],
    public: Mapping[str, Any],
    manifest_by_id: Mapping[str, Mapping[str, Any]],
    private_refs: Mapping[str, list[str]],
) -> None:
    """Validate the pre-P0-003 sidecar seam retained for scaffold compatibility.

    The actual portable artifact uses manifest member IDs distinct from evaluator
    semantic refs. That format is validated separately by ``_normalize_artifact``.
    """

    private_ids = {
        member_id
        for member_id, member in manifest_by_id.items()
        if member.get("partition") == "private-evaluator"
    }

    for category, refs in private_refs.items():
        for ref in refs:
            member = manifest_by_id.get(ref)
            if member is None or member.get("partition") != "private-evaluator":
                raise WorldBundleAdapterError(
                    f"{category} reference {ref!r} is not declared private-evaluator"
                )

    public_reference_groups = {
        "public.observationRefs": _as_string_list(
            public.get("observationRefs", []), field="public.observationRefs"
        ),
        "public.outcomeContractRefs": _as_string_list(
            public.get("outcomeContractRefs", []), field="public.outcomeContractRefs"
        ),
        "public.provenanceRefs": _as_string_list(
            public.get("provenanceRefs", []), field="public.provenanceRefs"
        ),
        "provenanceRefs": _as_string_list(bundle.get("provenanceRefs", []), field="provenanceRefs"),
    }
    for field, refs in public_reference_groups.items():
        leaked = sorted(set(refs) & private_ids)
        if leaked:
            raise WorldBundleAdapterError(
                f"{field} references private-evaluator member(s): {leaked}"
            )

    for index, raw_action in enumerate(
        _as_list(public.get("actionSurface", []), field="public.actionSurface")
    ):
        action = _as_mapping(raw_action, field=f"public.actionSurface[{index}]")
        action_id = _required_string(action.get("id"), field=f"public.actionSurface[{index}].id")
        if action_id in private_ids:
            raise WorldBundleAdapterError(
                f"public.actionSurface references private-evaluator member: {action_id}"
            )

    for index, raw_asset in enumerate(
        _as_list(public.get("assetDescriptors", []), field="public.assetDescriptors")
    ):
        asset = _as_mapping(raw_asset, field=f"public.assetDescriptors[{index}]")
        asset_id = _required_string(asset.get("id"), field=f"public.assetDescriptors[{index}].id")
        if asset_id in private_ids:
            raise WorldBundleAdapterError(
                f"public.assetDescriptors references private-evaluator member: {asset_id}"
            )


def _split_member_payloads(
    *,
    member_payloads: Mapping[str, Any] | None,
    manifest_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if member_payloads is None:
        return {}, {}
    public_payloads: dict[str, Any] = {}
    private_payloads: dict[str, Any] = {}
    for member_id, payload in member_payloads.items():
        member = manifest_by_id.get(member_id)
        if member is None:
            raise WorldBundleAdapterError(
                f"member payload {member_id!r} is not declared by partitionManifest"
            )
        if member.get("partition") == "private-evaluator":
            private_payloads[member_id] = copy.deepcopy(payload)
        else:
            public_payloads[member_id] = copy.deepcopy(payload)
    return public_payloads, private_payloads


def _extract_public_outcome_semantics(
    *,
    outcome_refs: Sequence[str],
    public_member_payloads: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str], list[dict[str, Any]], str]:
    outcome_contracts: list[dict[str, Any]] = []
    constraints: list[str] = []
    evidence_requirements: list[str] = []
    budgets: list[dict[str, Any]] = []
    success_descriptions: list[str] = []

    def append_unique(target: list[str], value: str) -> None:
        if value not in target:
            target.append(value)

    for ref in outcome_refs:
        payload = public_member_payloads.get(ref)
        if not isinstance(payload, Mapping):
            continue
        contract = copy.deepcopy(dict(payload))
        outcome_contracts.append(contract)

        for invariant in contract.get("invariants", []):
            if isinstance(invariant, str):
                append_unique(constraints, invariant)
        for evidence_ref in contract.get("requiredEvidenceRefs", []):
            if isinstance(evidence_ref, str):
                append_unique(evidence_requirements, evidence_ref)
                append_unique(constraints, f"required-evidence:{evidence_ref}")
        for requirement in contract.get("verificationRequirements", []):
            if isinstance(requirement, str):
                append_unique(constraints, f"verification:{requirement}")
        for raw_effect in contract.get("effectConstraints", []):
            if isinstance(raw_effect, Mapping):
                effect_class = raw_effect.get("effectClass")
                policy = raw_effect.get("policy")
                if isinstance(effect_class, str) and isinstance(policy, str):
                    append_unique(constraints, f"effect:{effect_class}:{policy}")
        for requirement in contract.get("acceptanceAuthorityRequirements", []):
            if isinstance(requirement, str):
                append_unique(constraints, f"acceptance-authority:{requirement}")
        for assertion in contract.get("successAssertions", []):
            if isinstance(assertion, Mapping) and isinstance(assertion.get("description"), str):
                description = assertion["description"]
                if description not in success_descriptions:
                    success_descriptions.append(description)
        budget = contract.get("budget")
        if isinstance(budget, Mapping):
            budgets.append(copy.deepcopy(dict(budget)))

    return (
        outcome_contracts,
        constraints,
        evidence_requirements,
        budgets,
        " ".join(success_descriptions),
    )


def _positive_integral(value: Any, *, field: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorldBundleAdapterError(f"{field} must be an integer-compatible number")
    if not float(value).is_integer():
        raise WorldBundleAdapterError(
            f"{field}={value!r} cannot be represented exactly by the Veritas integer budget"
        )
    integer = int(value)
    if integer < minimum:
        raise WorldBundleAdapterError(f"{field} must be >= {minimum}")
    return integer


def _runtime_budget_projection(budgets: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
    if not budgets:
        return _EFFECTIVELY_UNBOUNDED, _EFFECTIVELY_UNBOUNDED
    max_costs: list[int] = []
    max_attempts: list[int] = []
    for index, budget in enumerate(budgets):
        if "maximumCost" in budget:
            max_costs.append(
                _positive_integral(budget["maximumCost"], field=f"budget[{index}].maximumCost")
            )
        if "maximumAttempts" in budget:
            max_attempts.append(
                _positive_integral(
                    budget["maximumAttempts"], field=f"budget[{index}].maximumAttempts"
                )
            )
    return (
        min(max_costs) if max_costs else _EFFECTIVELY_UNBOUNDED,
        min(max_attempts) if max_attempts else _EFFECTIVELY_UNBOUNDED,
    )


def _build_actions(public: Mapping[str, Any]) -> tuple[list[PublicActionSpec], dict[str, dict[str, Any]]]:
    kind_map = {
        "READ": ActionKind.READ,
        "WRITE": ActionKind.WRITE,
        "EXECUTE": ActionKind.EXECUTE,
        "COMMUNICATE": ActionKind.COMMUNICATE,
        "ESCALATE": ActionKind.ESCALATE,
        "SUBMIT": ActionKind.SUBMIT,
    }
    actions: list[PublicActionSpec] = []
    bindings: dict[str, dict[str, Any]] = {}
    for index, raw_action in enumerate(
        _as_list(public.get("actionSurface", []), field="public.actionSurface")
    ):
        action = dict(_as_mapping(raw_action, field=f"public.actionSurface[{index}]"))
        action_id = _required_string(action.get("id"), field=f"public.actionSurface[{index}].id")
        name = _required_string(action.get("name"), field=f"public.actionSurface[{index}].name")
        kind = kind_map.get(action.get("kind"))
        if kind is None:
            raise WorldBundleAdapterError(
                f"public.actionSurface[{index}].kind is not a WorldBundle v0.1 action kind"
            )
        if action_id in bindings:
            raise WorldBundleAdapterError(f"duplicate action id: {action_id}")
        bindings[action_id] = copy.deepcopy(action)
        actions.append(
            PublicActionSpec(
                # Veritas dispatch has one unique action-name slot. Preserve the stable
                # Woyengi action id there and retain the Woyengi human name separately.
                name=action_id,
                kind=kind,
                system=WOYENGI_SYSTEM,
                description=name,
                parameter_names=[],
                cost=0,
            )
        )
    return actions, bindings


def _build_records(
    public: Mapping[str, Any],
    *,
    provenance_refs: list[str],
    preserve_record_identity: bool = False,
) -> list[OperationalRecord]:
    records: list[OperationalRecord] = []
    for ref in _as_string_list(public.get("observationRefs", []), field="public.observationRefs"):
        records.append(
            OperationalRecord(
                record_id=ref if preserve_record_identity else f"woyengi-observation::{ref}",
                system=WOYENGI_SYSTEM,
                record_type="worldbundle_observation_ref",
                object_id=ref,
                fields={"reference": ref},
                searchable_text=ref,
                provenance_ids=list(provenance_refs),
            )
        )
    for index, raw_asset in enumerate(
        _as_list(public.get("assetDescriptors", []), field="public.assetDescriptors")
    ):
        descriptor = dict(_as_mapping(raw_asset, field=f"public.assetDescriptors[{index}]"))
        asset_id = _required_string(descriptor.get("id"), field=f"public.assetDescriptors[{index}].id")
        asset_kind = _required_string(
            descriptor.get("kind"), field=f"public.assetDescriptors[{index}].kind"
        )
        records.append(
            OperationalRecord(
                record_id=asset_id if preserve_record_identity else f"woyengi-artifact::{asset_id}",
                system=WOYENGI_SYSTEM,
                record_type="worldbundle_artifact_descriptor",
                object_id=asset_id,
                fields={"descriptor": copy.deepcopy(descriptor)},
                searchable_text=" ".join(
                    str(value)
                    for value in (
                        asset_id,
                        asset_kind,
                        descriptor.get("format", ""),
                        descriptor.get("contentHash", ""),
                    )
                    if value
                ),
                provenance_ids=list(provenance_refs),
            )
        )
    return records


def _adapt_world_bundle(
    bundle_input: Mapping[str, Any],
    *,
    member_payloads: Mapping[str, Any] | None,
    domain: WorldDomain,
) -> OperationalEpisode:
    """Adapt the frozen logical v0.1 seam used before P0-003 artifact materialization."""

    bundle = copy.deepcopy(dict(_as_mapping(bundle_input, field="bundle")))
    if bundle.get("contract") != WORLD_BUNDLE_CONTRACT:
        raise WorldBundleAdapterError(
            f"unsupported WorldBundle contract: {bundle.get('contract')!r}"
        )
    if bundle.get("version") != WORLD_BUNDLE_VERSION:
        raise WorldBundleAdapterError(f"unsupported WorldBundle version: {bundle.get('version')!r}")

    bundle_id = _required_string(bundle.get("id"), field="id")
    source_spec_ref = _required_string(bundle.get("sourceSpecRef"), field="sourceSpecRef")
    source_spec_version = _required_string(
        bundle.get("sourceSpecVersion"), field="sourceSpecVersion"
    )
    compatibility = dict(_as_mapping(bundle.get("compatibility"), field="compatibility"))
    _required_string(
        compatibility.get("minimumRuntimeVersion"),
        field="compatibility.minimumRuntimeVersion",
    )
    public = _as_mapping(bundle.get("public"), field="public")
    objective = _required_string(public.get("objective"), field="public.objective")
    actor_roles = _as_string_list(public.get("actorRoles", []), field="public.actorRoles")

    manifest_by_id, public_manifest, private_manifest = _manifest_index(bundle)
    private_refs = _private_partition_refs(bundle)
    _validate_legacy_partition_boundary(
        bundle=bundle,
        public=public,
        manifest_by_id=manifest_by_id,
        private_refs=private_refs,
    )
    public_member_payloads, private_member_payloads = _split_member_payloads(
        member_payloads=member_payloads,
        manifest_by_id=manifest_by_id,
    )

    outcome_refs = _as_string_list(
        public.get("outcomeContractRefs", []), field="public.outcomeContractRefs"
    )
    (
        outcome_contracts,
        constraints,
        evidence_requirements,
        budgets,
        success_description,
    ) = _extract_public_outcome_semantics(
        outcome_refs=outcome_refs,
        public_member_payloads=public_member_payloads,
    )
    max_cost, max_tool_calls = _runtime_budget_projection(budgets)

    actions, action_bindings = _build_actions(public)
    public_provenance = _as_string_list(
        public.get("provenanceRefs", []), field="public.provenanceRefs"
    )
    top_level_provenance = _as_string_list(bundle.get("provenanceRefs", []), field="provenanceRefs")
    combined_provenance = list(dict.fromkeys([*public_provenance, *top_level_provenance]))
    records = _build_records(public, provenance_refs=combined_provenance)

    task = TaskContract(
        task_id=bundle_id,
        world_id=bundle_id,
        domain=domain,
        objective=objective,
        role=" | ".join(actor_roles),
        permitted_systems=[WOYENGI_SYSTEM],
        available_actions=actions,
        constraints=constraints,
        success_description=success_description,
        metadata={
            "woyengi": {
                "semantic_authority": "woyengi",
                "actor_roles": copy.deepcopy(actor_roles),
                "action_surface": copy.deepcopy(
                    _as_list(public.get("actionSurface", []), field="public.actionSurface")
                ),
                "action_bindings": copy.deepcopy(action_bindings),
                "observation_refs": copy.deepcopy(
                    _as_string_list(public.get("observationRefs", []), field="public.observationRefs")
                ),
                "asset_descriptors": copy.deepcopy(
                    _as_list(public.get("assetDescriptors", []), field="public.assetDescriptors")
                ),
                "outcome_contract_refs": copy.deepcopy(outcome_refs),
                "outcome_contracts": copy.deepcopy(outcome_contracts),
                "constraints": copy.deepcopy(constraints),
                "budgets": copy.deepcopy(budgets),
                "evidence_requirements": copy.deepcopy(evidence_requirements),
                "provenance_refs": copy.deepcopy(combined_provenance),
                "partition_manifest": copy.deepcopy(public_manifest),
                "public_member_payloads": copy.deepcopy(public_member_payloads),
                "public_materialization_complete": all(
                    ref in public_member_payloads for ref in outcome_refs
                ),
            }
        },
    )

    oracle = WoyengiHiddenOracle(
        task_id=bundle_id,
        initial_state={},
        target_state=[],
        invariants=[],
        required_actions=[],
        required_action_order=[],
        required_action_counts={},
        forbidden_actions=[],
        required_evidence_ids=[],
        action_effects=[],
        max_cost=max_cost,
        max_tool_calls=max_tool_calls,
        metadata={
            "semantic_authority": "woyengi",
            "projection_status": "legacy-opaque-private-semantics-retained",
        },
        source_bundle_id=bundle_id,
        private_partition_manifest=copy.deepcopy(private_manifest),
        target_assertion_refs=copy.deepcopy(private_refs["targetAssertionRefs"]),
        invariant_refs=copy.deepcopy(private_refs["invariantRefs"]),
        hidden_effect_refs=copy.deepcopy(private_refs["hiddenEffectRefs"]),
        evidence_locator_refs=copy.deepcopy(private_refs["evidenceLocatorRefs"]),
        private_member_payloads=copy.deepcopy(private_member_payloads),
    )

    return OperationalEpisode(
        episode_id=bundle_id,
        world_id=bundle_id,
        task=task,
        records=records,
        oracle=oracle,
        metadata={
            "woyengi_source": {
                "contract": WORLD_BUNDLE_CONTRACT,
                "bundle_id": bundle_id,
                "bundle_version": WORLD_BUNDLE_VERSION,
                "source_spec_ref": source_spec_ref,
                "source_spec_version": source_spec_version,
                "compatibility": copy.deepcopy(compatibility),
                "provenance_refs": copy.deepcopy(combined_provenance),
            },
            "adapter": {
                "contract": "veritas.woyengi-worldbundle-adapter.v0.1",
                "semantic_authority": "woyengi",
                "runtime_projection_domain": domain.value,
            },
        },
    )


def _canonical_json(value: Any) -> str:
    """Canonical JSON for P0 artifacts, failing closed on ambiguous float rendering.

    The pinned P0 fixture uses integral numbers. Python and JavaScript agree on the
    resulting canonical representation. Non-integral floats are rejected here rather
    than risking a cross-language hash disagreement.
    """

    def reject_float(node: Any, path: str) -> None:
        if isinstance(node, float):
            if not math.isfinite(node) or not node.is_integer():
                raise WorldBundleAdapterError(
                    f"portable artifact contains a non-integral float at {path}; "
                    "cross-language canonicalization is not lossless in this adapter"
                )
        elif isinstance(node, list):
            for index, item in enumerate(node):
                reject_float(item, f"{path}[{index}]")
        elif isinstance(node, Mapping):
            for key, item in node.items():
                reject_float(item, f"{path}.{key}")

    reject_float(value, "$artifact")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalize_artifact(artifact_input: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    artifact = copy.deepcopy(dict(_as_mapping(artifact_input, field="artifact")))
    if set(artifact) != {"artifactId", "bundle", "contract", "members"}:
        raise WorldBundleAdapterError(
            "portable WorldBundle artifact must contain exactly artifactId, bundle, contract, members"
        )
    if artifact.get("contract") != WORLD_BUNDLE_ARTIFACT_CONTRACT:
        raise WorldBundleAdapterError(
            f"unsupported portable WorldBundle artifact contract: {artifact.get('contract')!r}"
        )

    artifact_id = _required_string(artifact.get("artifactId"), field="artifactId")
    bundle = dict(_as_mapping(artifact.get("bundle"), field="bundle"))
    if bundle.get("contract") != WORLD_BUNDLE_CONTRACT:
        raise WorldBundleAdapterError(
            f"unsupported WorldBundle contract: {bundle.get('contract')!r}"
        )
    if bundle.get("version") != WORLD_BUNDLE_VERSION:
        raise WorldBundleAdapterError(f"unsupported WorldBundle version: {bundle.get('version')!r}")
    minimum_runtime = _semver(
        _as_mapping(bundle.get("compatibility"), field="bundle.compatibility").get(
            "minimumRuntimeVersion"
        ),
        field="bundle.compatibility.minimumRuntimeVersion",
    )
    if minimum_runtime > _semver(ADAPTER_RUNTIME_VERSION, field="adapter runtime version"):
        raise WorldBundleAdapterError(
            f"WorldBundle requires runtime {'.'.join(map(str, minimum_runtime))}, "
            f"adapter supports {ADAPTER_RUNTIME_VERSION}"
        )

    manifest_by_id, _, _ = _manifest_index(bundle)
    raw_members = _as_list(artifact.get("members"), field="members")
    members: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_member in enumerate(raw_members):
        member = dict(_as_mapping(raw_member, field=f"members[{index}]"))
        if set(member) != {"contentHash", "id", "kind", "partition", "payload"}:
            raise WorldBundleAdapterError(f"members[{index}] contains unknown or missing fields")
        member_id = _required_string(member.get("id"), field=f"members[{index}].id")
        if member_id in seen:
            raise WorldBundleAdapterError(f"duplicate materialized WorldBundle member: {member_id}")
        seen.add(member_id)
        manifest = manifest_by_id.get(member_id)
        if manifest is None:
            raise WorldBundleAdapterError(f"materialized member is not declared: {member_id}")
        if member.get("partition") != manifest.get("partition") or member.get("kind") != manifest.get("kind"):
            raise WorldBundleAdapterError(
                f"materialized member {member_id} does not match manifest partition/kind"
            )
        expected_member_hash = "sha256:" + hashlib.sha256(
            _canonical_json(member.get("payload")).encode("utf-8")
        ).hexdigest()
        if member.get("contentHash") != expected_member_hash:
            raise WorldBundleAdapterError(
                f"member {member_id} contentHash mismatch: expected {expected_member_hash}"
            )
        members.append(member)

    if set(manifest_by_id) != seen:
        missing = sorted(set(manifest_by_id) - seen)
        raise WorldBundleAdapterError(f"manifest member(s) are not materialized: {missing}")
    expected_order = sorted(members, key=lambda member: (str(member["partition"]), str(member["id"])))
    if members != expected_order:
        raise WorldBundleAdapterError("portable WorldBundle members are not in canonical order")

    source_ref = _required_string(bundle.get("sourceSpecRef"), field="bundle.sourceSpecRef")
    provenance = _as_string_list(bundle.get("provenanceRefs", []), field="bundle.provenanceRefs")
    public = _as_mapping(bundle.get("public"), field="bundle.public")
    public_provenance = _as_string_list(
        public.get("provenanceRefs", []), field="bundle.public.provenanceRefs"
    )
    if source_ref not in provenance or source_ref not in public_provenance:
        raise WorldBundleAdapterError(
            "source OperationalSystemSpec provenance must be present in bundle and public provenance"
        )

    expected_artifact_id = "world-bundle-artifact:sha256:" + hashlib.sha256(
        _canonical_json(
            {
                "contract": WORLD_BUNDLE_ARTIFACT_CONTRACT,
                "bundle": bundle,
                "members": members,
            }
        ).encode("utf-8")
    ).hexdigest()
    if artifact_id != expected_artifact_id:
        raise WorldBundleAdapterError(
            f"artifactId mismatch: expected {expected_artifact_id}, got {artifact_id}"
        )

    private_refs = _private_partition_refs(bundle)
    private_tokens = {
        *private_refs["targetAssertionRefs"],
        *private_refs["invariantRefs"],
        *private_refs["hiddenEffectRefs"],
        *private_refs["evidenceLocatorRefs"],
        *(
            member["id"]
            for member in members
            if member.get("partition") == "private-evaluator"
        ),
    }
    public_values: list[Any] = [public]
    public_values.extend(
        member["payload"] for member in members if member.get("partition") == "public"
    )
    public_text = json.dumps(public_values, sort_keys=True, ensure_ascii=False)
    leaked_refs = sorted(token for token in private_tokens if token in public_text)
    if leaked_refs:
        raise WorldBundleAdapterError(
            f"public portable artifact references evaluator-private identifiers: {leaked_refs}"
        )

    return bundle, members


def _portable_public_semantics(
    *,
    bundle: Mapping[str, Any],
    members: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[dict[str, Any]], list[str], list[dict[str, Any]], str]:
    public = _as_mapping(bundle.get("public"), field="bundle.public")
    objective = _required_string(public.get("objective"), field="bundle.public.objective")
    public_actions = copy.deepcopy(
        _as_list(public.get("actionSurface", []), field="bundle.public.actionSurface")
    )
    public_assets = copy.deepcopy(
        _as_list(public.get("assetDescriptors", []), field="bundle.public.assetDescriptors")
    )
    public_roles = _as_string_list(public.get("actorRoles", []), field="bundle.public.actorRoles")
    source_ref = _required_string(bundle.get("sourceSpecRef"), field="bundle.sourceSpecRef")
    source_version = _required_string(bundle.get("sourceSpecVersion"), field="bundle.sourceSpecVersion")

    structured_constraints: list[dict[str, Any]] = []
    budgets: list[dict[str, Any]] = []
    evidence_requirements: list[str] = []
    success_assertions: list[dict[str, Any]] = []
    public_member_payloads: list[dict[str, Any]] = []

    for member in members:
        if member.get("partition") != "public":
            continue
        payload = dict(_as_mapping(member.get("payload"), field=f"member:{member.get('id')}.payload"))
        public_member_payloads.append(copy.deepcopy(payload))
        if "objective" in payload and payload["objective"] != objective:
            raise WorldBundleAdapterError(
                f"public member {member.get('id')} objective diverges from bundle.public.objective"
            )
        if "actions" in payload and payload["actions"] != public_actions:
            raise WorldBundleAdapterError(
                f"public member {member.get('id')} action semantics diverge from bundle.public.actionSurface"
            )
        if "artifactDescriptors" in payload and payload["artifactDescriptors"] != public_assets:
            raise WorldBundleAdapterError(
                f"public member {member.get('id')} artifact descriptors diverge from bundle.public.assetDescriptors"
            )
        if "actors" in payload:
            actors = _as_list(payload["actors"], field=f"member:{member.get('id')}.payload.actors")
            roles = [
                _required_string(
                    _as_mapping(actor, field="portable actor").get("role"),
                    field="portable actor.role",
                )
                for actor in actors
            ]
            if roles != public_roles:
                raise WorldBundleAdapterError(
                    f"public member {member.get('id')} actor roles diverge from bundle.public.actorRoles"
                )
        if payload.get("sourceSpecRef", source_ref) != source_ref:
            raise WorldBundleAdapterError(
                f"public member {member.get('id')} sourceSpecRef diverges from bundle"
            )
        if payload.get("sourceSpecVersion", source_version) != source_version:
            raise WorldBundleAdapterError(
                f"public member {member.get('id')} sourceSpecVersion diverges from bundle"
            )

        for index, raw_constraint in enumerate(payload.get("constraints", [])):
            constraint = dict(
                _as_mapping(raw_constraint, field=f"portable constraints[{index}]")
            )
            _required_string(constraint.get("id"), field=f"portable constraints[{index}].id")
            _required_string(
                constraint.get("statement"), field=f"portable constraints[{index}].statement"
            )
            structured_constraints.append(copy.deepcopy(constraint))
        for index, raw_budget in enumerate(payload.get("budgets", [])):
            budget = dict(_as_mapping(raw_budget, field=f"portable budgets[{index}]"))
            _required_string(budget.get("currency"), field=f"portable budgets[{index}].currency")
            budgets.append(copy.deepcopy(budget))
        for evidence_ref in payload.get("evidenceRequirements", []):
            if not isinstance(evidence_ref, str):
                raise WorldBundleAdapterError("portable evidenceRequirements must contain strings")
            if evidence_ref not in evidence_requirements:
                evidence_requirements.append(evidence_ref)
        for index, raw_assertion in enumerate(payload.get("successAssertions", [])):
            assertion = dict(
                _as_mapping(raw_assertion, field=f"portable successAssertions[{index}]")
            )
            _required_string(assertion.get("id"), field=f"portable successAssertions[{index}].id")
            _required_string(
                assertion.get("description"),
                field=f"portable successAssertions[{index}].description",
            )
            success_assertions.append(copy.deepcopy(assertion))

    constraints = [str(item["statement"]) for item in structured_constraints]
    success_description = " ".join(str(item["description"]) for item in success_assertions)
    return (
        public_member_payloads,
        structured_constraints,
        constraints,
        budgets,
        evidence_requirements,
        success_assertions,
        success_description,
    )


def _collect_private_entries(
    members: Sequence[Mapping[str, Any]],
    *,
    key: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for member in members:
        if member.get("partition") != "private-evaluator":
            continue
        payload = _as_mapping(member.get("payload"), field=f"member:{member.get('id')}.payload")
        raw_entries = payload.get(key, [])
        if not isinstance(raw_entries, list):
            raise WorldBundleAdapterError(f"private evaluator {key} must be an array")
        for index, raw_entry in enumerate(raw_entries):
            entries.append(
                dict(_as_mapping(raw_entry, field=f"private evaluator {key}[{index}]"))
            )
    return entries


def _state_assertion_from_woyengi(raw: Mapping[str, Any], *, context: str) -> StateAssertion:
    operator_map = {
        "EQUALS": AssertionComparison.EQUAL,
        "EQUAL": AssertionComparison.EQUAL,
        "NOT_EQUALS": AssertionComparison.NOT_EQUAL,
        "NOT_EQUAL": AssertionComparison.NOT_EQUAL,
        "LESS_THAN": AssertionComparison.LESS_THAN,
        "LESS_THAN_OR_EQUAL": AssertionComparison.LESS_THAN_OR_EQUAL,
        "GREATER_THAN": AssertionComparison.GREATER_THAN,
        "GREATER_THAN_OR_EQUAL": AssertionComparison.GREATER_THAN_OR_EQUAL,
        "CONTAINS": AssertionComparison.CONTAINS,
        "IN": AssertionComparison.IN,
    }
    path = _required_string(raw.get("path"), field=f"{context}.path")
    if "." not in path:
        raise WorldBundleAdapterError(
            f"{context} path {path!r} cannot be losslessly split into Veritas object/field identity"
        )
    object_id, field_name = path.split(".", 1)
    if not object_id or not field_name:
        raise WorldBundleAdapterError(f"{context} path {path!r} is not a valid state path")
    raw_operator = _required_string(raw.get("operator"), field=f"{context}.operator")
    comparison = operator_map.get(raw_operator)
    if comparison is None:
        raise WorldBundleAdapterError(
            f"{context} operator {raw_operator!r} has no lossless Veritas mapping"
        )
    if "value" not in raw:
        raise WorldBundleAdapterError(f"{context}.value is required for lossless mapping")
    tolerance = raw.get("tolerance")
    if tolerance is not None and not isinstance(tolerance, (int, float)):
        raise WorldBundleAdapterError(f"{context}.tolerance must be numeric")
    return StateAssertion(
        object_id=object_id,
        field_name=field_name,
        expected_value=copy.deepcopy(raw["value"]),
        tolerance=float(tolerance) if tolerance is not None else None,
        comparison=comparison,
    )


def _private_projection(
    *,
    bundle: Mapping[str, Any],
    members: Sequence[Mapping[str, Any]],
    public_actions: Sequence[PublicActionSpec],
    records: Sequence[OperationalRecord],
    evidence_requirements: Sequence[str],
) -> tuple[list[StateAssertion], list[OperationalInvariant], list[HiddenActionEffect], list[str], list[str]]:
    refs = _private_partition_refs(bundle)
    target_entries = _collect_private_entries(members, key="targetAssertions")
    invariant_entries = _collect_private_entries(members, key="invariants")
    effect_entries = _collect_private_entries(members, key="hiddenEffects")
    locator_entries = _collect_private_entries(members, key="evidenceLocators")

    blockers: list[str] = []

    def index_entries(entries: Sequence[Mapping[str, Any]], *, category: str) -> dict[str, Mapping[str, Any]]:
        indexed: dict[str, Mapping[str, Any]] = {}
        for entry in entries:
            entry_id = entry.get("id") if category != "evidence locator" else entry.get("ref")
            if not isinstance(entry_id, str) or not entry_id:
                blockers.append(f"{category} entry lacks a stable id/ref required for lossless mapping")
                continue
            if entry_id in indexed:
                blockers.append(f"duplicate {category} entry {entry_id}")
            indexed[entry_id] = entry
        return indexed

    target_by_id = index_entries(target_entries, category="target assertion")
    invariant_by_id = index_entries(invariant_entries, category="invariant")
    effect_by_id = index_entries(effect_entries, category="hidden effect")
    locator_by_ref = index_entries(locator_entries, category="evidence locator")

    target_state: list[StateAssertion] = []
    for ref in refs["targetAssertionRefs"]:
        raw = target_by_id.get(ref)
        if raw is None:
            blockers.append(f"target assertion {ref} is referenced but not materialized")
            continue
        try:
            target_state.append(_state_assertion_from_woyengi(raw, context=f"target assertion {ref}"))
        except WorldBundleAdapterError as exc:
            blockers.append(str(exc))

    invariants: list[OperationalInvariant] = []
    for ref in refs["invariantRefs"]:
        raw = invariant_by_id.get(ref)
        if raw is None:
            blockers.append(f"invariant {ref} is referenced but not materialized")
            continue
        assertion_raw = raw.get("assertion")
        severity = raw.get("severity")
        scope = raw.get("scope")
        if not isinstance(assertion_raw, Mapping) or severity not in {
            "low",
            "medium",
            "high",
            "critical",
        } or scope not in {"final", "always"}:
            blockers.append(
                f"invariant {ref} cannot be mapped losslessly: portable material must provide "
                "an executable assertion plus explicit severity and scope"
            )
            continue
        try:
            assertion = _state_assertion_from_woyengi(
                assertion_raw, context=f"invariant {ref}.assertion"
            )
        except WorldBundleAdapterError as exc:
            blockers.append(str(exc))
            continue
        statement = raw.get("statement")
        if not isinstance(statement, str) or not statement:
            blockers.append(f"invariant {ref} needs a statement for lossless description parity")
            continue
        invariants.append(
            OperationalInvariant(
                invariant_id=ref,
                description=statement,
                assertion=assertion,
                severity=severity,
                scope=scope,
            )
        )

    action_names = {action.name for action in public_actions}
    effects: list[HiddenActionEffect] = []
    for ref in refs["hiddenEffectRefs"]:
        raw = effect_by_id.get(ref)
        if raw is None:
            blockers.append(f"hidden effect {ref} is referenced but not materialized")
            continue
        action_ref = raw.get("actionRef")
        transition = raw.get("transition")
        if not isinstance(action_ref, str) or action_ref not in action_names:
            blockers.append(
                f"hidden effect {ref} cannot be mapped losslessly: actionRef must name a declared public action"
            )
            continue
        if not isinstance(transition, Mapping):
            blockers.append(
                f"hidden effect {ref} cannot be mapped losslessly: descriptive effect text is not "
                "an executable Veritas transition"
            )
            continue
        required_state: list[StateAssertion] = []
        try:
            for index, raw_assertion in enumerate(transition.get("requiredState", [])):
                required_state.append(
                    _state_assertion_from_woyengi(
                        _as_mapping(raw_assertion, field=f"hidden effect {ref}.requiredState[{index}]"),
                        context=f"hidden effect {ref}.requiredState[{index}]",
                    )
                )
        except WorldBundleAdapterError as exc:
            blockers.append(str(exc))
            continue
        set_state = transition.get("setState", {})
        if not isinstance(set_state, Mapping):
            blockers.append(f"hidden effect {ref}.transition.setState must be an object")
            continue
        observable = transition.get("observableResult", {})
        blocked_observable = transition.get("blockedObservableResult", {})
        if not isinstance(observable, Mapping) or not isinstance(blocked_observable, Mapping):
            blockers.append(f"hidden effect {ref} observable results must be objects")
            continue
        effects.append(
            HiddenActionEffect(
                action_name=action_ref,
                required_parameters=copy.deepcopy(dict(transition.get("requiredParameters", {}))),
                required_state=required_state,
                required_prior_actions=list(transition.get("requiredPriorActions", [])),
                set_state=copy.deepcopy(dict(set_state)),
                observable_result=copy.deepcopy(dict(observable)),
                blocked_observable_result=copy.deepcopy(dict(blocked_observable)),
                emitted_side_effects=list(transition.get("emittedSideEffects", [])),
                forbidden=bool(transition.get("forbidden", False)),
                consequence_severity=float(transition.get("consequenceSeverity", 0.0)),
            )
        )

    for ref in refs["evidenceLocatorRefs"]:
        if ref not in locator_by_ref:
            blockers.append(f"private evidence locator {ref} is referenced but not materialized")

    record_ids = {record.record_id for record in records}
    required_evidence_ids: list[str] = []
    for evidence_ref in evidence_requirements:
        if evidence_ref not in record_ids:
            blockers.append(
                f"required evidence {evidence_ref} cannot be mapped losslessly: no agent-visible "
                "OperationalRecord with that identity is materialized"
            )
        else:
            required_evidence_ids.append(evidence_ref)

    expected_categories = (
        (refs["targetAssertionRefs"], target_by_id, "target assertion"),
        (refs["invariantRefs"], invariant_by_id, "invariant"),
        (refs["hiddenEffectRefs"], effect_by_id, "hidden effect"),
        (refs["evidenceLocatorRefs"], locator_by_ref, "evidence locator"),
    )
    for expected_refs, indexed, category in expected_categories:
        extras = sorted(set(indexed) - set(expected_refs))
        if extras:
            blockers.append(f"unreferenced private {category} material would be dropped: {extras}")

    if blockers:
        raise WorldBundleAdapterError(
            "portable WorldBundle cannot achieve lossless Woyengi -> Veritas parity:\n- "
            + "\n- ".join(blockers)
        )
    return target_state, invariants, effects, required_evidence_ids, list(locator_by_ref)


def adapt_world_bundle_artifact(
    artifact: Mapping[str, Any],
    *,
    domain: WorldDomain = WorldDomain.ENTERPRISE_OPERATIONS,
    fixture_sha256: str | None = None,
) -> OperationalEpisode:
    """Adapt a complete `woyengi.world-bundle-artifact.v0.1` in-process.

    Full artifact identities and evaluator-private member hashes stay on the oracle side.
    The public episode is reconstructed from only Woyengi's public bundle partition and
    materialized public members.
    """

    artifact_map = copy.deepcopy(dict(_as_mapping(artifact, field="artifact")))
    source_artifact_id = _required_string(artifact_map.get("artifactId"), field="artifactId")
    bundle, members = _normalize_artifact(artifact_map)
    bundle_id = _required_string(bundle.get("id"), field="bundle.id")
    source_spec_ref = _required_string(bundle.get("sourceSpecRef"), field="bundle.sourceSpecRef")
    source_spec_version = _required_string(
        bundle.get("sourceSpecVersion"), field="bundle.sourceSpecVersion"
    )
    compatibility = copy.deepcopy(
        dict(_as_mapping(bundle.get("compatibility"), field="bundle.compatibility"))
    )
    public = _as_mapping(bundle.get("public"), field="bundle.public")
    objective = _required_string(public.get("objective"), field="bundle.public.objective")
    actor_roles = _as_string_list(public.get("actorRoles", []), field="bundle.public.actorRoles")
    outcome_refs = _as_string_list(
        public.get("outcomeContractRefs", []), field="bundle.public.outcomeContractRefs"
    )
    public_provenance = _as_string_list(
        public.get("provenanceRefs", []), field="bundle.public.provenanceRefs"
    )
    top_level_provenance = _as_string_list(
        bundle.get("provenanceRefs", []), field="bundle.provenanceRefs"
    )
    combined_provenance = list(dict.fromkeys([*public_provenance, *top_level_provenance]))
    _, public_manifest, private_manifest = _manifest_index(bundle)
    private_refs = _private_partition_refs(bundle)

    (
        public_member_payloads,
        structured_constraints,
        constraints,
        budgets,
        evidence_requirements,
        success_assertions,
        success_description,
    ) = _portable_public_semantics(bundle=bundle, members=members)
    max_cost, max_tool_calls = _runtime_budget_projection(budgets)
    actions, action_bindings = _build_actions(public)
    records = _build_records(
        public,
        provenance_refs=combined_provenance,
        preserve_record_identity=True,
    )

    target_state, invariants, effects, required_evidence_ids, _ = _private_projection(
        bundle=bundle,
        members=members,
        public_actions=actions,
        records=records,
        evidence_requirements=evidence_requirements,
    )

    private_member_payloads = {
        str(member["id"]): copy.deepcopy(member["payload"])
        for member in members
        if member.get("partition") == "private-evaluator"
    }
    public_member_ids = [
        str(member["id"]) for member in members if member.get("partition") == "public"
    ]

    task = TaskContract(
        task_id=bundle_id,
        world_id=bundle_id,
        domain=domain,
        objective=objective,
        role=" | ".join(actor_roles),
        permitted_systems=[WOYENGI_SYSTEM],
        available_actions=actions,
        constraints=constraints,
        success_description=success_description,
        metadata={
            "woyengi": {
                "semantic_authority": "woyengi",
                "actor_roles": copy.deepcopy(actor_roles),
                "action_surface": copy.deepcopy(
                    _as_list(public.get("actionSurface", []), field="bundle.public.actionSurface")
                ),
                "action_bindings": copy.deepcopy(action_bindings),
                "observation_refs": copy.deepcopy(
                    _as_string_list(
                        public.get("observationRefs", []), field="bundle.public.observationRefs"
                    )
                ),
                "asset_descriptors": copy.deepcopy(
                    _as_list(
                        public.get("assetDescriptors", []), field="bundle.public.assetDescriptors"
                    )
                ),
                "outcome_contract_refs": copy.deepcopy(outcome_refs),
                "constraints": copy.deepcopy(structured_constraints),
                "budgets": copy.deepcopy(budgets),
                "evidence_requirements": copy.deepcopy(evidence_requirements),
                "success_assertions": copy.deepcopy(success_assertions),
                "provenance_refs": copy.deepcopy(combined_provenance),
                "partition_manifest": copy.deepcopy(public_manifest),
                "public_member_ids": public_member_ids,
                "public_member_payloads": copy.deepcopy(public_member_payloads),
            }
        },
    )

    oracle = WoyengiHiddenOracle(
        task_id=bundle_id,
        initial_state={},
        target_state=target_state,
        invariants=invariants,
        required_actions=[],
        required_action_order=[],
        required_action_counts={},
        forbidden_actions=[],
        required_evidence_ids=required_evidence_ids,
        action_effects=effects,
        max_cost=max_cost,
        max_tool_calls=max_tool_calls,
        metadata={
            "semantic_authority": "woyengi",
            "projection_status": "portable-artifact-lossless",
        },
        source_bundle_id=bundle_id,
        source_artifact_id=source_artifact_id,
        source_fixture_sha256=fixture_sha256,
        private_partition_manifest=copy.deepcopy(private_manifest),
        target_assertion_refs=copy.deepcopy(private_refs["targetAssertionRefs"]),
        invariant_refs=copy.deepcopy(private_refs["invariantRefs"]),
        hidden_effect_refs=copy.deepcopy(private_refs["hiddenEffectRefs"]),
        evidence_locator_refs=copy.deepcopy(private_refs["evidenceLocatorRefs"]),
        private_member_payloads=private_member_payloads,
    )

    episode = OperationalEpisode(
        episode_id=bundle_id,
        world_id=bundle_id,
        task=task,
        records=records,
        oracle=oracle,
        metadata={
            "woyengi_source": {
                # Do not publish full artifact ID/hash: both are content-bound to the
                # evaluator-private member. Public reconstruction uses only public IDs.
                "contract": WORLD_BUNDLE_CONTRACT,
                "artifact_contract": WORLD_BUNDLE_ARTIFACT_CONTRACT,
                "bundle_id": bundle_id,
                "bundle_version": WORLD_BUNDLE_VERSION,
                "source_spec_ref": source_spec_ref,
                "source_spec_version": source_spec_version,
                "compatibility": compatibility,
                "provenance_refs": copy.deepcopy(combined_provenance),
            },
            "adapter": {
                "contract": "veritas.woyengi-worldbundle-adapter.v0.1",
                "semantic_authority": "woyengi",
                "runtime_projection_domain": domain.value,
            },
        },
    )

    private_tokens = {
        source_artifact_id,
        *(member["id"] for member in members if member.get("partition") == "private-evaluator"),
        *(member["contentHash"] for member in members if member.get("partition") == "private-evaluator"),
        *private_refs["targetAssertionRefs"],
        *private_refs["invariantRefs"],
        *private_refs["hiddenEffectRefs"],
        *private_refs["evidenceLocatorRefs"],
    }
    if fixture_sha256 is not None:
        private_tokens.add(fixture_sha256)
    public_text = json.dumps(episode.public_payload(), sort_keys=True, ensure_ascii=False)
    leaks = sorted(str(token) for token in private_tokens if str(token) in public_text)
    if leaks:
        raise WorldBundleAdapterError(
            f"adapter leaked evaluator-private artifact identity/material into public_payload: {leaks}"
        )
    return episode


def adapt_world_bundle(
    bundle: Mapping[str, Any],
    *,
    member_payloads: Mapping[str, Any] | None = None,
    domain: WorldDomain = WorldDomain.ENTERPRISE_OPERATIONS,
) -> OperationalEpisode:
    """Adapt the logical Woyengi WorldBundle v0.1 seam without a Woyengi service.

    New cross-repository conformance should prefer the complete portable artifact via
    :func:`adapt_world_bundle_artifact`. This logical seam remains for deterministic
    scaffold/backward tests while Woyengi P0-003 establishes the portable container.
    """

    return _adapt_world_bundle(bundle, member_payloads=member_payloads, domain=domain)


def adapt_pinned_world_bundle_fixture(
    raw_fixture: bytes | str,
    *,
    expected_sha256: str,
    member_payloads: Mapping[str, Any] | None = None,
    domain: WorldDomain = WorldDomain.ENTERPRISE_OPERATIONS,
) -> OperationalEpisode:
    """Verify exact upstream bytes before adapting a logical or portable fixture.

    P0 final parity uses the complete `woyengi.world-bundle-artifact.v0.1` bytes/hash
    published by Woyengi issue #9. Hashing occurs before UTF-8 decoding or JSON parsing.
    """

    raw_bytes = raw_fixture.encode("utf-8") if isinstance(raw_fixture, str) else raw_fixture
    if not isinstance(raw_bytes, bytes):
        raise WorldBundleAdapterError("raw_fixture must be UTF-8 text or bytes")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise WorldBundleAdapterError(
            "expected fixture SHA-256 must be a 64-character hex digest"
        )
    try:
        int(expected_sha256, 16)
    except ValueError as exc:
        raise WorldBundleAdapterError("expected fixture SHA-256 must be hexadecimal") from exc

    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256.lower()):
        raise WorldBundleAdapterError(
            f"fixture SHA-256 mismatch: expected {expected_sha256.lower()}, got {actual_sha256}"
        )
    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorldBundleAdapterError("pinned WorldBundle fixture is not valid UTF-8 JSON") from exc
    root = _as_mapping(parsed, field="fixture")
    if root.get("contract") == WORLD_BUNDLE_ARTIFACT_CONTRACT:
        if member_payloads is not None:
            raise WorldBundleAdapterError(
                "portable WorldBundle artifacts already materialize members; member_payloads is not allowed"
            )
        return adapt_world_bundle_artifact(
            root,
            domain=domain,
            fixture_sha256=actual_sha256,
        )
    return _adapt_world_bundle(root, member_payloads=member_payloads, domain=domain)
