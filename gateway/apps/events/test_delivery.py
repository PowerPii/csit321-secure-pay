"""Webhook delivery from the outbox (API-CONTRACT.md section 7)."""
import json
from datetime import timedelta
from itertools import pairwise

import httpx
import pytest
from django.db import transaction
from django.utils import timezone

from apps.events import delivery, signing
from apps.events.models import EventType, OutboxEvent, WebhookAttempt
from apps.events.outbox import record_payment_event
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db

HOOK = "https://shop.example/webhooks/securepay"


class Receiver:
    """The merchant's endpoint, through httpx.MockTransport."""

    def __init__(self):
        self.status = 200
        self.fail = None  # an httpx exception class to raise instead
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if self.fail:
            raise self.fail("boom", request=request)
        return httpx.Response(self.status, text="ok")


@pytest.fixture
def receiver(monkeypatch, settings):
    r = Receiver()
    monkeypatch.setattr(delivery, "TRANSPORT", httpx.MockTransport(r))
    settings.WEBHOOK_ALLOWED_PRIVATE_HOSTS = frozenset({"shop.example"})
    return r


@pytest.fixture
def hooked_shop(make_merchant):
    return make_merchant(webhook_url=HOOK, webhook_url_approved=True)


def make_event(client):
    payment_id = client.create_payment().json()["id"]
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(public_id=payment_id)
        payment.status = "expired"
        return record_payment_event(payment, EventType.PAYMENT_EXPIRED)


def test_delivers_signed_event_with_contract_headers(hooked_shop, receiver):
    event = make_event(hooked_shop)
    assert delivery.deliver_due() == 1
    (request,) = receiver.requests
    assert str(request.url) == HOOK
    assert request.headers["SecurePay-Event-Id"] == event.public_id
    assert request.headers["SecurePay-Event-Type"] == "payment.expired"
    assert request.headers["SecurePay-Delivery-Attempt"] == "1"
    assert request.headers["User-Agent"] == "SecurePay-Webhooks/1.0"
    assert signing.verify(request.content, request.headers["SecurePay-Signature"],
                          hooked_shop.secret)
    assert json.loads(request.content) == event.payload
    event.refresh_from_db()
    assert event.status == "delivered" and event.delivered_at
    attempt = WebhookAttempt.objects.get()
    assert (attempt.attempt_number, attempt.http_status, attempt.succeeded) == (1, 200, True)
    assert delivery.deliver_due() == 0  # nothing left


def test_event_payload_validates_against_the_contract(hooked_shop, receiver, event_schema):
    event = make_event(hooked_shop)
    event_schema(event.payload)


@pytest.mark.parametrize("failure", ["500", "302", "timeout", "connect"])
def test_failure_schedules_a_retry(hooked_shop, receiver, failure):
    if failure == "timeout":
        receiver.fail = httpx.ReadTimeout
    elif failure == "connect":
        receiver.fail = httpx.ConnectError
    else:
        receiver.status = int(failure)
    event = make_event(hooked_shop)
    before = timezone.now()
    delivery.deliver_due()
    event.refresh_from_db()
    assert event.status == "pending" and event.attempt_count == 1
    assert event.first_failed_at is not None
    delay = (event.next_attempt_at - before).total_seconds()
    assert 54 <= delay <= 67  # 60 s +/- 10%
    attempt = WebhookAttempt.objects.get()
    assert not attempt.succeeded
    assert attempt.http_status or attempt.error
    assert delivery.deliver_due() == 0  # not due yet


def test_retry_is_signed_fresh_with_next_attempt_number(hooked_shop, receiver):
    receiver.status = 503
    event = make_event(hooked_shop)
    delivery.deliver_due()
    OutboxEvent.objects.filter(pk=event.pk).update(next_attempt_at=timezone.now())
    receiver.status = 204
    delivery.deliver_due()
    first, second = receiver.requests
    assert second.headers["SecurePay-Delivery-Attempt"] == "2"
    assert second.content == first.content
    event.refresh_from_db()
    assert event.status == "delivered" and event.attempt_count == 2


def test_72_hour_schedule_makes_14_attempts_then_undelivered(hooked_shop, receiver,
                                                             monkeypatch):
    """Runs on an accelerated clock: each attempt happens when it is due."""
    receiver.status = 500
    monkeypatch.setattr(delivery._random, "uniform", lambda a, b: 1.0)
    event = make_event(hooked_shop)
    clock = timezone.now()
    monkeypatch.setattr(timezone, "now", lambda: clock)
    times = []
    for _ in range(20):
        event.refresh_from_db()
        if event.status != "pending":
            break
        clock = event.next_attempt_at
        times.append(clock)
        assert delivery.deliver_due() == 1
    event.refresh_from_db()
    assert event.status == "undelivered" and event.attempt_count == 14
    assert len(receiver.requests) == 14
    assert times[-1] - times[0] == timedelta(hours=72)  # the final attempt at the window end
    gaps = [(b - a).total_seconds() for a, b in pairwise(times)][:12]
    assert gaps == [60, 300, 900, 1800, 3600, 7200, 14400, 28800, 43200, 43200, 43200, 43200]


def test_unapproved_or_missing_endpoint_is_not_called(make_merchant, receiver):
    for fields in ({"webhook_url": HOOK, "webhook_url_approved": False}, {}):
        client = make_merchant(name=str(fields), **fields)
        make_event(client)
    delivery.deliver_due()
    assert receiver.requests == []
    assert set(WebhookAttempt.objects.values_list("error", flat=True)) == {"no_approved_endpoint"}


@pytest.mark.parametrize(("url", "error"), [
    ("http://shop.example/hook", "not_https"),
    ("https://127.0.0.1/hook", "blocked_address"),
    ("https://10.1.2.3/hook", "blocked_address"),
    ("https://169.254.169.254/latest", "blocked_address"),
    ("https://[::1]/hook", "blocked_address"),
])
def test_private_or_plain_http_addresses_are_refused(make_merchant, receiver, url, error):
    client = make_merchant(webhook_url=url, webhook_url_approved=True)
    make_event(client)
    delivery.deliver_due()
    assert receiver.requests == []
    assert WebhookAttempt.objects.get().error == error


def test_two_workers_never_claim_the_same_event(hooked_shop, receiver):
    make_event(hooked_shop)
    first = delivery.claim_due(10)
    second = delivery.claim_due(10)
    assert len(first) == 1 and second == []


def test_crashed_worker_lease_runs_out(hooked_shop, receiver, settings):
    event = make_event(hooked_shop)
    delivery.claim_due(10)  # claimed, then the worker died
    assert delivery.claim_due(10) == []
    OutboxEvent.objects.filter(pk=event.pk).update(
        next_attempt_at=timezone.now() - timedelta(seconds=1))
    assert delivery.deliver_due() == 1
    event.refresh_from_db()
    assert event.status == "delivered"


def test_delivery_failure_never_changes_the_payment(hooked_shop, receiver):
    receiver.status = 500
    event = make_event(hooked_shop)
    before = Payment.objects.get(pk=event.payment_id)
    delivery.deliver_due()
    after = Payment.objects.get(pk=event.payment_id)
    assert (after.status, after.sequence) == (before.status, before.sequence)
