"""URS 4.4.2 Integrity: NFR-INT-01 at the URS's own numbers, on the demonstration store's side.

50 webhooks and status replies, each with a changed body, a wrong signature or a timestamp
older than 5 minutes, are all rejected; 50 valid messages are all accepted.
"""
import json
import time

import httpx
import pytest

from apps.shop import securepay
from apps.shop.models import Order
from apps.webhooks.models import ReceivedEvent
from conftest import SECRET, sign

pytestmark = pytest.mark.django_db

PROBLEMS = ("changed_body", "wrong_signature", "old_timestamp")


def _signed(raw: bytes, problem: str | None):
    """(body actually sent, signature header) for one message."""
    if problem == "wrong_signature":
        return raw, sign(raw, "whsec_not_the_secret")
    if problem == "old_timestamp":
        return raw, sign(raw, SECRET, int(time.time()) - 301)
    header = sign(raw, SECRET)
    if problem == "changed_body":
        return raw.replace(b'"authorised"', b'"captured"'), header
    return raw, header


def _event(payment_id, n):
    return {"id": f"evt_{n:024d}", "object": "event", "type": "payment.authorised",
            "payment_id": payment_id, "sequence": 2, "created_at": "2026-11-13T10:00:00Z",
            "data": {"object": {"id": payment_id, "status": "authorised"}}}


def test_nfr_int_01_tampered_webhooks_rejected_and_valid_ones_accepted(client, gateway):
    from apps.shop.tests import place_order

    place_order(client)
    order = Order.objects.get()
    payment_id = order.latest_attempt.payment_id
    rejected = accepted = 0
    for n in range(25):  # 25 tampered webhooks
        raw = json.dumps(_event(payment_id, n)).encode()
        body, header = _signed(raw, PROBLEMS[n % 3])
        r = client.post("/webhooks/securepay", body, content_type="application/json",
                        HTTP_SECUREPAY_SIGNATURE=header)
        rejected += r.status_code == 400
    assert rejected == 25
    assert not ReceivedEvent.objects.exists()
    order.refresh_from_db()
    assert order.paid_at is None
    for n in range(100, 125):  # 25 valid webhooks
        raw = json.dumps(_event(payment_id, n)).encode()
        r = client.post("/webhooks/securepay", raw, content_type="application/json",
                        HTTP_SECUREPAY_SIGNATURE=sign(raw, SECRET))
        accepted += r.status_code == 200
    assert accepted == 25
    assert ReceivedEvent.objects.count() == 25


def test_nfr_int_01_tampered_status_replies_rejected_and_valid_ones_accepted(gateway,
                                                                               monkeypatch):
    data = {"id": "pay_" + "P" * 24, "object": "payment", "status": "authorised",
            "amount": 4590, "currency": "SGD", "sequence": 3}
    raw = json.dumps(data).encode()
    plan = [PROBLEMS[n % 3] for n in range(25)] + [None] * 25
    replies = iter(plan)

    def answer(request):
        body, header = _signed(raw, next(replies))
        return httpx.Response(200, content=body, headers={
            "Content-Type": "application/json", "SecurePay-Signature": header})

    monkeypatch.setattr(securepay, "TRANSPORT", httpx.MockTransport(answer))
    rejected = accepted = 0
    for problem in plan:
        try:
            reply = securepay.get_payment(data["id"])
        except securepay.GatewayError:
            rejected += problem is not None
        else:
            accepted += problem is None and reply.data["status"] == "authorised"
    assert (rejected, accepted) == (25, 25)
