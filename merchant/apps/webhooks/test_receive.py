"""The shop's webhook endpoint (API-CONTRACT.md section 7) and capture / cancel (S1)."""
import json
import time

import pytest
from django.core.management import call_command

from apps.shop import payments
from apps.shop.models import Order, PaymentAttempt
from apps.webhooks.models import ReceivedEvent
from conftest import SECRET, sign

pytestmark = pytest.mark.django_db


@pytest.fixture
def ordered(client, gateway):
    from apps.shop.tests import place_order

    place_order(client)
    order = Order.objects.get()
    return order, order.latest_attempt


def event(attempt, sequence=2, event_id="evt_" + "E" * 24, type_="payment.authorised"):
    return {"id": event_id, "object": "event", "type": type_, "payment_id": attempt.payment_id,
            "sequence": sequence, "created_at": "2026-11-13T10:00:00Z",
            "data": {"object": {"id": attempt.payment_id, "status": "authorised"}}}


def deliver(client, data, secret=SECRET, ts=None):
    raw = json.dumps(data).encode()
    return client.post("/webhooks/securepay", raw, content_type="application/json",
                       HTTP_SECUREPAY_SIGNATURE=sign(raw, secret, ts))


def test_verified_event_is_confirmed_by_get_and_marks_paid(client, gateway, ordered):
    order, attempt = ordered
    r = deliver(client, event(attempt))
    assert r.status_code == 200 and r.json()["result"] == "applied"
    order.refresh_from_db()
    attempt.refresh_from_db()
    assert order.paid_at and attempt.status == "authorised"
    assert gateway.calls[-1][:2] == ("GET", f"/v1/payments/{attempt.payment_id}")


def test_duplicate_event_is_ignored(client, gateway, ordered):
    _, attempt = ordered
    deliver(client, event(attempt))
    calls = len(gateway.calls)
    r = deliver(client, event(attempt))
    assert r.status_code == 200 and r.json()["result"] == "duplicate"
    assert len(gateway.calls) == calls
    assert ReceivedEvent.objects.count() == 1


def test_older_sequence_is_ignored(client, gateway, ordered):
    _, attempt = ordered
    PaymentAttempt.objects.filter(pk=attempt.pk).update(sequence=5)
    r = deliver(client, event(attempt, sequence=4))
    assert r.json()["result"] == "stale"
    assert all(method == "POST" for method, *_ in gateway.calls)


@pytest.mark.parametrize("problem", ["wrong_secret", "stale", "unsigned"])
def test_bad_signature_is_rejected_and_nothing_changes(client, gateway, ordered, problem):
    order, attempt = ordered
    data = event(attempt)
    if problem == "unsigned":
        r = client.post("/webhooks/securepay", json.dumps(data),
                        content_type="application/json")
    else:
        r = deliver(client, data, secret="whsec_wrong" if problem == "wrong_secret" else SECRET,
                    ts=int(time.time()) - 301 if problem == "stale" else None)
    assert r.status_code == 400
    order.refresh_from_db()
    assert order.paid_at is None and not ReceivedEvent.objects.exists()


def test_unknown_payment_is_acknowledged(client, gateway, ordered):
    _, attempt = ordered
    data = event(attempt)
    data["payment_id"] = "pay_" + "Z" * 24
    assert deliver(client, data).json()["result"] == "unknown_payment"


def test_failed_confirmation_asks_the_gateway_to_retry(client, gateway, ordered):
    _order, attempt = ordered
    gateway.mode = "down"
    r = deliver(client, event(attempt))
    assert r.status_code == 503
    assert not ReceivedEvent.objects.exists()  # the retry is processed in full
    gateway.mode = "normal"
    assert deliver(client, event(attempt)).json()["result"] == "applied"


def test_malformed_event_is_400(client, gateway, ordered):
    raw = b'{"id": "nope"}'
    r = client.post("/webhooks/securepay", raw, content_type="application/json",
                    HTTP_SECUREPAY_SIGNATURE=sign(raw, SECRET))
    assert r.status_code == 400


# --- capture and cancel from the back office ----------------------------------------------

def test_capture_command_charges_and_shows_paid(client, gateway, ordered):
    order, attempt = ordered
    deliver(client, event(attempt))
    call_command("settle_order", "capture", order.reference)
    attempt.refresh_from_db()
    assert (attempt.status, attempt.captured_amount) == ("captured", order.total_cents)
    method, path, body, headers = gateway.calls[-1]
    assert (method, path, body) == ("POST", f"/v1/payments/{attempt.payment_id}/capture", {})
    assert headers["idempotency-key"] == str(attempt.capture_key)
    assert b"Paid" in client.get(f"/orders/{order.number}").content


def test_partial_capture_and_retry_reuse_the_key(client, gateway, ordered):
    _order, attempt = ordered
    deliver(client, event(attempt))
    payments.capture(attempt, 1000)
    payments.capture(attempt, 1000)
    keys = {h["idempotency-key"] for m, p, b, h in gateway.calls if p.endswith("/capture")}
    assert keys == {str(attempt.capture_key)}
    attempt.refresh_from_db()
    assert attempt.captured_amount == 1000


def test_cancel_shows_the_order_as_cancelled(client, gateway, ordered):
    order, attempt = ordered
    deliver(client, event(attempt))
    gateway.next_status = "cancelled"
    assert payments.cancel(attempt) == "cancelled"
    page = client.get(f"/orders/{order.number}").content
    assert b"hold on your card was released" in page
    assert b"with SecurePay" not in page  # no new payment offered for a cancelled order


def test_refused_capture_is_reported(client, gateway, ordered):
    _order, attempt = ordered
    gateway.settle_reply = (409, {"error": {"code": "authorisation_expired"}})
    with pytest.raises(payments.SettleError, match="authorisation_expired"):
        payments.capture(attempt)


def test_pending_capture_waits_for_the_webhook(client, gateway, ordered):
    _order, attempt = ordered
    deliver(client, event(attempt))
    attempt.refresh_from_db()
    pending = {**gateway.payments[attempt.payment_id][1], "status": "authorised",
               "sequence": attempt.sequence, "checkout_url": None,
               "pending_operation": {"type": "capture", "status": "unresolved"}}
    gateway.settle_reply = (202, pending)
    assert payments.capture(attempt) == "pending"


def test_refund_command_sends_a_new_key_each_time(client, gateway, ordered, capsys):
    order, attempt = ordered
    deliver(client, event(attempt))
    call_command("settle_order", "refund", order.reference, "--amount", "500",
                 "--reason", "One item returned")
    call_command("settle_order", "refund", order.reference, "--amount", "500")
    sent = [(b, h["idempotency-key"]) for m, p, b, h in gateway.calls if p.endswith("/refunds")]
    assert [b for b, _ in sent] == [{"amount": 500, "reason": "One item returned"},
                                    {"amount": 500}]
    assert sent[0][1] != sent[1][1]
    assert "RF-AAAA-0001 500 completed" in capsys.readouterr().out
