"""Simulator notifications to the gateway (SIMULATOR-CONTRACT.md section 9, proposal S3).

Sent only while a `notify` fault rule matches: `copies` identical `operation.recorded`
messages (same `id`, `delivery` 1..n), each signed like a reply, `delay_ms` after the
operation was recorded. Sent from a background thread so the operation's own reply is not
held up. The simulator never retries; the gateway's status query is the safety net.
"""
import json
import logging
import threading

import httpx
from django.conf import settings
from django.utils import timezone

from apps.common.http import SIGNATURE_HEADER, rfc3339, sign
from apps.common.ids import new_id

logger = logging.getLogger(__name__)

# Tests replace these: TRANSPORT with an httpx.MockTransport, run_later to run at once.
TRANSPORT: httpx.BaseTransport | None = None


def run_later(delay_seconds: float, fn) -> None:
    timer = threading.Timer(delay_seconds, fn)
    timer.daemon = True
    timer.start()


def build(record: dict, notification_id: str, delivery: int) -> bytes:
    body = {"id": notification_id, "type": "operation.recorded",
            "created_at": rfc3339(timezone.now()), "delivery": delivery, "data": record}
    return json.dumps(body, separators=(",", ":")).encode()


def send(record: dict, copies: int) -> None:
    notification_id = new_id("ntf")
    with httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0), transport=TRANSPORT,
                      verify=settings.SIM_GATEWAY_CA_BUNDLE or True,
                      follow_redirects=False) as client:
        for delivery in range(1, copies + 1):
            body = build(record, notification_id, delivery)
            try:
                response = client.post(
                    settings.SIM_GATEWAY_NOTIFY_URL, content=body,
                    headers={"Content-Type": "application/json",
                             SIGNATURE_HEADER: sign(body, settings.SIMULATOR_SIGNING_SECRET),
                             "User-Agent": "SecurePay-Simulator/1.0"})
                logger.info("Notification %s copy %d for %s: HTTP %d", notification_id,
                            delivery, record["operation_id"], response.status_code)
            except httpx.HTTPError as exc:
                logger.warning("Notification %s copy %d for %s not delivered: %s",
                               notification_id, delivery, record["operation_id"],
                               type(exc).__name__)


def schedule(record: dict, rules) -> None:
    """One send per matching notify rule. `no_record` is never notified (section 9)."""
    if record.get("status") == "no_record":
        return
    for rule in rules:
        run_later((rule.delay_ms or 0) / 1000, lambda r=rule: send(record, r.copies))
