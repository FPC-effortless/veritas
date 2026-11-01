"""Non-executing answer validation for public math training tasks."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def extract_gsm8k_answer(text):
    if not isinstance(text, str):
        return None
    match = re.search(
        r"(?:^|\n)####[ \t]*\$?[ \t]*(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)[ \t]*\Z", text.strip()
    )
    if match is None:
        return None
    value = match.group(1).replace(",", "")
    if len(value) > 64:
        return None
    try:
        number = Decimal(value)
        if not number.is_finite():
            return None
        if number == 0:
            return "0"
        rendered = format(number, "f")
        return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
    except InvalidOperation:
        return None


def verify_math(task, completion):
    if task.get("verifier") != "gsm8k-exact-v1":
        raise ValueError("unsupported math verifier")
    actual = extract_gsm8k_answer(completion)
    expected = task["expected_answer"]
    return float(actual is not None and Decimal(actual) == Decimal(expected))
