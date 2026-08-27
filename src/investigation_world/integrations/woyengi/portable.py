from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from investigation_world.integrations.woyengi.adapter import (
    WORLD_BUNDLE_ARTIFACT_CONTRACT,
    WorldBundleAdapterError,
    adapt_pinned_world_bundle_fixture as _adapt_pinned_world_bundle_fixture,
)
from investigation_world.operational.models import (
    ActionKind,
    OperationalEpisode,
    OperationalRecord,
    PublicActionSpec,
    TaskContract,
    WorldDomain,
)

_KIND_MAP = {
    "READ": ActionKind.READ,
    "WRITE": ActionKind.WRITE,
    "EXECUTE": ActionKind.EXECUTE,
    "COMMUNICATE": ActionKind.COMMUNICATE,
    "ESCALATE": ActionKind.ESCALATE,
    "SUBMIT": ActionKind.SUBMIT,
}


def adapt_pinned_world_bundle_fixture(
    raw_fixture: bytes | str,
    *,
    expected_sha256: str,
    member_payloads: Mapping[str, Any] | None = None,
    domain: WorldDomain = WorldDomain.ENTERPRISE_OPERATIONS,
) -> OperationalEpisode:
    """Verify and adapt the exact pinned Woyengi artifact without lossy public defaults.

    The legacy adapter remains the semantic/private-oracle parser. For complete portable
    artifacts this wrapper then restores Woyengi's declared logical systems, parameter
    names, exact integral public costs, and materialized public evidence records into
    Veritas-native public structures. No hidden material is used to enrich the public
    task.
    """

    episode = _adapt_pinned_world_bundle_fixture(
        raw_fixture,
        expected_sha256=expected_sha256,
        member_payloads=member_payloads,
        domain=domain,
    )

    raw_bytes = raw_fixture.encode("utf-8") if isinstance(raw_fixture, str) else raw_fixture
    try:
        root = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:  # pragma: no cover - legacy already checks
        raise WorldBundleAdapterError("pinned WorldBundle fixture is not valid UTF-8 JSON") from exc
    if not isinstance(root, dict) or root.get("contract") != WORLD_BUNDLE_ARTIFACT_CONTRACT:
        return episode

    bundle = _mapping(root.get("bundle"), "artifact.bundle")
    public = _mapping(bundle.get("public"), "artifact.bundle.public")
    actions = _portable_actions(public)
    permitted_systems = sorted({action.system for action in actions})
    records = _portable_records(root, episode.records)

    metadata = copy.deepcopy(episode.task.metadata)
    woyengi_metadata = metadata.setdefault("woyengi", {})
    if isinstance(woyengi_metadata, dict):
        woyengi_metadata["portable_action_projection"] = "lossless-public-v0.1"
        woyengi_metadata["permitted_systems"] = copy.deepcopy(permitted_systems)

    task = TaskContract(
        task_id=episode.task.task_id,
        world_id=episode.task.world_id,
        domain=episode.task.domain,
        objective=episode.task.objective,
        role=episode.task.role,
        permitted_systems=permitted_systems,
        available_actions=actions,
        constraints=copy.deepcopy(episode.task.constraints),
        success_description=episode.task.success_description,
        metadata=metadata,
    )

    projected = OperationalEpisode(
        episode_id=episode.episode_id,
        world_id=episode.world_id,
        task=task,
        records=records,
        oracle=episode.oracle,
        metadata=copy.deepcopy(episode.metadata),
    )

    if expected_sha256 in json.dumps(projected.public_payload(), sort_keys=True):
        raise WorldBundleAdapterError("fixture SHA-256 leaked into public payload")
    return projected


