"""Delivery reports from the mail provider (Resend), after it has accepted an email.

`POST /webhooks/resend`: Resend signs each report the Svix way (`svix-id`,
`svix-timestamp`, `svix-signature` headers; RUNBOOK.md 13b). A report moves the outbox row
on from "accepted by the provider" (`sent`) to what really happened:

    email.delivered  -> delivered  (the recipient's mail server took it)
    email.bounced    -> bounced    (refused for good, e.g. no such mailbox)
    email.failed     -> failed     (the provider could not send it after accepting it)

Other report types (opened, clicked, delayed, complained...) are acknowledged and ignored:
open and click tracking are off, and a delay is followed by delivered or bounced anyway.

The report names our email by its RFC Message-ID, `<eml_...@domain>` (emails._headers), so
nothing has to be stored about the provider's own ID. A report we cannot match, or one that
would move a row backwards (delivered after bounced), still gets 200 so the provider stops
retrying, and changes nothing. Each change is one conditional UPDATE, so a repeat, a report
racing the worker, or two copies at once leave the same result. Nothing here logs an address,
a subject or the provider's bounce message (it can quote the address); only the bounce
type, such as `Permanent/Suppressed`, is kept.

Without RESEND_WEBHOOK_SECRET the endpoint answers 404: it is off until it is configured.
"""
import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import time
from datetime import timedelta
from typing import ClassVar

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.errors import invalid
from apps.events.models import OutboundEmail
from apps.reconciliation.views import RawParser

logger = logging.getLogger(__name__)

TOLERANCE_SECONDS = 300  # Svix's own default: older or future-dated reports are refused
MESSAGE_ID = re.compile(r"<?(eml_[A-Za-z0-9]{8,40})@")
# Fallback match when a report has no usable Message-ID: same recipient and subject, sent
# through the provider within this long of the provider's own creation time, and only if
# exactly one email fits.
FALLBACK_WINDOW = timedelta(minutes=15)

S = OutboundEmail.Status
# Report type -> (new status, statuses it may replace). Never backwards: a bounce outranks a
# delivery, and nothing replaces a bounce. `pending` is included because the provider can
# accept an email whose reply we lost; the worker then finds its claim gone and stops.
TRANSITIONS = {
    "email.delivered": (S.DELIVERED, (S.PENDING, S.SENT)),
    "email.bounced": (S.BOUNCED, (S.PENDING, S.SENT, S.DELIVERED)),
    "email.failed": (S.FAILED, (S.PENDING, S.SENT)),
}


def verify(body: bytes, msg_id: str, timestamp: str, signature: str, secret: str,
           now: int | None = None, tolerance: int = TOLERANCE_SECONDS) -> bool:
    """Svix signature check: HMAC-SHA256 over `id.timestamp.body` with the base64 key after
    `whsec_`; the header holds one or more space-separated `v1,<base64>` signatures (more than
    one while a secret is being rotated)."""
    if not (msg_id and timestamp and signature and secret):
        return False
    try:
        ts = int(timestamp)
        key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
    except (ValueError, binascii.Error):
        return False
    now = int(time.time()) if now is None else now
    if abs(now - ts) > tolerance:
        return False
    mac = hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode()
    for item in signature.split():
        version, _, given = item.partition(",")
        if version == "v1" and hmac.compare_digest(expected, given):
            return True
    return False


def sign(body: bytes, msg_id: str, timestamp: int, secret: str) -> str:
    """The header Resend would send (tests and the RUNBOOK's curl check)."""
    key = base64.b64decode(secret.removeprefix("whsec_"))
    mac = hmac.new(key, f"{msg_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(mac).decode()


def _find(data: dict) -> OutboundEmail | None:
    match = MESSAGE_ID.search(str(data.get("message_id") or ""))
    if match:
        return OutboundEmail.objects.filter(public_id=match.group(1)).first()
    recipients = data.get("to") or []
    created = parse_datetime(str(data.get("created_at") or ""))
    if len(recipients) != 1 or created is None or not data.get("subject"):
        return None
    candidates = list(OutboundEmail.objects.filter(
        route=OutboundEmail.Route.PROVIDER, to__iexact=recipients[0], subject=data["subject"],
        sent_at__gte=created - FALLBACK_WINDOW, sent_at__lte=created + FALLBACK_WINDOW,
    )[:2])
    return candidates[0] if len(candidates) == 1 else None


def apply(report: dict) -> str:
    """Apply one verified report. Returns what happened (for the reply and the tests):
    `applied`, `ignored` (a type we do not track), `unmatched` or `unchanged`."""
    kind = report.get("type")
    if kind not in TRANSITIONS:
        return "ignored"
    data = report.get("data") or {}
    email = _find(data)
    if email is None:
        return "unmatched"
    new_status, allowed = TRANSITIONS[kind]
    fields = {"status": new_status, "delivery_reported_at": timezone.now(),
              "body_encrypted": "", "claim_token": ""}  # nosec B105 - clears a lease, no password
    if new_status == S.BOUNCED:
        bounce = data.get("bounce") or {}
        fields["bounce_type"] = "/".join(
            str(bounce.get(k))[:30] for k in ("type", "subType") if bounce.get(k))[:64]
    if new_status == S.FAILED:
        fields["last_error"] = "ProviderFailed"
    updated = OutboundEmail.objects.filter(pk=email.pk, status__in=allowed).update(**fields)
    return "applied" if updated else "unchanged"


class ResendWebhookView(APIView):
    authentication_classes: ClassVar = []
    permission_classes: ClassVar = [AllowAny]
    parser_classes: ClassVar = [RawParser]
    throttle_classes: ClassVar = []  # signed; an unsigned flood costs one HMAC each
    schema = None

    def post(self, request):
        secret = settings.RESEND_WEBHOOK_SECRET
        if not secret:
            return Response({"detail": "Not found."}, status=404)
        raw = request.body
        h = request.headers
        if not verify(raw, h.get("svix-id", ""), h.get("svix-timestamp", ""),
                      h.get("svix-signature", ""), secret):
            raise invalid("signature_invalid", "Missing or invalid svix-signature.")
        try:
            report = json.loads(raw)
            if not isinstance(report, dict):
                raise TypeError
        except (ValueError, TypeError):
            raise invalid("invalid_json", "Not a mail provider report.") from None
        result = apply(report)
        logger.info("Mail report %s %s: %s", h.get("svix-id", "")[:40],
                    str(report.get("type"))[:40], result)
        return Response({"received": True, "result": result})
