from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from investigation_world.integrations.woyengi.adapter import WORLD_BUNDLE_ARTIFACT_CONTRACT
from investigation_world.integrations.woyengi.portable import (
    adapt_pinned_world_bundle_fixture as _adapt_pinned_world_bundle_fixture,
)
from investigation_world.operational.models import OperationalEpisode, WorldDomain


def adapt_pinned_world_bundle_fixture(
    raw_fixture: bytes | str,
    *,
    expected_sha256: str,
    member_payloads: Mapping[str, Any] | None = None,
    domain: WorldDomain = WorldDomain.ENTERPRISE_OPERATIONS,
) -> OperationalEpisode:
    episode = _adapt_pinned_world_bundle_fixture(
        raw_fixture,
        expected_sha256=expected_sha256,
        member_payloads=member_payloads,
        domain=domain,
    )
    raw_bytes = raw_fixture.encode("utf-8") if isinstance(raw_fixture, str) else raw_fixture
    try:
        root = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):  # underlying adapter already validates
        return episode

    # The legacy logical fixture hash binds only the public logical bundle; evaluator
    # payloads arrive through a separate sidecar. Preserve its historical public
    # provenance field for compatibility. Complete portable-artifact hashes remain
    # evaluator-private because they bind private member bytes.
    if not isinstance(root, dict) or root.get("contract") == WORLD_BUNDLE_ARTIFACT_CONTRACT:
        return episode

    metadata = copy.deepcopy(episode.metadata)
    source = metadata.setdefault("woyengi_source", {})
    if isinstance(source, dict):
        source["fixture_sha256"] = expected_sha256
    return OperationalEpisode(
        episode_id=episode.episode_id,
        world_id=episode.world_id,
        task=episode.task,
        records=episode.records,
        oracle=episode.oracle,
        metadata=metadata,
    )
