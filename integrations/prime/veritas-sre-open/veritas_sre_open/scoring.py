from __future__ import annotations

import json


_ALLOWED = {"regression", "infrastructure", "capacity", "transient"}


def parse_prediction(raw: object) -> str | None:
    """Parse exactly one allowed causal class from a model reply."""

    text = str(raw or "").strip()
    payload = None
    try:
        candidate = json.loads(text)
        if isinstance(candidate, dict):
            payload = candidate
    except json.JSONDecodeError:
        left = text.find("{")
        right = text.rfind("}")
        if left >= 0 and right > left:
            try:
                candidate = json.loads(text[left : right + 1])
                if isinstance(candidate, dict):
                    payload = candidate
            except json.JSONDecodeError:
                pass

    value = str(payload.get("causal_class", "")) if payload else text
    normalized = value.strip().casefold().strip("\"'` .")
    return normalized if normalized in _ALLOWED else None


def score_prediction(raw: object, expected_causal_class: str) -> float:
    """Return binary reward for exact causal-class agreement."""

    return float(parse_prediction(raw) == expected_causal_class)
