from __future__ import annotations

from email.message import Message
from pathlib import Path

import pytest

from investigation_world.foundry.public_investigation_sources import fetch_cdc_nors_csv

_HEADER = (
    b"Year,Month,State,Primary Mode,Etiology,Serotype or Genotype,Etiology Status,"
    b"Setting,Illnesses,Hospitalizations,Info On Hospitalizations,Deaths,Info On Deaths,"
    b"Food Vehicle,Food Contaminated Ingredient,IFSAC Category,Water Exposure,Water Type,"
    b"Animal Type\n"
)


class _FakeResponse:
    def __init__(self, payload: bytes, *, url: str, content_type: str = "text/csv") -> None:
        self._payload = payload
        self._url = url
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def geturl(self) -> str:
        return self._url

    def read(self, amount: int) -> bytes:
        return self._payload[:amount]


def test_fetch_cdc_nors_csv_writes_only_requested_staging_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _HEADER + b"2023,1,Texas,Food,Norovirus,,,,1,0,1,0,1,,,,,,\n"

    def fake_urlopen(request, timeout):
        assert timeout == 5.0
        return _FakeResponse(payload, url=request.full_url)

    monkeypatch.setattr(
        "investigation_world.foundry.public_investigation_sources.urllib.request.urlopen",
        fake_urlopen,
    )
    destination = tmp_path / "private" / "nors.csv"
    result = fetch_cdc_nors_csv(destination, timeout_seconds=5.0)

    assert destination.read_bytes() == payload
    assert result["byte_count"] == len(payload)
    assert len(str(result["sha256"])) == 64
    assert not (tmp_path / "public").exists()


def test_fetch_cdc_nors_csv_rejects_redirect_to_untrusted_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout):
        return _FakeResponse(_HEADER, url="https://example.com/nors.csv")

    monkeypatch.setattr(
        "investigation_world.foundry.public_investigation_sources.urllib.request.urlopen",
        fake_urlopen,
    )

    with pytest.raises(ValueError, match="host is not allowed"):
        fetch_cdc_nors_csv(tmp_path / "nors.csv")


def test_fetch_cdc_nors_csv_rejects_unexpected_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout):
        return _FakeResponse(b"year,state,result\n2023,Texas,hidden\n", url=request.full_url)

    monkeypatch.setattr(
        "investigation_world.foundry.public_investigation_sources.urllib.request.urlopen",
        fake_urlopen,
    )

    with pytest.raises(ValueError, match="expected streamlined schema"):
        fetch_cdc_nors_csv(tmp_path / "nors.csv")
    assert not (tmp_path / "nors.csv").exists()


def test_fetch_cdc_nors_csv_enforces_byte_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _HEADER + b"x" * 64

    def fake_urlopen(request, timeout):
        return _FakeResponse(payload, url=request.full_url)

    monkeypatch.setattr(
        "investigation_world.foundry.public_investigation_sources.urllib.request.urlopen",
        fake_urlopen,
    )

    with pytest.raises(ValueError, match="exceeds max_bytes"):
        fetch_cdc_nors_csv(tmp_path / "nors.csv", max_bytes=32)