def _portable_actions(public: Mapping[str, Any]) -> list[PublicActionSpec]:
    raw_actions = public.get("actionSurface")
    if not isinstance(raw_actions, list):
        raise WorldBundleAdapterError("artifact.bundle.public.actionSurface must be an array")
    actions: list[PublicActionSpec] = []
    for index, raw in enumerate(raw_actions):
        action = _mapping(raw, f"actionSurface[{index}]")
        action_id = _text(action.get("id"), f"actionSurface[{index}].id")
        human_name = _text(action.get("name"), f"actionSurface[{index}].name")
        system_ref = _text(action.get("systemRef"), f"actionSurface[{index}].systemRef")
        kind = _KIND_MAP.get(action.get("kind"))
        if kind is None:
            raise WorldBundleAdapterError(
                f"actionSurface[{index}].kind has no Veritas mapping: {action.get('kind')!r}"
            )
        parameter_names = action.get("parameterNames")
        if not isinstance(parameter_names, list) or not all(
            isinstance(value, str) and value for value in parameter_names
        ):
            raise WorldBundleAdapterError(
                f"actionSurface[{index}].parameterNames must contain only non-empty strings"
            )

        cost = 0
        raw_cost = action.get("cost")
        if raw_cost is not None:
            cost_record = _mapping(raw_cost, f"actionSurface[{index}].cost")
            amount = cost_record.get("amount")
            currency = _text(cost_record.get("currency"), f"actionSurface[{index}].cost.currency")
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not float(amount).is_integer():
                raise WorldBundleAdapterError(
                    f"actionSurface[{index}].cost.amount cannot be represented losslessly by Veritas integer cost"
                )
            cost = int(amount)
            if cost < 0:
                raise WorldBundleAdapterError(f"actionSurface[{index}].cost.amount must be non-negative")
            # Currency remains preserved in adapter metadata/action_bindings. Veritas's
            # first-class cost slot is unit-only; the pinned v0.1 fixture uses one USD unit domain.
            if currency != "USD":
                raise WorldBundleAdapterError(
                    f"actionSurface[{index}] currency {currency!r} is not losslessly representable by the v0.1 Veritas unit projection"
                )

        actions.append(
            PublicActionSpec(
                # Keep the stable Woyengi action identity as the runtime dispatch name so
                # private actionRef bindings remain exact; retain the human name as description.
                name=action_id,
                kind=kind,
                system=system_ref,
                description=human_name,
                parameter_names=list(parameter_names),
                cost=cost,
            )
        )
    return actions


def _portable_records(root: Mapping[str, Any], legacy_records: list[OperationalRecord]) -> list[OperationalRecord]:
    by_id = {record.record_id: record for record in legacy_records}
    raw_members = root.get("members")
    if not isinstance(raw_members, list):
        raise WorldBundleAdapterError("artifact.members must be an array")
    for index, raw_member in enumerate(raw_members):
        member = _mapping(raw_member, f"members[{index}]")
        if member.get("partition") != "public" or member.get("kind") != "EVIDENCE_RECORD":
            continue
        payload = _mapping(member.get("payload"), f"members[{index}].payload")
        if payload.get("contract") != "woyengi.world-bundle.public-evidence.v0.1":
            raise WorldBundleAdapterError(
                f"members[{index}] EVIDENCE_RECORD has unsupported contract {payload.get('contract')!r}"
            )
        record_id = _text(payload.get("recordId"), f"members[{index}].payload.recordId")
        system_ref = _text(payload.get("systemRef"), f"members[{index}].payload.systemRef")
        record_type = _text(payload.get("recordType"), f"members[{index}].payload.recordType")
        object_id = _text(payload.get("objectId"), f"members[{index}].payload.objectId")
        searchable_text = _text(
            payload.get("searchableText"), f"members[{index}].payload.searchableText"
        )
        fields = _mapping(payload.get("fields"), f"members[{index}].payload.fields")
        provenance = payload.get("provenanceRefs")
        if not isinstance(provenance, list) or not all(isinstance(value, str) for value in provenance):
            raise WorldBundleAdapterError(
                f"members[{index}].payload.provenanceRefs must contain only strings"
            )
        by_id[record_id] = OperationalRecord(
            record_id=record_id,
            system=system_ref,
            record_type=record_type,
            object_id=object_id,
            fields=copy.deepcopy(dict(fields)),
            searchable_text=searchable_text,
            provenance_ids=list(provenance),
        )
    return list(by_id.values())


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorldBundleAdapterError(f"{field} must be an object")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldBundleAdapterError(f"{field} must be a non-empty string")
    return value
