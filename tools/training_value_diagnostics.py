"""Compatibility import for repository scripts; semantics live in TrainLab."""

from __future__ import annotations

import runpy
from pathlib import Path

# Repository tools use this checkout's helper even if an older TrainLab package
# is already imported. No arbitrary supplied path or installed-version shadowing.
_source = Path(__file__).resolve().parents[1] / "integrations/trainlab/src/trainlab"
_helpers = runpy.run_path(str(_source / "training_value_diagnostics.py"))
content_identity = _helpers["content_identity"]
interpretation = _helpers["interpretation"]
score_by_id = _helpers["score_by_id"]
unique_rows = _helpers["unique_rows"]

__all__ = ["content_identity", "interpretation", "score_by_id", "unique_rows"]
