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
from urllib.parse import urlsplit, urlunsplit

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
    excerpt: str = ""  # start of the response body, for the merchant's webhook log


class EndpointRefused(Exception):
    """The merchant's address may not be called (not approved, not HTTPS, private IP)."""


def check_endpoint(url: str) -> str | None:
    """Allow only an approved HTTPS address that resolves to public IPs (SSRF guard).

    Checked before every attempt, because DNS can change between attempts. Returns the
    public address that this attempt must connect to, so the name is resolved once and the
    call cannot be sent somewhere else by a second lookup (DNS rebinding, security self-test
    SEC-09). None for a host in WEBHOOK_ALLOWED_PRIVATE_HOSTS (local stack only), which is
    called by name as before.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise EndpointRefused("not_https")
    host = parts.hostname.lower()
    if host in settings.WEBHOOK_ALLOWED_PRIVATE_HOSTS:
        return None
    try:
        infos = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError):
        raise EndpointRefused("dns_error") from None
    addresses = []
    for info in infos:
        address = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
        if not address.is_global:
            raise EndpointRefused("blocked_address")
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise EndpointRefused("dns_error")
    # Prefer IPv4: the server's Docker networks may have no IPv6 route.
    addresses.sort(key=lambda a: a.version)
    return str(addresses[0])


def pinned_target(url: str, address: str | None) -> tuple[str, dict, dict]:
    """The URL, extra headers and httpx extensions for one call to `url` at `address`.

    The connection goes to the checked IP address, while the Host header and the TLS name
    (SNI, and the name the certificate is verified against) stay the merchant's host name,
    so a valid certificate for that name is still required.
    """
    if address is None:
        return url, {}, {}
    parts = urlsplit(url)
    host = parts.hostname
    literal = f"[{address}]" if ":" in address else address
    port = f":{parts.port}" if parts.port else ""
    target = urlunsplit(parts._replace(netloc=literal + port))
    host_header = (f"[{host}]" if ":" in host else host) + port
    return target, {"Host": host_header}, {"sni_hostname": host}


def excerpt(text: str) -> str:
    """The start of a reply body as one printable line, for the webhook log."""
    cleaned = "".join(ch if ch.isprintable() else " " for ch in text[:2000])
    cleaned = " ".join(cleaned.split())
    limit = WebhookAttempt.RESPONSE_EXCERPT_CHARS
    return cleaned if len(cleaned) <= limit else cleaned[:limit - 1] + "\u2026"


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
        address = check_endpoint(merchant.webhook_url)
    except EndpointRefused as exc:
        return Result(False, error=str(exc), duration_ms=elapsed())
    target, extra_headers, extensions = pinned_target(merchant.webhook_url, address)

    body = body_bytes(event)
    headers = {
        "Content-Type": "application/json",
        signing.HEADER: signing.sign(body, merchant.signing_secret),
        "SecurePay-Event-Id": event.public_id,
        "SecurePay-Event-Type": event.type,
        "SecurePay-Delivery-Attempt": str(attempt_number),
        "User-Agent": USER_AGENT,
        **extra_headers,
    }
    try:
        with httpx.Client(timeout=settings.GATEWAY_RULES["WEBHOOK_TIMEOUT_SECONDS"],
                          verify=settings.WEBHOOK_CA_BUNDLE or True, follow_redirects=False,
                          transport=TRANSPORT) as client:
            response = client.post(target, content=body, headers=headers,
                                   extensions=extensions)
    except httpx.TimeoutException:
        return Result(False, error="timeout", duration_ms=elapsed())
    except httpx.HTTPError as exc:
        return Result(False, error=type(exc).__name__[:64], duration_ms=elapsed())
    ok = 200 <= response.status_code < 300
    try:
        reply = excerpt(response.text)
    except (UnicodeError, LookupError):
        reply = ""
    return Result(ok, http_status=response.status_code, duration_ms=elapsed(), excerpt=reply)


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
    retries_done = event.attempt_count - event.schedule_base - 1
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
            error=result.error, succeeded=result.ok, response_excerpt=result.excerpt,
            manual=event.resend_count > 0 and attempt_number == event.schedule_base + 1)
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


class ResendRefused(Exception):
    """The event cannot be sent again now. `code` is the API error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def requeue(event_id: int, now: datetime | None = None) -> tuple[OutboxEvent, str]:
    """Put a delivered or undelivered event back in the queue for the worker (webhook log).

    The event keeps its ID, sequence and payload, so a merchant that already processed it
    drops the repeat by event ID (contract section 7, "Duplicates"); each attempt is signed
    afresh as usual. The retry schedule and the 72-hour window start again from the next
    attempt. A pending event is already queued and is refused, so the worker never sends the
    same event twice at once. Returns the event and its status before the resend.
    Call inside a transaction.
    """
    now = now or timezone.now()
    event = (OutboxEvent.objects.select_for_update(of=("self",))
             .select_related("merchant").get(pk=event_id))
    if event.status == OutboxEvent.Status.PENDING:
        raise ResendRefused("already_queued",
                            "This event is already waiting for its next attempt.")
    merchant = event.merchant
    if not merchant.webhook_url or not merchant.webhook_url_approved:
        raise ResendRefused("no_approved_endpoint",
                            "There is no approved webhook address to send it to.")
    if event.resend_count >= settings.GATEWAY_RULES["WEBHOOK_MAX_MANUAL_RESENDS"]:
        raise ResendRefused("resend_limit",
                            "This event has been resent the maximum number of times.")
    previous = event.status
    event.status = OutboxEvent.Status.PENDING
    event.next_attempt_at = now
    event.first_failed_at = None
    event.schedule_base = event.attempt_count
    event.resend_count += 1
    event.save(update_fields=["status", "next_attempt_at", "first_failed_at", "schedule_base",
                              "resend_count"])
    return event, previous
