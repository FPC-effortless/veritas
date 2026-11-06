import hashlib

import pytest
from pydantic import ValidationError

from investigation_world.sandbox import SandboxAssetDeclaration, SandboxCreateRequest


def test_read_only_asset_mount_cannot_overlap_writable_output_root() -> None:
    payload = b"private input fixture"
    asset = SandboxAssetDeclaration(
        asset_id="input",
        mount_path="shared/input.bin",
        sha256=hashlib.sha256(payload).hexdigest(),
        read_only=True,
    )

    with pytest.raises(ValidationError, match="read-only asset mount"):
        SandboxCreateRequest(assets=(asset,), writable_paths=("shared",))
