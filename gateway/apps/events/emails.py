"""Customer and account emails through the outbox (apps.events.models.OutboundEmail).

`queue` runs inside the caller's transaction; the worker's `send_due` sends after commit,
retries with backoff and records failures. Nothing here logs an address or a body.

Each email is claimed on its own just before it is sent, with a fresh claim token, and the
result is saved only while that token still holds (Codex re-audit, 19 Nov 2026: claiming 50
at once let later leases run out mid-batch). The outbox ID goes out as the Message-ID and the
provider's idempotency key, so a retry after a lost reply is delivered once. Retries stop when
the code or link inside has expired, and the route taken (capture inbox, provider, or not sent)
is recorded so an operator can tell a provider failure from a customer who did not act.
"""
import logging
import secrets
import smtplib
from datetime import timedelta
from email.utils import parseaddr

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from apps.common import crypto, mail_routing
from apps.events.models import OutboundEmail

logger = logging.getLogger(__name__)

RETRY_DELAYS_SECONDS = (30, 120, 600, 1800, 3600)  # then failed
LEASE_SECONDS = 60  # one email at a time; one SMTP send times out after EMAIL_TIMEOUT (5 s)

ROUTES = {mail_routing.CAPTURE: OutboundEmail.Route.CAPTURE,
          mail_routing.PROVIDER: OutboundEmail.Route.PROVIDER,
          mail_routing.SUPPRESS: OutboundEmail.Route.SUPPRESS}


def queue(kind: str, payment, to: str, subject: str, body: str,
          discard_after=None) -> OutboundEmail:
    return OutboundEmail.objects.create(
        kind=kind, payment=payment, to=to, subject=subject,
        body_encrypted=crypto.encrypt(body), next_attempt_at=timezone.now(),
        discard_after=discard_after)


def _claim_one() -> tuple[int, str] | None:
    now = timezone.now()
    with transaction.atomic():
        pk = (OutboundEmail.objects.select_for_update(skip_locked=True)
              .filter(status=OutboundEmail.Status.PENDING, next_attempt_at__lte=now)
              .order_by("next_attempt_at").values_list("pk", flat=True).first())
        if pk is None:
            return None
        token = secrets.token_hex(16)
        OutboundEmail.objects.filter(pk=pk).update(
            next_attempt_at=now + timedelta(seconds=LEASE_SECONDS), claim_token=token)
    return pk, token


def _headers(email: OutboundEmail) -> dict:
    domain = parseaddr(settings.DEFAULT_FROM_EMAIL)[1].rpartition("@")[2] or "localhost"
    return {"Message-ID": f"<{email.public_id}@{domain}>",
            # Resend drops a second message with the same key within 24 hours.
            "Resend-Idempotency-Key": email.public_id,
            "X-Entity-Ref-ID": email.public_id}


def _permanent(exc: Exception) -> bool:
    """The receiving server refused this message for good (5xx): retrying cannot help."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return all(500 <= code < 600 for code, _ in exc.recipients.values())
    if isinstance(exc, (smtplib.SMTPDataError, smtplib.SMTPSenderRefused)):
        return 500 <= exc.smtp_code < 600
    return False


def _finish(email: OutboundEmail, token: str, **fields) -> bool:
    updated = OutboundEmail.objects.filter(
        pk=email.pk, claim_token=token, status=OutboundEmail.Status.PENDING).update(**fields)
    if not updated:
        logger.warning("Email %s: claim lost before its result was saved", email.public_id)
    return bool(updated)


def _send_one(pk: int, token: str) -> None:
    email = OutboundEmail.objects.get(pk=pk)
    now = timezone.now()
    if email.status != OutboundEmail.Status.PENDING or email.claim_token != token:
        return
    if email.discard_after is not None and now >= email.discard_after:
        _finish(email, token, status=OutboundEmail.Status.DISCARDED, body_encrypted="")
        return
    route = ROUTES[mail_routing.route_for(email.to)]
    if route == OutboundEmail.Route.SUPPRESS:
        _finish(email, token, status=OutboundEmail.Status.SUPPRESSED, route=route,
                body_encrypted="")
        logger.info("Email %s (%s) not sent: no permitted route for a real recipient",
                    email.public_id, email.kind)
        return
    attempts = email.attempt_count + 1
    try:
        EmailMessage(email.subject, crypto.decrypt(email.body_encrypted), None, [email.to],
                     headers=_headers(email)).send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 - SMTP, DNS, decrypt: all retried the same way
        error = type(exc).__name__[:64]
        retry_at = (None if _permanent(exc) or attempts > len(RETRY_DELAYS_SECONDS)
                    else now + timedelta(seconds=RETRY_DELAYS_SECONDS[attempts - 1]))
        if retry_at is None:
            _finish(email, token, status=OutboundEmail.Status.FAILED, attempt_count=attempts,
                    last_error=error, route=route, body_encrypted="")
            logger.error("Email %s (%s) failed after %d attempt(s): %s", email.public_id,
                         email.kind, attempts, error)
        elif email.discard_after is not None and retry_at >= email.discard_after:
            # The code or link will have expired before the next try: stop here.
            _finish(email, token, status=OutboundEmail.Status.DISCARDED,
                    attempt_count=attempts, last_error=error, route=route, body_encrypted="")
            logger.warning("Email %s (%s) attempt %d failed (%s); expires before a retry",
                           email.public_id, email.kind, attempts, error)
        else:
            _finish(email, token, attempt_count=attempts, last_error=error, route=route,
                    next_attempt_at=retry_at)
            logger.warning("Email %s (%s) attempt %d failed: %s", email.public_id, email.kind,
                           attempts, error)
    else:
        _finish(email, token, status=OutboundEmail.Status.SENT, sent_at=now,
                attempt_count=attempts, last_error="", route=route, body_encrypted="")


def send_due(limit: int = 50) -> int:
    count = 0
    while count < limit:
        claim = _claim_one()
        if claim is None:
            break
        count += 1
        try:
            _send_one(*claim)
        except Exception:
            logger.exception("Email %s could not be processed", claim[0])
    return count
