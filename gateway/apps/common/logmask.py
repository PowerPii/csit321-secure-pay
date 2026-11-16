"""Masking of personal data in logs and audit details (NFR-PRI-01).

    mask_text("mail jane@example.com")  -> "mail j•••@example.com"
    mask_value({...})                    -> the same structure with every string masked
    MaskPersonalData                     -> logging filter, installed on every handler

Email addresses keep their first letter and domain, enough to recognise but not to contact.
Phone numbers (8 or more digits, optionally with +, spaces or dashes) keep their last 2
digits. Card-number-length digit runs are masked too, as a last line of defence: card data
never reaches a log on purpose (FR-TXN-09). Public IDs (pay_..., SP-...) and timestamps are
not touched.
"""
import logging
import re

EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
# A phone-like run: optional +, then 8 to 19 digits that may be split by single spaces or
# dashes. Not preceded or followed by a letter, digit, underscore or colon, so IDs, times
# (12:30:45) and dates (2026-11-16) are left alone.
PHONE = re.compile(r"(?<![\w:+-])\+?\d(?:[ -]?\d){7,18}(?![\w:])")


def _phone(match: re.Match) -> str:
    text = match.group(0)
    digits = re.sub(r"\D", "", text)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):  # a date
        return text
    return "•" * (len(digits) - 2) + digits[-2:]


def mask_text(text: str) -> str:
    if not text:
        return text
    text = EMAIL.sub(lambda m: f"{m.group(1)}•••@{m.group(2)}", text)
    return PHONE.sub(_phone, text)


def mask_value(value):
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {k: mask_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [mask_value(v) for v in value]
    return value


class MaskPersonalData(logging.Filter):
    """Rewrite each record's message with emails and phone numbers masked."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):  # a broken format string: leave it to logging
            return True
        masked = mask_text(message)
        if masked != message:
            record.msg, record.args = masked, None
        return True
