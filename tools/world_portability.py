"""Compatibility launcher for the installed Veritas portable operational CLI."""

from investigation_world.world_portability import REQUIRED_SEMANTIC_FIELDS, main

__all__ = ["REQUIRED_SEMANTIC_FIELDS", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
