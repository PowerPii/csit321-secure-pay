"""URS 4.4.2 Integrity: NFR-INT-03 and NFR-INT-04 at the URS's own numbers.

NFR-INT-01 is checked on the receiving side, in merchant/apps/webhooks/test_acceptance.py.
NFR-INT-02 is apps/security/test_integrity.py::test_ten_entries_edited_deleted_or_reordered_are_all_detected.
"""
import threading
import uuid

import httpx
import pytest
from django.core.cache import cache
from django.db import connection
from django.db.models import Sum
from nfr_helpers import LOST_RESPONSE, capture, card, pay, refund
from rest_framework.test import APIClient

from apps.payments import reconciliation
from apps.payments.models import Operation, Payment
from apps.refunds.models import Refund

ORDER_ATTEMPT = "order-10042-attempt-1"


@pytest.mark.django_db(databases=["default", "vault"])
def test_nfr_int_03_one_request_sent_100_times_is_charged_once(shop, fake_sim):
    """100 identical requests with one Idempotency-Key, through a processing timeout."""
    from conftest import valid_body

    created = [shop.create_payment(valid_body(), key=ORDER_ATTEMPT) for _ in range(100)]
    assert {r.status_code for r in created} == {201}
    assert len({r.json()["id"] for r in created}) == 1
    assert created[-1]["Idempotent-Replayed"] == "true"
    assert Payment.objects.count() == 1
    payment = Payment.objects.get()

    # The bank's reply is lost on the first submit (simulated timeout): the payment is
    # unresolved, and 99 more submits must not send the card again. Retries spread over
    # minutes in real life, so the per-minute rate limits are reset between the batches.
    cache.clear()
    browser = APIClient()
    base = f"/checkout/{payment.checkout_session_id}"
    assert browser.post(f"{base}/card", card(LOST_RESPONSE), format="json").status_code == 200
    for _ in range(100):
        r = browser.post(f"{base}/submit", {}, format="json")
        assert r.status_code in (200, 409, 429), r.content  # answered, refused or slowed
    payment.refresh_from_db()
    assert payment.status == "unresolved"
    Operation.objects.filter(status="unresolved").update(next_check_at=payment.created_at)
    reconciliation.reconcile_due()
    payment.refresh_from_db()
    assert payment.status == "authorised"

    authorise_calls = [b for m, p, b in fake_sim.requests if p == "/sim/authorise"]
    approvals = [r for r in fake_sim.records.values()
                 if r["type"] == "authorise" and r["status"] == "approved"]
    assert len(authorise_calls) == 1 and len(approvals) == 1  # exactly one charge

    cache.clear()
    capture_key = str(uuid.uuid4())
    for _ in range(100):
        r = shop.post(f"/v1/payments/{payment.public_id}/capture", {}, format="json",
                      headers={"Idempotency-Key": capture_key})
        assert r.status_code == 200, r.content
    assert len([1 for m, p, b in fake_sim.requests if p == "/sim/capture"]) == 1


@pytest.mark.django_db(databases=["default", "vault"], transaction=True)
def test_nfr_int_04_fifty_simultaneous_refunds_never_exceed_the_refundable_amount(
        shop, fake_sim):
    payment = capture(shop, pay(shop))
    refundable = payment.captured_amount
    amount = 100
    assert 50 * amount > refundable  # the requests ask for more than can be refunded

    # The simulator answers most refunds but loses every seventh reply: those stay
    # unresolved and must keep their reservation.
    lock, served = threading.Lock(), [0]
    answer = fake_sim.refund

    def flaky_refund(request, body):
        with lock:
            served[0] += 1
            reply = answer(request, body)
            if served[0] % 7 == 0:
                raise httpx.ReadTimeout("reply lost", request=request)
            return reply

    fake_sim.refund = flaky_refund

    barrier = threading.Barrier(50)
    results, done, overdrawn = [], threading.Event(), []

    def holding_total():
        totals = (Refund.objects.filter(payment_id=payment.pk)
                  .exclude(status=Refund.Status.FAILED).aggregate(total=Sum("amount")))
        return totals["total"] or 0

    def watch():
        try:
            while not done.is_set():
                total = holding_total()
                if total > refundable:
                    overdrawn.append(total)
        finally:
            connection.close()

    def run():
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {shop.key}")
        barrier.wait()
        try:
            results.append(refund(client, payment, amount).status_code)
        finally:
            connection.close()

    watcher = threading.Thread(target=watch)
    watcher.start()
    threads = [threading.Thread(target=run) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    done.set()
    watcher.join()

    assert len(results) == 50 and set(results) <= {201, 202, 409, 422}, results
    assert overdrawn == []  # completed + reserved never above the refundable amount
    refunds = Refund.objects.filter(payment_id=payment.pk)
    completed = sum(r.amount for r in refunds if r.status == Refund.Status.COMPLETED)
    held = sum(r.amount for r in refunds if r.status in Refund.HOLDING)
    assert completed + held <= refundable
    unresolved = [r for r in refunds if r.status == Refund.Status.UNRESOLVED]
    assert unresolved, "the simulator was meant to leave some refunds unresolved"
    for item in unresolved:  # each keeps its reservation until reconciliation settles it
        assert item.amount == amount
    assert results.count(422) >= 50 - refundable // amount
