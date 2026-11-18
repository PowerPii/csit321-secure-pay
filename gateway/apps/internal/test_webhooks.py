"""Webhook delivery log and Resend (extends FR-TXN-07; FR-MER-08/09, FR-ADM-10)."""
import httpx
import pytest
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.events import delivery
from apps.events.models import EventType, OutboxEvent, WebhookAttempt
from apps.events.outbox import record_payment_event
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db

HOOK = "https://shop.example/webhooks/securepay"


class Receiver:
    def __init__(self):
        self.status = 200
        self.text = "ok"
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return httpx.Response(self.status, text=self.text)


@pytest.fixture
def receiver(monkeypatch, settings):
    r = Receiver()
    monkeypatch.setattr(delivery, "TRANSPORT", httpx.MockTransport(r))
    settings.WEBHOOK_ALLOWED_PRIVATE_HOSTS = frozenset({"shop.example"})
    return r


@pytest.fixture
def hooked(make_merchant):
    return make_merchant(webhook_url=HOOK, webhook_url_approved=True)


@pytest.fixture
def other(make_merchant):
    return make_merchant("Other Shop", webhook_url=HOOK, webhook_url_approved=True)


def make_event(client) -> OutboxEvent:
    payment_id = client.create_payment().json()["id"]
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(public_id=payment_id)
        payment.status = "expired"
        return record_payment_event(payment, EventType.PAYMENT_EXPIRED)


def give_up(event):
    """Run the event to "undelivered" quickly: the window is already over."""
    delivery.deliver_due()
    OutboxEvent.objects.filter(pk=event.pk).update(
        first_failed_at=timezone.now() - timezone.timedelta(hours=73),
        next_attempt_at=timezone.now())
    delivery.deliver_due()
    event.refresh_from_db()
    assert event.status == "undelivered"
    return event


def test_operator_sees_own_events_with_attempts(staff_client, hooked, other, receiver):
    receiver.status, receiver.text = 500, "Internal error\n\x00 order not found"
    mine = make_event(hooked)
    theirs = make_event(other)
    delivery.deliver_due()
    operator = staff_client("merchant_operator", merchant=hooked.merchant)
    data = operator.get("/internal/webhooks").json()
    assert [row["id"] for row in data["data"]] == [mine.public_id]
    row = data["data"][0]
    assert row["status"] == "pending" and row["attempts"] == 1
    assert row["last_http_status"] == 500 and row["next_attempt_at"]
    assert data["counts"]["pending"] == 1
    assert data["endpoint"] == {"url": HOOK, "approved": True}

    detail = operator.get(f"/internal/webhooks/{mine.public_id}").json()
    assert detail["payload"] == mine.payload
    (attempt,) = detail["attempt_log"]
    assert attempt["http_status"] == 500 and not attempt["succeeded"]
    assert attempt["response_excerpt"] == "Internal error order not found"
    assert attempt["duration_ms"] >= 0
    assert detail["can_resend"] is False  # still being retried

    # FR-MER-08/09: another merchant's event is "not found", and the attempt is logged.
    assert operator.get(f"/internal/webhooks/{theirs.public_id}").status_code == 404
    assert operator.post(f"/internal/webhooks/{theirs.public_id}/resend",
                         content_type="application/json").status_code == 404
    assert AuditEvent.objects.filter(action="security.cross_merchant_access",
                                     target_id=theirs.public_id).count() == 2


def test_administrator_sees_every_merchant_and_can_filter(staff_client, hooked, other,
                                                          receiver):
    make_event(hooked)
    theirs = make_event(other)
    admin = staff_client("administrator")
    assert admin.get("/internal/webhooks").json()["count"] == 2
    data = admin.get(f"/internal/webhooks?merchant={other.merchant.public_id}").json()
    assert [r["id"] for r in data["data"]] == [theirs.public_id]
    assert data["endpoint"] is None
    by_payment = admin.get(f"/internal/webhooks?q={theirs.payment.public_id}").json()
    assert [r["id"] for r in by_payment["data"]] == [theirs.public_id]
    assert admin.get(f"/internal/webhooks?q={theirs.public_id}").json()["count"] == 1
    assert admin.get("/internal/webhooks?status=delivered").json()["count"] == 0
    assert admin.get("/internal/webhooks?status=nope").status_code == 400
    assert admin.get("/internal/webhooks?type=nope").status_code == 400


