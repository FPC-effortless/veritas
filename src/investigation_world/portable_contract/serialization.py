from __future__ import annotations

from investigation_world.portable_contract.models import PortableOperationalContract


def serialize_portable_contract(contract: PortableOperationalContract) -> bytes:
    """Serialize the complete evaluator-bearing contract deterministically."""
    return contract.canonical_bytes()


def serialize_public_contract(contract: PortableOperationalContract) -> bytes:
    """Serialize only agent-visible semantics; evaluator-private data is unreachable."""
    return contract.public_bytes()
