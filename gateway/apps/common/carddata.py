"""Refuse request bodies that contain a card number (FR-TXN-09, API-CONTRACT.md section 1).

A string counts as a card number if, ignoring spaces and dashes, it is 13 to 19 digits
that pass the Luhn check. Such a body is rejected before it is logged, fingerprinted or
stored anywhere.
"""
import re

_SEPARATORS = re.compile(r"[ \-]")
_DIGIT_RUN = re.compile(r"\d[\d \-]{11,}\d")


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def looks_like_card_number(text: str) -> bool:
    for run in _DIGIT_RUN.findall(text):
        digits = _SEPARATORS.sub("", run)
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            return True
    return False


def contains_card_number(value) -> bool:
    """Search every string (keys too) in a parsed JSON value."""
    if isinstance(value, str):
        return looks_like_card_number(value)
    if isinstance(value, dict):
        return any(contains_card_number(k) or contains_card_number(v) for k, v in value.items())
    if isinstance(value, list):
        return any(contains_card_number(v) for v in value)
    return False
