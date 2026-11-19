"""Where an email goes, decided per recipient (Codex re-audit, 19 Nov 2026).

Made-up demo addresses (example.com, demoshop.sg, .test and so on) are only ever caught by
the capture inbox (Mailpit, the shared demo inbox at mail.<domain>). Real addresses are sent
straight to the mail provider (Resend) and never copied into the capture inbox, so somebody
watching the demo inbox cannot read a real person's verification code or reset link.

  capture   EMAIL_HOST/EMAIL_PORT (Mailpit). Synthetic recipients everywhere; on a laptop or in
            CI (MAIL_CAPTURE_REAL=1, the default) also real-looking ones, since nothing leaves.
  provider  MAIL_PROVIDER_HOST (smtp.resend.com), for real recipients that pass the optional
            MAIL_REAL_RECIPIENTS allowlist (provider staging: the team's own inboxes only).
  suppress  Not sent at all: a real recipient on a server with no provider configured
            (MAIL_CAPTURE_REAL=0), or one outside the allowlist. Recorded on the outbox row.
"""
import re
from functools import cache

from django.conf import settings

CAPTURE, PROVIDER, SUPPRESS = "capture", "provider", "suppress"


@cache
def _pattern(expression: str) -> re.Pattern | None:
    return re.compile(expression) if expression else None


def is_synthetic(address: str) -> bool:
    pattern = _pattern(settings.MAIL_SYNTHETIC_RECIPIENTS)
    return bool(pattern and pattern.search(address.strip()))


def provider_configured() -> bool:
    return bool(settings.MAIL_PROVIDER["host"])


def route_for(address: str) -> str:
    if is_synthetic(address):
        return CAPTURE
    if provider_configured():
        allow = _pattern(settings.MAIL_REAL_RECIPIENTS)
        return PROVIDER if allow is None or allow.search(address.strip()) else SUPPRESS
    return CAPTURE if settings.MAIL_CAPTURE_REAL else SUPPRESS
