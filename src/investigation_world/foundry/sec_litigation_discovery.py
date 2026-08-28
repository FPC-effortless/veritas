from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

from investigation_world.foundry.public_investigation_data import (
    ArtifactRole,
    DatasetSplit,
    InvestigationStatus,
    PublicInvestigationCase,
    PublicInvestigationDataset,
    SourceArtifact,
)

_SEC_HOSTS = {"sec.gov", "www.sec.gov"}
_RELEASE_PATTERN = re.compile(r"\bLR-\s*(\d{4,6})\b", re.IGNORECASE)
_DATE_PATTERN = re.compile(
    r"\b(?:Jan\.|Feb\.|March|April|May|June|July|Aug\.|Sept\.|Oct\.|Nov\.|Dec\.)"
    r"\s+\d{1,2},\s+\d{4}\b"
)
_SAFE_ID = re.compile(r"[^a-z0-9]+")
_PUBLIC_TERMS = (
    "complaint",
    "application",
    "memorandum",
    "declaration",
    "administrative subpoena",
    "motion",
    "order instituting proceedings",
)
_VERIFIER_TERMS = (
    "final judgment",
    "judgment",
    "dismissal",
    "stipulation",
    "settlement",
    "consent",
    "decree",
    "opinion",
    "summary judgment",
    "order granting",
)


class _SecTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self._in_row = False
        self._row_text: list[str] = []
        self._anchors: list[dict[str, str]] = []
        self._active_href: str | None = None
        self._active_text: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() == "tr":
            self._in_row = True
            self._row_text = []
            self._anchors = []
        if not self._in_row or tag.casefold() != "a":
            return
        attributes = dict(attrs)
        self._active_href = attributes.get("href")
        self._active_text = []

    def handle_data(self, data: str) -> None:
        if not self._in_row:
            return
        self._row_text.append(data)
        if self._active_href is not None:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if self._in_row and normalized == "a" and self._active_href is not None:
            text = " ".join("".join(self._active_text).split())
            self._anchors.append({"text": text, "href": self._active_href})
            self._active_href = None
            self._active_text = []
        if normalized == "tr" and self._in_row:
            text = " ".join("".join(self._row_text).split())
            self.rows.append({"text": text, "anchors": list(self._anchors)})
            self._in_row = False
            self._row_text = []
            self._anchors = []


def _host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").casefold()


def _require_sec_https(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.casefold() != "https":
        raise ValueError(f"SEC URL must use https: {url}")
    if _host(url) not in _SEC_HOSTS:
        raise ValueError(f"SEC URL host is not allowed: {url}")


def fetch_sec_page(url: str, *, timeout_seconds: float = 30.0) -> str:
    _require_sec_https(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "VeritasInvestigationCorpus/1.0 contact=repository-maintainer"
        },
    )
    # B310 is mitigated by HTTPS-only SEC host validation before and after redirects.
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
        final_url = response.geturl()
        _require_sec_https(final_url)
        payload = response.read(8 * 1024 * 1024 + 1)
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError("SEC index page exceeded the 8 MiB safety cap")
    return payload.decode("utf-8", errors="replace")


def _parse_date(text: str) -> date:
    match = _DATE_PATTERN.search(text)
    if match is None:
        raise ValueError(f"SEC row is missing a publication date: {text[:120]}")
    value = match.group(0).replace("Sept.", "Sep.")
    for format_string in ("%b. %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, format_string).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported SEC publication date: {value}")


def _artifact_kind(title: str) -> str | None:
    normalized = " ".join(title.casefold().split())
    if "order instituting proceedings" in normalized:
        return "public"
    if any(term in normalized for term in _VERIFIER_TERMS):
        return "verifier"
    if any(term in normalized for term in _PUBLIC_TERMS):
        return "public"
    return None


def _artifact_id(case_id: str, title: str, index: int) -> str:
    slug = _SAFE_ID.sub("-", title.casefold()).strip("-")[:48] or "document"
    return f"{case_id}-{index:02d}-{slug}"


