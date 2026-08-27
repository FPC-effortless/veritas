from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from investigation_world.qualification.sre import SRECausalClass, SREIncidentSource


SRE_V4_PROVIDERS: tuple[str, ...] = (
    "render",
    "supabase",
    "elastic",
    "grafana",
    "figma",
    "postman",
    "airtable",
    "webflow",
    "reddit",
    "claude",
    "instructure",
    "ibmcloudsecurity",
    "hedera",
    "snyk",
    "snowflake",
    "newrelic",
    "hubspot",
    "temporal",
)

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
    # Fresh SRE v4 provider family. These Statuspage incident APIs are disjoint from the v1-v3
    # provider families and are frozen before any v4 model evidence is run.
    "render": "https://status.render.com/api/v2/incidents.json",
    "supabase": "https://status.supabase.com/api/v2/incidents.json",
    "elastic": "https://status.elastic.co/api/v2/incidents.json",
    "grafana": "https://status.grafana.com/api/v2/incidents.json",
    "figma": "https://status.figma.com/api/v2/incidents.json",
    "postman": "https://status.postman.com/api/v2/incidents.json",
    "airtable": "https://status.airtable.com/api/v2/incidents.json",
    "webflow": "https://status.webflow.com/api/v2/incidents.json",
    "reddit": "https://www.redditstatus.com/api/v2/incidents.json",
    "claude": "https://status.claude.com/api/v2/incidents.json",
    "instructure": "https://status.instructure.com/api/v2/incidents.json",
    "ibmcloudsecurity": "https://statuspage.ibmcloudsecurity.com/api/v2/incidents.json",
    "hedera": "https://status.hedera.com/api/v2/incidents.json",
    "snyk": "https://status.snyk.io/api/v2/incidents.json",
    "snowflake": "https://status.snowflake.com/api/v2/incidents.json",
    "newrelic": "https://status.newrelic.com/api/v2/incidents.json",
    "hubspot": "https://status.hubspot.com/api/v2/incidents.json",
    "temporal": "https://status.temporal.io/api/v2/incidents.json",
}


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _matches(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in patterns)


def _infer_causal_class_with_rule(text: str) -> tuple[SRECausalClass, str, bool]:
    """Infer a coarse causal class only from later/private evidence.

    Rules require causal/resolution language rather than generic remediation language. In
    particular, "deployed a fix" is not evidence that a deployment caused the incident.
    """
    value = " ".join(text.split())

    regression_patterns = (
        r"\bregression\b",
        r"\b(?:recent|new|previous) (?:deploy(?:ment)?|release|version|change)\b.*\b(?:caus|introduc|trigger)",
        r"\b(?:caus|introduc|trigger)(?:ed|ing|es)? by\b.*\b(?:deploy(?:ment)?|release|change|configuration|config)\b",
        r"\b(?:configuration|config|code|software) change\b.*\b(?:caus|introduc|trigger)",
        r"\b(?:bad|incorrect|invalid|faulty) (?:configuration|config|deploy(?:ment)?|release|change)\b",
        r"\brollback\b.*\b(?:restor|resolv|recover|normal|function)",
        r"\broll(?:ed|ing)? back\b.*\b(?:restor|resolv|recover|normal|function)",
        r"\brevert(?:ed|ing)?\b.*\b(?:change|deploy|release|config|restor|resolv|recover)",
    )
    capacity_patterns = (
        r"\bcapacity\b",
        r"\b(?:traffic|request|load) (?:spike|surge)\b",
        r"\b(?:overload|saturat|resource exhaustion|exhausted|quota exhaustion)\w*\b",
        r"\brate limit(?:ing|ed)?\b",
        r"\btoo many connections\b",
        r"\bqueue backlog\b",
        r"\b(?:memory|cpu) pressure\b",
        r"\bconnection pool (?:exhaust|saturat)\w*\b",
        r"\bresource contention\b",
    )
    infrastructure_patterns = (
        r"\b(?:network|dns|routing|bgp)(?: connectivity)? (?:issue|fail(?:ed|ure)|outage|incident|partition)\b",
        r"\b(?:network|dns|routing|bgp)(?: connectivity)? (?:was |has )?(?:degraded|unavailable)\b",
        r"\b(?:hardware|disk|storage|power) (?:fail(?:ed|ure)|fault|outage|incident)\b",
        r"\b(?:database|datastore) (?:failover|fail(?:ed|ure)|outage|unavailable|corruption)\b",
        r"\b(?:region|availability zone|data ?center) (?:fail(?:ed|ure)|outage|incident|unavailable)\b",
        r"\b(?:cloud|upstream|third[- ]party|dependency) provider (?:fail(?:ed|ure)|outage|incident|unavailable)\b",
        r"\b(?:degraded|failed|unhealthy) (?:[\w.-]+ ){0,3}(?:node|host|server)\b",
        r"\b(?:node|host|server|cluster) (?:fail(?:ed|ure)|unavailable|unhealthy)\b",
        r"\b(?:fiber|cable) (?:cut|failure)\b",
        r"\b(?:isp|carrier|transit provider|network provider)\b.*\b(?:outage|failure|connectivity|routing|unavailable)\b",
        r"\b(?:outage|failure|connectivity|routing)\b.*\b(?:isp|carrier|transit provider|network provider)\b",
        r"\b(?:packet loss|network partition|connection reset)\b",
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

    Incident updates are ordered by creation time. The earliest updates form public evidence; later
    resolution/RCA updates and an optional Statuspage postmortem form evaluator-only evidence.
    Incidents without a separable later evidence segment are discarded.
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
        postmortem = str(raw.get("postmortem_body") or "").strip()
        if postmortem and postmortem not in later:
            later = [*later, postmortem]
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
                    "compiler": "statuspage-v4-causal",
                    "source_endpoint": source_endpoint,
                    "causal_label_rule": causal_rule,
                    "explicit_causal_signal": explicit_causal_signal,
                    "postmortem_included": bool(postmortem),
                },
            )
        )
    return incidents
