"""Webhook delivery from the outbox (API-CONTRACT.md section 7, FR-TXN-06/07, FR-MER-10).

The worker claims due events with SELECT ... FOR UPDATE SKIP LOCKED and pushes their
next_attempt_at forward by a lease before it commits, so several workers never send the
same event at once, and an event held by a worker that died becomes due again after the
lease. The HTTP call happens outside any transaction. Each attempt is recorded; delivery
results never change a payment (FR-TXN-07).
"""
import ipaddress
import json
import logging
import secrets
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.events import signing
from apps.events.models import OutboxEvent, WebhookAttempt

logger = logging.getLogger(__name__)

USER_AGENT = "SecurePay-Webhooks/1.0"
# Tests replace this with an httpx.MockTransport; None means real network calls.
TRANSPORT: httpx.BaseTransport | None = None
_random = secrets.SystemRandom()


@dataclass(frozen=True)
class Result:
    ok: bool
    http_status: int | None = None
    error: str = ""  # error class when there is no 2xx: timeout, blocked_address, ...
    duration_ms: int = 0


class EndpointRefused(Exception):
    """The merchant's address may not be called (not approved, not HTTPS, private IP)."""


def check_endpoint(url: str) -> None:
    """Allow only an approved HTTPS address that resolves to public IPs (SSRF guard).

    Checked before every attempt, because DNS can change between attempts.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise EndpointRefused("not_https")
    host = parts.hostname.lower()
    if host in settings.WEBHOOK_ALLOWED_PRIVATE_HOSTS:
        return
    try:
        infos = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise EndpointRefused("dns_error") from None
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise EndpointRefused("dns_error")
    for address in addresses:
        if not ipaddress.ip_address(address.split("%", 1)[0]).is_global:
            raise EndpointRefused("blocked_address")


def body_bytes(event: OutboxEvent) -> bytes:
    return json.dumps(event.payload, separators=(",", ":"), ensure_ascii=False).encode()


def send(event: OutboxEvent, attempt_number: int) -> Result:
    """One POST to the merchant. Signed fresh, so the timestamp is the attempt's own."""
    merchant = event.merchant
    started = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    if not merchant.webhook_url or not merchant.webhook_url_approved:
        return Result(False, error="no_approved_endpoint")
    try:
        check_endpoint(merchant.webhook_url)
    except EndpointRefused as exc:
        return Result(False, error=str(exc), duration_ms=elapsed())

    body = body_bytes(event)
    headers = {
        "Content-Type": "application/json",
        signing.HEADER: signing.sign(body, merchant.signing_secret),
        "SecurePay-Event-Id": event.public_id,
        "SecurePay-Event-Type": event.type,
        "SecurePay-Delivery-Attempt": str(attempt_number),
        "User-Agent": USER_AGENT,
    }
    try:
        with httpx.Client(timeout=settings.GATEWAY_RULES["WEBHOOK_TIMEOUT_SECONDS"],
                          verify=settings.WEBHOOK_CA_BUNDLE or True, follow_redirects=False,
                          transport=TRANSPORT) as client:
            response = client.post(merchant.webhook_url, content=body, headers=headers)
    except httpx.TimeoutException:
        return Result(False, error="timeout", duration_ms=elapsed())
    except httpx.HTTPError as exc:
        return Result(False, error=type(exc).__name__[:64], duration_ms=elapsed())
    ok = 200 <= response.status_code < 300
    return Result(ok, http_status=response.status_code, duration_ms=elapsed())


def next_attempt_after_failure(event: OutboxEvent, now: datetime) -> datetime | None:
    """When to try again, or None when the 72-hour window is over (contract section 7).

    The window starts at the first failed attempt. Retries follow
    WEBHOOK_RETRY_DELAYS_SECONDS with +/-10% jitter, never past the window end; a final
    attempt is made at the window end; a failure then is final.
    """
    rules = settings.GATEWAY_RULES
    window_end = event.first_failed_at + timedelta(hours=rules["WEBHOOK_RETRY_WINDOW_HOURS"])
    if now >= window_end:
        return None
    delays = rules["WEBHOOK_RETRY_DELAYS_SECONDS"]
    retries_done = event.attempt_count - 1
    if retries_done >= len(delays):
        return window_end
    delay = delays[retries_done] * _random.uniform(0.9, 1.1)
    return min(now + timedelta(seconds=delay), window_end)


def claim_due(limit: int, now: datetime | None = None) -> list[int]:
    """Lease up to `limit` due events to this worker and return their IDs."""
    now = now or timezone.now()
    lease = now + timedelta(seconds=settings.WEBHOOK_LEASE_SECONDS)
    with transaction.atomic():
        ids = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(status=OutboxEvent.Status.PENDING, next_attempt_at__lte=now)
            .order_by("next_attempt_at", "id")
            .values_list("id", flat=True)[:limit]
        )
        OutboxEvent.objects.filter(id__in=ids).update(next_attempt_at=lease)
    return ids


def deliver(event_id: int) -> OutboxEvent:
    """Make the next attempt for one claimed event and record the outcome."""
    event = OutboxEvent.objects.select_related("merchant").get(pk=event_id)
    if event.status != OutboxEvent.Status.PENDING:
        return event
    attempt_number = event.attempt_count + 1
    started_at = timezone.now()
    result = send(event, attempt_number)
    now = timezone.now()
    with transaction.atomic():
        event = OutboxEvent.objects.select_for_update().get(pk=event_id)
        if event.status != OutboxEvent.Status.PENDING or event.attempt_count >= attempt_number:
            return event  # another worker finished it after our lease ran out
        WebhookAttempt.objects.create(
            event=event, attempt_number=attempt_number, started_at=started_at,
            duration_ms=result.duration_ms, http_status=result.http_status,
            error=result.error, succeeded=result.ok)
        event.attempt_count = attempt_number
        if result.ok:
            event.status = OutboxEvent.Status.DELIVERED
            event.delivered_at = now
            event.next_attempt_at = None
        else:
            if event.first_failed_at is None:
                event.first_failed_at = now
            event.next_attempt_at = next_attempt_after_failure(event, now)
            if event.next_attempt_at is None:
                event.status = OutboxEvent.Status.UNDELIVERED
                logger.warning("Webhook %s undelivered after %d attempts", event.public_id,
                               attempt_number)
        event.save(update_fields=["status", "attempt_count", "first_failed_at",
                                  "next_attempt_at", "delivered_at"])
    return event


def deliver_due(limit: int | None = None) -> int:
    """One worker pass: claim due events and attempt each once. Returns how many."""
    ids = claim_due(limit or settings.WORKER_BATCH_SIZE)
    for event_id in ids:
        try:
            deliver(event_id)
        except Exception:
            # Leave it leased; it becomes due again when the lease runs out.
            logger.exception("Webhook delivery crashed for event %s", event_id)
    return len(ids)
