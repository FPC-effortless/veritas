from __future__ import annotations

import pytest

from investigation_world.investigation_data.acquisition import (
    AcquisitionError,
    _AllowlistedRedirectHandler,
)


def test_redirect_handler_rejects_off_allowlist_target_before_following():
    handler = _AllowlistedRedirectHandler(("ucdp.uu.se",))
    with pytest.raises(AcquisitionError, match="allowlisted"):
        handler.redirect_request(
            None,
            None,
            302,
            "Found",
            {},
            "https://evil.example/payload.zip",
        )
