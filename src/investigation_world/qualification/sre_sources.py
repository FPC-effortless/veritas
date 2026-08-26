from __future__ import annotations

from datetime import datetime
from typing import Any

from investigation_world.qualification.sre import SRECausalClass, SREIncidentSource


STATUSPAGE_INCIDENT_ENDPOINTS: dict[str, str] = {
    "github": "https://www.githubstatus.com/api/v2/incidents.json",
    "atlassian": "https://status.atlassian.com/api/v2/incidents.json",
    "cloudflare": "https://www.cloudflarestatus.com/api/v2/incidents.json",
    "datadog": "https://status.datadoghq.com/api/v2/incidents.json",
    "digitalocean": "https://status.digitalocean.com/api/v2/incidents.json",
    # SRE v2 provider family.
    "openai": "https://status.openai.com/api/v2/incidents.json",
    "twilio": "https://status.twilio.com/api/v2/incidents.json",
    "vercel": "https://www.vercel-status.com/api/v2/incidents.json",
    # Independent SRE v3 provider family. None of these providers appear in the v1 or v2
    # qualification panels. Keep this family frozen before inspecting its private labels.
    "circleci": "https://status.circleci.com/api/v2/incidents.json",
    "discord": "https://discordstatus.com/api/v2/incidents.json",
    "dropbox": "https://status.dropbox.com/api/v2/incidents.json",
    "mongodb": "https://status.mongodb.com/api/v2/incidents.json",
    "npm": "https://status.npmjs.org/api/v2/incidents.json",
}


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _infer_causal_class(text: str) -> SRECausalClass:
    value = text.casefold()
    if any(token in value for token in ("deploy", "release", "rollback", "regression", "change introduced")):
        return SRECausalClass.REGRESSION
    if any(token in value for token in ("capacity", "traffic", "overload", "saturation", "rate limit", "exhaust")):
        return SRECausalClass.CAPACITY
    if any(token in value for token in ("network", "dns", "database", "storage", "hardware", "region", "power")):
        return SRECausalClass.INFRASTRUCTURE
    return SRECausalClass.TRANSIENT


def parse_statuspage_incidents(
    provider: str,
    payload: dict[str, Any],
    *,
    endpoint: str | None = None,
    early_update_count: int = 2,
) -> list[SREIncidentSource]:
    """Compile resolved Statuspage incidents into early-public/later-private evidence.

    Statuspage returns incident updates newest-first on common provider pages. We reorder by
    timestamp, expose the earliest updates to the candidate, and reserve later resolution/RCA
    updates for private truth. Incidents without a separable later evidence segment are discarded.
    """
    incidents: list[SREIncidentSource] = []
    source_endpoint = endpoint or STATUSPAGE_INCIDENT_ENDPOINTS.get(provider, "")
    for raw in payload.get("incidents", []):
        if not isinstance(raw, dict) or not raw.get("resolved_at"):
            continue
        updates = [item for item in raw.get("incident_updates", []) if isinstance(item, dict)]
        updates.sort(key=lambda item: str(item.get("created_at") or item.get("updated_at") or ""))
        bodies = [str(item.get("body", "")).strip() for item in updates if str(item.get("body", "")).strip()]
        if len(bodies) <= early_update_count:
            continue
        early = bodies[:early_update_count]
        later = bodies[early_update_count:]
        private_text = "\n".join(later)
        incident_id = str(raw.get("id", "")).strip()
        if not incident_id:
            continue
        source_uri = str(raw.get("shortlink") or "").strip() or f"{source_endpoint}#{incident_id}"
        incidents.append(
            SREIncidentSource(
                provider=provider,
                incident_id=incident_id,
                source_uri=source_uri,
                title=str(raw.get("name", "Incident")),
                early_updates=early,
                resolution_updates=later,
                causal_class=_infer_causal_class(private_text),
                started_at=_parse_datetime(raw.get("started_at") or raw.get("created_at")),
                resolved_at=_parse_datetime(raw.get("resolved_at")),
                metadata={
                    "impact": raw.get("impact"),
                    "status": raw.get("status"),
                    "compiler": "statuspage-v2",
                    "source_endpoint": source_endpoint,
                },
            )
        )
    return incidents
