from __future__ import annotations

import pytest

from investigation_world.observatory.providers import _validated_http_url


def test_provider_url_accepts_http_and_https_network_endpoints():
    assert _validated_http_url("https://api.example.com/v1/responses") == (
        "https://api.example.com/v1/responses"
    )
    assert _validated_http_url("http://127.0.0.1:8000/v1/chat/completions") == (
        "http://127.0.0.1:8000/v1/chat/completions"
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/provider.json",
        "ftp://example.com/model",
        "data:text/plain,hello",
        "/relative/path",
        "https:///missing-host",
        "https://user:secret@example.com/v1",
    ],
)
def test_provider_url_rejects_non_network_or_embedded_credential_urls(url: str):
    with pytest.raises(ValueError):
        _validated_http_url(url)
