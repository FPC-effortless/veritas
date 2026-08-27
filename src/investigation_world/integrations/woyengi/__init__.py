"""Standalone Woyengi WorldBundle v0.1 integration for Veritas."""

from investigation_world.integrations.woyengi.adapter import (
    WORLD_BUNDLE_CONTRACT,
    WORLD_BUNDLE_VERSION,
    WoyengiHiddenOracle,
    WorldBundleAdapterError,
    adapt_world_bundle,
)
from investigation_world.integrations.woyengi.pinned import adapt_pinned_world_bundle_fixture

__all__ = [
    "WORLD_BUNDLE_CONTRACT",
    "WORLD_BUNDLE_VERSION",
    "WoyengiHiddenOracle",
    "WorldBundleAdapterError",
    "adapt_pinned_world_bundle_fixture",
    "adapt_world_bundle",
]
