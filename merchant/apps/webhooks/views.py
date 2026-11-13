"""POST /webhooks/securepay: the shop's webhook endpoint (API-CONTRACT.md section 7, FR-SIM-07).

1. Verify the signature over the raw bytes before parsing; reject a stale timestamp.
2. Ignore an event ID we already accepted (repeats and replays).
3. Ignore an event whose sequence is not higher than the one we stored.
4. Confirm with a signed GET /v1/payments/{id} and store that, never the webhook body alone.

A 2xx tells the gateway to stop retrying, so we answer 503 when the confirming GET fails
and let the gateway try again later.
"""
import json
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.shop import payments, securepay
from apps.shop.models import PaymentAttempt
from apps.webhooks.models import ReceivedEvent
from apps.webhooks.signing import verify

logger = logging.getLogger(__name__)

EVENT_ID = re.compile(r"^evt_[0-9A-Za-z]{24}$")
PAYMENT_ID = re.compile(r"^pay_[0-9A-Za-z]{24}$")
KEEP_DAYS = 7


def _reply(status: int, result: str) -> JsonResponse:
    return JsonResponse({"result": result}, status=status)


@csrf_exempt
@require_POST
def receive(request):
    if not securepay.configured():
        return _reply(503, "not_configured")
    raw = request.body
    header = request.headers.get("SecurePay-Signature", "")
    if not verify(raw, header, settings.SECUREPAY_SIGNING_SECRET,
                  settings.SECUREPAY_SIGNATURE_TOLERANCE_SECONDS):
        logger.warning("Rejected a webhook with a bad or stale signature")
        return _reply(400, "bad_signature")
    try:
        event = json.loads(raw)
        event_id, payment_id = event["id"], event["payment_id"]
        sequence, event_type = event["sequence"], event["type"]
    except (ValueError, KeyError, TypeError):
        return _reply(400, "invalid_event")
    if (not isinstance(event_id, str) or not EVENT_ID.match(event_id)
            or not isinstance(payment_id, str) or not PAYMENT_ID.match(payment_id)
            or not isinstance(sequence, int)):
        return _reply(400, "invalid_event")

    try:
        with transaction.atomic():
            if ReceivedEvent.objects.select_for_update().filter(event_id=event_id).exists():
                return _reply(200, "duplicate")
            outcome = _handle(payment_id, sequence)
            ReceivedEvent.objects.create(event_id=event_id, type=str(event_type)[:40],
                                         payment_id=payment_id, sequence=sequence,
                                         outcome=outcome)
    except IntegrityError:
        return _reply(200, "duplicate")  # the same event arrived twice at once
    except securepay.GatewayError as exc:
        logger.warning("Could not confirm %s with SecurePay (%s); asking for a retry",
                       event_id, exc)
        return _reply(503, "confirm_failed")
    _forget_old_events()
    return _reply(200, outcome)


def _handle(payment_id: str, sequence: int) -> str:
    attempt = PaymentAttempt.objects.filter(payment_id=payment_id).first()
    if attempt is None:
        logger.info("Webhook for a payment that is not ours: %s", payment_id)
        return "unknown_payment"
    if sequence <= attempt.sequence:
        return "stale"
    reply = securepay.get_payment(payment_id)  # raises GatewayError: the gateway retries
    if reply.status != 200:
        raise securepay.GatewayError(f"HTTP {reply.status}")
    payments.apply_payment(attempt, reply.data, attempt.order)
    return "applied"


def _forget_old_events() -> None:
    cutoff = timezone.now() - timedelta(days=KEEP_DAYS)
    ReceivedEvent.objects.filter(received_at__lt=cutoff).delete()