def test_fraud_analyst_is_refused(staff_client, hooked):
    analyst = staff_client("fraud_analyst")
    assert analyst.get("/internal/webhooks").status_code == 403
    event = make_event(hooked)
    assert analyst.post(f"/internal/webhooks/{event.public_id}/resend",
                        content_type="application/json").status_code == 403


def test_resend_undelivered_event_keeps_id_and_payload_and_is_audited(
        staff_client, hooked, receiver):
    receiver.status = 500
    event = give_up(make_event(hooked))
    assert event.attempt_count == 2
    operator = staff_client("merchant_operator", merchant=hooked.merchant)
    assert operator.get(f"/internal/webhooks/{event.public_id}").json()["can_resend"]

    r = operator.post(f"/internal/webhooks/{event.public_id}/resend",
                      content_type="application/json")
    assert r.status_code == 202, r.content
    assert r.json()["status"] == "pending" and r.json()["resends"] == 1
    entry = AuditEvent.objects.get(action="webhook.resent")
    assert (entry.actor_id, entry.target_id, entry.merchant_id) == (
        operator.account.public_id, event.public_id, hooked.merchant.public_id)
    assert entry.correlation_id == event.payment.public_id
    assert entry.details["previous_status"] == "undelivered"

    receiver.status = 200
    assert delivery.deliver_due() == 1
    event.refresh_from_db()
    assert event.status == "delivered" and event.attempt_count == 3
    first, last = receiver.requests[0], receiver.requests[-1]
    assert last.headers["SecurePay-Event-Id"] == first.headers["SecurePay-Event-Id"]
    assert last.content == first.content
    assert last.headers["SecurePay-Delivery-Attempt"] == "3"
    third = WebhookAttempt.objects.get(event=event, attempt_number=3)
    assert third.manual and third.succeeded


def test_resend_restarts_the_retry_schedule(staff_client, hooked, receiver, monkeypatch):
    receiver.status = 500
    event = give_up(make_event(hooked))
    monkeypatch.setattr(delivery._random, "uniform", lambda a, b: 1.0)
    admin = staff_client("administrator")
    assert admin.post(f"/internal/webhooks/{event.public_id}/resend",
                      content_type="application/json").status_code == 202
    before = timezone.now()
    delivery.deliver_due()
    event.refresh_from_db()
    assert event.status == "pending" and event.first_failed_at >= before
    # First retry after a resend waits the first delay (60 s), not the window end.
    assert 55 <= (event.next_attempt_at - before).total_seconds() <= 65


def test_resend_refused_while_queued_without_endpoint_or_over_limit(
        staff_client, hooked, receiver, settings):
    event = make_event(hooked)
    operator = staff_client("merchant_operator", merchant=hooked.merchant)
    url = f"/internal/webhooks/{event.public_id}/resend"
    r = operator.post(url, content_type="application/json")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "already_queued")

    delivery.deliver_due()  # delivered
    settings.GATEWAY_RULES = {**settings.GATEWAY_RULES, "WEBHOOK_MAX_MANUAL_RESENDS": 1}
    assert operator.post(url, content_type="application/json").status_code == 202
    delivery.deliver_due()
    r = operator.post(url, content_type="application/json")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "resend_limit")

    settings.GATEWAY_RULES = {**settings.GATEWAY_RULES, "WEBHOOK_MAX_MANUAL_RESENDS": 5}
    hooked.merchant.webhook_url_approved = False
    hooked.merchant.save(update_fields=["webhook_url_approved"])
    r = operator.post(url, content_type="application/json")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "no_approved_endpoint")
    assert AuditEvent.objects.filter(action="webhook.resent").count() == 1


def test_excerpt_is_one_short_printable_line():
    text = "line one\r\nline\ttwo \x07" + "x" * 1000
    out = delivery.excerpt(text)
    assert out.startswith("line one line two x")
    assert len(out) == WebhookAttempt.RESPONSE_EXCERPT_CHARS and out.endswith("…")
    assert delivery.excerpt("") == ""