def parse_sec_litigation_page(
    html: str,
    *,
    page_url: str,
    paired_only: bool = True,
) -> list[PublicInvestigationCase]:
    _require_sec_https(page_url)
    parser = _SecTableParser()
    parser.feed(html)
    cases: list[PublicInvestigationCase] = []

    for row in parser.rows:
        row_text = str(row["text"])
        release_match = _RELEASE_PATTERN.search(row_text)
        anchors = list(row["anchors"])
        if release_match is None or not anchors:
            continue
        case_id = f"LR-{release_match.group(1)}"
        event_date = _parse_date(row_text)
        release_url = urllib.parse.urljoin(page_url, anchors[0]["href"])
        if _host(release_url) not in _SEC_HOSTS:
            continue

        public_artifacts: list[SourceArtifact] = []
        verifier_artifacts: list[SourceArtifact] = []
        unclassified_count = 0
        for index, anchor in enumerate(anchors[1:], start=1):
            link_title = anchor["text"].strip()
            link_url = urllib.parse.urljoin(page_url, anchor["href"])
            if _host(link_url) not in _SEC_HOSTS:
                continue
            kind = _artifact_kind(link_title)
            if kind is None:
                unclassified_count += 1
                continue
            artifact = SourceArtifact(
                artifact_id=_artifact_id(case_id, link_title, index),
                title=link_title,
                url=link_url,
                role=(
                    ArtifactRole.VERIFIER_REFERENCE
                    if kind == "verifier"
                    else ArtifactRole.OTHER_EVIDENCE
                ),
                media_type=(
                    "application/pdf"
                    if urllib.parse.urlparse(link_url).path.casefold().endswith(".pdf")
                    else "text/html"
                ),
                source_published_date=event_date,
                metadata={"sec_release": case_id, "classification": kind},
            )
            if kind == "verifier":
                verifier_artifacts.append(artifact)
            else:
                public_artifacts.append(artifact)

        if paired_only and (not public_artifacts or not verifier_artifacts):
            continue
        if not public_artifacts and not verifier_artifacts:
            continue
        cases.append(
            PublicInvestigationCase(
                case_id=case_id,
                source_id="sec_litigation",
                title=f"SEC litigation case {case_id}",
                jurisdiction="United States",
                domain="financial_misconduct",
                event_date=event_date,
                status=InvestigationStatus.COMPLETED,
                split=DatasetSplit.TRAIN_REFERENCE,
                objective=(
                    "Assess the supplied pre-disposition court record and determine the "
                    "legally supported disposition without access to later judgments, "
                    "dismissals, settlements, or consent outcomes."
                ),
                public_evidence=public_artifacts,
                verifier_references=verifier_artifacts,
                metadata={
                    "release_number": case_id,
                    "unclassified_link_count": unclassified_count,
                    "label_semantics": "court_or_case_disposition_not_factual_ground_truth",
                },
            )
        )
    return cases


def discover_sec_litigation_dataset(
    *,
    as_of: date,
    max_pages: int = 200,
    maximum_cases: int | None = None,
    delay_seconds: float = 0.15,
    fetcher: Callable[[str], str] = fetch_sec_page,
) -> PublicInvestigationDataset:
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    if maximum_cases is not None and maximum_cases < 1:
        raise ValueError("maximum_cases must be positive when provided")

    by_id: dict[str, PublicInvestigationCase] = {}
    for page in range(max_pages):
        page_url = (
            "https://www.sec.gov/enforcement-litigation/litigation-releases"
            f"?month=All&order=field_publish_date&page={page}&populate=&sort=desc&year=All"
        )
        html = fetcher(page_url)
        page_cases = parse_sec_litigation_page(html, page_url=page_url, paired_only=True)
        if not page_cases and page > 0:
            break
        for case in page_cases:
            by_id[case.case_id] = case
            if maximum_cases is not None and len(by_id) >= maximum_cases:
                break
        if maximum_cases is not None and len(by_id) >= maximum_cases:
            break
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    cases = sorted(by_id.values(), key=lambda item: (item.event_date, item.case_id))
    return PublicInvestigationDataset(
        dataset_id=f"sec-litigation-paired-{as_of.isoformat()}",
        version=as_of.strftime("%Y.%m.%d"),
        as_of=as_of,
        source_registry_id="veritas-public-operations-sources",
        cases=cases,
        notes=[
            (
                "SEC civil enforcement cases with pre-disposition filings separated "
                "from later court or case disposition documents."
            ),
            (
                "Historical public cases are training/reference material, not "
                "contamination-resistant holdouts."
            ),
            "SEC complaints contain allegations, not adjudicated facts.",
            (
                "Verifier references encode legal/procedural dispositions, not ground "
                "truth about reality."
            ),
            (
                "Litigation release narrative pages are not emitted into the public "
                "projection because they may summarize outcomes."
            ),
        ],
    )
