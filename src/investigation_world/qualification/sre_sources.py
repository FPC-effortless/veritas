from __future__ import annotations

import re
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
    # SRE v3 provider family. This family is retired from private commercial evaluation because
    # historical Actions artifacts exposed its raw qualification material.
    "circleci": "https://status.circleci.com/api/v2/incidents.json",
    "discord": "https://discordstatus.com/api/v2/incidents.json",
    "dropbox": "https://status.dropbox.com/api/v2/incidents.json",
    "mongodb": "https://status.mongodb.com/api/v2/incidents.json",
    "npm": "https://status.npmjs.org/api/v2/incidents.json",
    # Fresh SRE v4 provider family. These Statuspage incident APIs were selected before v4 model
    # evaluation and are disjoint from the v1-v3 provider families.
    "render": "https://status.render.com/api/v2/incidents.json",
    "supabase": "https://status.supabase.com/api/v2/incidents.json",
    "elastic": "https://status.elastic.co/api/v2/incidents.json",
    "grafana": "https://status.grafana.com/api/v2/incidents.json",
    "figma": "https://status.figma.com/api/v2/incidents.json",
}


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _matches(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in patterns)


def _infer_causal_class_with_rule(text: str) -> tuple[SRECausalClass, str, bool]:
    """Infer a coarse causal class only from later/private evidence.

    Regression rules deliberately require causal wording. A generic phrase such as "deployed a
    fix" must not turn an unrelated incident into a regression label. The boolean indicates
    whether the private text contained an explicit causal signal rather than falling back to the
    residual transient class.
    """
    value = " ".join(text.split())

    regression_patterns = (
        r"\bregression\b",
        r"\b(?:recent|new|previous) (?:deploy(?:ment)?|release|version|change)\b.*\b(?:caus|introduc|trigger)",
        r"\b(?:caus|introduc|trigger)(?:ed|ing|es)? by\b.*\b(?:deploy(?:ment)?|release|change|configuration|config)\b",
        r"\b(?:configuration|config|code|software) change\b.*\b(?:caus|introduc|trigger)",
        r"\brollback\b.*\b(?:restor|resolv|recover)",
    )
    capacity_patterns = (
        r"\bcapacity\b",
        r"\b(?:traffic|request|load) (?:spike|surge)\b",
        r"\b(?:overload|saturat|resource exhaustion|exhausted|quota exhaustion)\w*\b",
        r"\brate limit(?:ing|ed)?\b",
        r"\btoo many connections\b",
        r"\bqueue backlog\b",
    )
    infrastructure_patterns = (
        r"\b(?:network|dns|routing|bgp) (?:issue|failure|outage|incident|partition)\b",
        r"\b(?:hardware|disk|storage|power) (?:failure|fault|outage|incident)\b",
        r"\b(?:database|datastore) (?:failover|failure|outage|unavailable|corruption)\b",
        r"\b(?:region|availability zone|data ?center) (?:failure|outage|incident)\b",
        r"\b(?:cloud|upstream|third[- ]party|dependency) provider (?:failure|outage|incident)\b",
    )
    transient_patterns = (
        r"\btransient\b",
        r"\bintermittent\b",
        r"\btemporary\b",
        r"\bself[- ]recover(?:ed|ing)?\b",
        r"\bautomatically recover(?:ed|ing)?\b",
        r"\bno persistent (?:fault|issue|cause)\b",
    )

    if _matches(value, regression_patterns):
        return SRECausalClass.REGRESSION, "explicit-regression", True
    if _matches(value, capacity_patterns):
        return SRECausalClass.CAPACITY, "explicit-capacity", True
    if _matches(value, infrastructure_patterns):
        return SRECausalClass.INFRASTRUCTURE, "explicit-infrastructure", True
    if _matches(value, transient_patterns):
        return SRECausalClass.TRANSIENT, "explicit-transient", True
    return SRECausalClass.TRANSIENT, "fallback-transient", False


def _infer_causal_class(text: str) -> SRECausalClass:
    return _infer_causal_class_with_rule(text)[0]


def parse_statuspage_incidents(
    provider: str,
    payload: dict[str, Any],
    *,
    endpoint: str | None = None,
    early_update_count: int = 2,
    require_explicit_causal_label: bool = False,
) -> list[SREIncidentSource]:
    """Compile resolved Statuspage incidents into early-public/later-private evidence.

    Statuspage returns incident updates newest-first on common provider pages. We reorder by
    timestamp, expose the earliest updates to the candidate, and reserve later resolution/RCA
    updates for private truth. Incidents without a separable later evidence segment are discarded.
    Commercial/private candidates can additionally require an explicit later causal signal instead
    of accepting the residual fallback class.
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
        causal_class, causal_rule, explicit_causal_signal = _infer_causal_class_with_rule(private_text)
        if require_explicit_causal_label and not explicit_causal_signal:
            continue
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
                causal_class=causal_class,
                started_at=_parse_datetime(raw.get("started_at") or raw.get("created_at")),
                resolved_at=_parse_datetime(raw.get("resolved_at")),
                metadata={
                    "impact": raw.get("impact"),
                    "status": raw.get("status"),
                    "compiler": "statuspage-v3-causal",
                    "source_endpoint": source_endpoint,
                    "causal_label_rule": causal_rule,
                    "explicit_causal_signal": explicit_causal_signal,
                },
            )
        )
    return incidents
