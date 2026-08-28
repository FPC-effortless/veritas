from __future__ import annotations

import hashlib
import urllib.parse
import urllib.request
from pathlib import Path

_CDC_NORS_EXPORT_URL = (
    "https://data.cdc.gov/api/views/5xkq-dg7x/rows.csv?accessType=DOWNLOAD"
)
_CDC_HOSTS = {"data.cdc.gov"}


def _host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").casefold()


def _require_cdc_https(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.casefold() != "https":
        raise ValueError(f"CDC source URL must use https: {url}")
    if _host(url) not in _CDC_HOSTS:
        raise ValueError(f"CDC source host is not allowed: {url}")


def fetch_cdc_nors_csv(
    destination: Path,
    *,
    timeout_seconds: float = 60.0,
    max_bytes: int = 256 * 1024 * 1024,
) -> dict[str, str | int]:
    """Fetch the official NORS CSV into a private/staging path.

    The raw export includes verifier-bearing fields and must not be exposed to an
    evaluated agent. Callers are expected to compile it through a structured source
    profile immediately and publish only the separated public projection.
    """

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    _require_cdc_https(_CDC_NORS_EXPORT_URL)
    request = urllib.request.Request(
        _CDC_NORS_EXPORT_URL,
        headers={"User-Agent": "VeritasInvestigationCorpus/1.0"},
    )
    # B310 is mitigated by HTTPS-only CDC host validation before and after redirects.
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
        final_url = response.geturl()
        _require_cdc_https(final_url)
        payload = response.read(max_bytes + 1)
        content_type = response.headers.get_content_type()
    if len(payload) > max_bytes:
        raise ValueError(f"CDC NORS export exceeds max_bytes={max_bytes}")
    if content_type not in {"text/csv", "application/octet-stream", "text/plain"}:
        raise ValueError(f"unexpected CDC NORS content type: {content_type}")
    header = payload.splitlines()[0].decode("utf-8-sig", errors="strict") if payload else ""
    if "Etiology" not in header or "Primary Mode" not in header or "Year" not in header:
        raise ValueError("CDC NORS export does not match the expected streamlined schema")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return {
        "source_url": _CDC_NORS_EXPORT_URL,
        "byte_count": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "content_type": content_type,
    }
