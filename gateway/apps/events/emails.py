"""Customer emails through the outbox (apps.events.models.OutboundEmail).

`queue` runs inside the caller's transaction; the worker's `send_due` sends after commit,
retries with backoff and records failures. Nothing here logs an address or a body.
"""
import logging
from datetime import timedelta

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.common import crypto
from apps.events.models import OutboundEmail

logger = logging.getLogger(__name__)

RETRY_DELAYS_SECONDS = (30, 120, 600, 1800, 3600)  # then failed
LEASE_SECONDS = 60


def queue(kind: str, payment, to: str, subject: str, body: str,
          discard_after=None) -> OutboundEmail:
    return OutboundEmail.objects.create(
        kind=kind, payment=payment, to=to, subject=subject,
        body_encrypted=crypto.encrypt(body), next_attempt_at=timezone.now(),
        discard_after=discard_after)


def _claim(limit: int) -> list[int]:
    now = timezone.now()
    with transaction.atomic():
        ids = list(OutboundEmail.objects.select_for_update(skip_locked=True)
                   .filter(status=OutboundEmail.Status.PENDING, next_attempt_at__lte=now)
                   .order_by("next_attempt_at").values_list("pk", flat=True)[:limit])
        OutboundEmail.objects.filter(pk__in=ids).update(
            next_attempt_at=now + timedelta(seconds=LEASE_SECONDS))
    return ids


def _send_one(pk: int) -> None:
    email = OutboundEmail.objects.get(pk=pk)
    now = timezone.now()
    if email.status != OutboundEmail.Status.PENDING:
        return
    if email.discard_after is not None and now >= email.discard_after:
        email.status, email.body_encrypted = OutboundEmail.Status.DISCARDED, ""
        email.save(update_fields=["status", "body_encrypted"])
        return
    email.attempt_count += 1
    try:
        send_mail(email.subject, crypto.decrypt(email.body_encrypted), None, [email.to],
                  fail_silently=False)
    except Exception as exc:  # noqa: BLE001 - SMTP, DNS, decrypt: all retried the same way
        email.last_error = type(exc).__name__[:64]
        if email.attempt_count > len(RETRY_DELAYS_SECONDS):
            email.status, email.body_encrypted = OutboundEmail.Status.FAILED, ""
            logger.error("Email %s (%s) failed after %d attempts: %s", email.public_id,
                         email.kind, email.attempt_count, email.last_error)
        else:
            email.next_attempt_at = now + timedelta(
                seconds=RETRY_DELAYS_SECONDS[email.attempt_count - 1])
            logger.warning("Email %s (%s) attempt %d failed: %s", email.public_id, email.kind,
                           email.attempt_count, email.last_error)
    else:
        email.status, email.sent_at, email.body_encrypted = (OutboundEmail.Status.SENT, now,
                                                             "")
        email.last_error = ""
    email.save(update_fields=["status", "attempt_count", "next_attempt_at", "last_error",
                              "sent_at", "body_encrypted"])


def send_due(limit: int = 50) -> int:
    ids = _claim(limit)
    for pk in ids:
        try:
            _send_one(pk)
        except Exception:
            logger.exception("Email %s could not be processed", pk)
    return len(ids)
