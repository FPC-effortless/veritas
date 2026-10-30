"""Keep the public inquiry path and commercial readiness boundaries explicit."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_pilot_default_uses_existing_public_inquiry_form_and_keeps_override():
    page = (ROOT / "app/page.tsx").read_text()
    assert "process.env.NEXT_PUBLIC_PILOT_CONTACT" in page
    assert (
        "https://github.com/FPC-effortless/veritas/issues/new?template=commercial-evaluation.yml"
        in page
    )
    assert (ROOT / ".github/ISSUE_TEMPLATE/commercial-evaluation.yml").is_file()
    assert "public" in page.lower()
    assert "credentials" in page.lower()
    assert "customer-confidential" in page.lower()
    assert page.count("href={pilotHref}") == 3


def test_readiness_links_current_authority_and_preserves_seller_gates():
    path = ROOT / "docs/commercial/procurement-readiness.md"
    doc = path.read_text()
    assert "0.11.0" in doc
    assert "v0.5.0" not in doc
    assert "launch-checklist.md" in doc
    assert "BUILD_STATUS.md" in doc
    for requirement in (
        "Seller legal/contracting identity",
        "Private credential-exchange channel",
        "Retention/deletion terms",
        "Incident escalation/contact owner",
        "First external design partner",
        "backup/recovery",
    ):
        assert any(line.startswith("- [ ]") and requirement in line for line in doc.splitlines())
    for link in re.findall(r"\]\(([^)]+)\)", doc):
        if not link.startswith("https://"):
            assert (path.parent / link.split("#")[0]).is_file(), link
