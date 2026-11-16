"""Reconciliation of unresolved operations (UC-29, UC-43, SIMULATOR-CONTRACT.md 6-7, S4)."""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.events.models import OutboxEvent
from apps.payments import reconciliation
from apps.payments.models import Operation, Payment

pytestmark = pytest.mark.django_db(databases=["default", "vault"])

LOST_RESPONSE = "4000000000000119"
SLOW = "4000000000000127"
LOST_REQUEST = "4000000000000135"


def pay(shop, number):
    from conftest import valid_body

    payment = Payment.objects.get(public_id=shop.create_payment(valid_body()).json()["id"])
    browser = APIClient()
    base = f"/checkout/{payment.checkout_session_id}"
    card = {"number": number, "expiry_month": 12, "expiry_year": 2030, "cvc": "123", "privacy_consent": True}
    assert browser.post(f"{base}/card", card, format="json").status_code == 200
    assert browser.post(f"{base}/submit", {}, format="json").status_code == 200
    payment.refresh_from_db()
    return payment


def make_due(operation=None):
    qs = Operation.objects.filter(status="unresolved")
    if operation is not None:
        qs = qs.filter(pk=operation.pk)
    qs.update(next_check_at=timezone.now() - timedelta(seconds=1))


def status_queries(fake_sim):
    return [path for method, path, _ in fake_sim.requests
            if method == "GET" and path.startswith("/sim/operations/")]


def test_first_check_is_scheduled_about_30_seconds_after_the_timeout(shop, fake_sim):
    before = timezone.now()
    payment = pay(shop, LOST_RESPONSE)
    assert payment.status == "unresolved"
    op = Operation.objects.get(payment=payment)
    assert op.status == "unresolved" and op.reconciliation_checks == 0
    assert timedelta(seconds=26) < op.next_check_at - before < timedelta(seconds=34)
    assert reconciliation.reconcile_due() == 0  # not due yet
    assert status_queries(fake_sim) == []


@pytest.mark.parametrize("number", [LOST_RESPONSE, SLOW])
def test_lost_response_is_authorised_with_the_original_operation_id(shop, fake_sim, number,
                                                                    payment_schema,
                                                                    event_schema):
    """Demo story S4: the simulator approved but the reply was lost."""
    payment = pay(shop, number)
    op = Operation.objects.get(payment=payment)
    make_due()
    assert reconciliation.reconcile_due() == 1

    payment.refresh_from_db()
    op.refresh_from_db()
    assert payment.status == "authorised" and payment.authorised_at
    assert (op.status, op.reconciliation_checks) == ("succeeded", 1)
    assert op.evidence_signature and op.simulator_reference
    # Asked about the same ID; never sent a second authorisation.
    assert status_queries(fake_sim) == [f"/sim/operations/{op.public_id}"]
    assert sum(1 for _, path, _ in fake_sim.requests if path == "/sim/authorise") == 1
    types = list(OutboxEvent.objects.filter(payment=payment).order_by("sequence")
                 .values_list("type", flat=True))
    assert types == ["payment.processing", "payment.unresolved", "payment.authorised"]
    event = OutboxEvent.objects.get(payment=payment, type="payment.authorised")
    event_schema(event.payload)
    payment_schema.validate(event.payload["data"]["object"])
    assert AuditEvent.objects.filter(action="payment.authorised",
                                     target_id=payment.public_id).exists()
    assert reconciliation.reconcile_due() == 0  # settled: nothing more to check


def test_lost_request_is_declined_not_processed_and_the_id_retired(shop, fake_sim):
    payment = pay(shop, LOST_REQUEST)
    make_due()
    reconciliation.reconcile_due()
    payment.refresh_from_db()
    assert (payment.status, payment.outcome_reason) == ("declined", "not_processed")
    op = Operation.objects.get(payment=payment)
    assert op.status == "not_processed"
    assert fake_sim.records[op.public_id]["status"] == "no_record"
    assert OutboxEvent.objects.filter(payment=payment, type="payment.declined").exists()
    page = APIClient().get(f"/checkout/{payment.checkout_session_id}").json()
    assert page["result"] == "not_completed"  # not "your bank declined": it never got it


def test_checkout_page_shows_the_result_after_reconciliation(shop, fake_sim):
    payment = pay(shop, LOST_RESPONSE)
    browser = APIClient()
    url = f"/checkout/{payment.checkout_session_id}"
    assert browser.get(url).json()["result"] == "pending"
    make_due()
    reconciliation.reconcile_due()
    assert browser.get(url).json()["result"] == "approved"


def test_schedule_then_escalation_after_six_checks(shop, fake_sim, settings):
    """30 s, 1, 2, 5, 10, 20 min, then escalated (S2, about 38.5 minutes, NFR-AVA-03)."""
    payment = pay(shop, LOST_RESPONSE)
    op = Operation.objects.get(payment=payment)
    fake_sim.status_mode = "fail"
    delays = settings.GATEWAY_RULES["RECONCILIATION_DELAYS_SECONDS"]
    for n in range(1, 6):
        make_due()
        start = timezone.now()
        assert reconciliation.reconcile_due() == 1
        op.refresh_from_db()
        assert op.reconciliation_checks == n and op.escalated_at is None
        wait = (op.next_check_at - start).total_seconds()
        assert delays[n] * 0.9 - 1 <= wait <= delays[n] * 1.1 + 1
    assert sum(delays) == 2310  # 38.5 minutes in all
    make_due()
    reconciliation.reconcile_due()
    op.refresh_from_db()
    assert op.reconciliation_checks == 6 and op.escalated_at and op.next_check_at is None
    assert op.status == "unresolved"
    payment.refresh_from_db()
    assert payment.status == "unresolved"  # nobody guesses an outcome
    assert AuditEvent.objects.filter(action="operation.escalated",
                                     target_id=payment.public_id).exists()
    Operation.objects.filter(pk=op.pk).update(next_check_at=timezone.now())
    assert reconciliation.reconcile_due() == 0  # escalated: no more automatic checks
    assert len(status_queries(fake_sim)) == 6


def test_admin_recheck_settles_an_escalated_operation(shop, fake_sim):
    payment = pay(shop, LOST_RESPONSE)
    op = Operation.objects.get(payment=payment)
    Operation.objects.filter(pk=op.pk).update(escalated_at=timezone.now(), next_check_at=None,
                                              reconciliation_checks=6)
    result = reconciliation.check(op.pk, actor=("staff", "admin"), manual=True)
    assert result.status == "succeeded" and result.reconciliation_checks == 6
    payment.refresh_from_db()
    assert payment.status == "authorised"
    assert AuditEvent.objects.filter(action="operation.rechecked", actor_id="admin").exists()


def test_admin_recheck_without_answer_changes_nothing(shop, fake_sim):
    payment = pay(shop, LOST_RESPONSE)
    op = Operation.objects.get(payment=payment)
    fake_sim.status_mode = "fail"
    result = reconciliation.check(op.pk, actor=("staff", "admin"), manual=True)
    assert result.status == "unresolved" and result.reconciliation_checks == 0
    assert AuditEvent.objects.filter(action="operation.recheck_no_answer").exists()


def test_id_conflict_is_escalated_at_once(shop, fake_sim):
    payment = pay(shop, LOST_RESPONSE)
    fake_sim.status_mode = "conflict"
    make_due()
    reconciliation.reconcile_due()
    op = Operation.objects.get(payment=payment)
    assert op.status == "unresolved" and op.escalated_at is not None
    assert op.reconciliation_checks == 1


def test_bad_signature_counts_as_no_answer(shop, fake_sim):
    payment = pay(shop, LOST_RESPONSE)
    fake_sim.mode = "bad_signature"
    make_due()
    reconciliation.reconcile_due()
    op = Operation.objects.get(payment=payment)
    assert op.status == "unresolved" and op.reconciliation_checks == 1
    payment.refresh_from_db()
    assert payment.status == "unresolved"


def test_stale_pending_operation_is_recovered_after_a_crash(shop, fake_sim):
    """FR-TXN-15: committed, then the process died before the simulator answered."""
    from conftest import valid_body

    payment = Payment.objects.get(public_id=shop.create_payment(valid_body()).json()["id"])
    Payment.objects.filter(pk=payment.pk).update(status="processing")
    op = Operation.objects.create(payment=payment, type="authorise", amount=payment.amount)
    fake_sim.records[op.public_id] = fake_sim.record(
        {"operation_id": op.public_id, "merchant_id": shop.merchant.public_id,
         "payment_id": payment.public_id, "amount": payment.amount,
         "card": {"number": "4242424242424242"}}, "approved")
    assert reconciliation.reconcile_due() == 0  # too recent: the call may still be running
    Operation.objects.filter(pk=op.pk).update(
        created_at=timezone.now() - timedelta(minutes=2))
    assert reconciliation.reconcile_due() == 1  # marked unresolved and checked at once
    payment.refresh_from_db()
    assert payment.status == "authorised"
    assert list(OutboxEvent.objects.filter(payment=payment).order_by("sequence")
                .values_list("type", flat=True)) == ["payment.unresolved",
                                                     "payment.authorised"]


# --- capture and cancel -----------------------------------------------------------------------

def settle(shop, payment, action):
    return shop.post(f"/v1/payments/{payment.public_id}/{action}", {}, format="json",
                     headers={"Idempotency-Key": str(uuid.uuid4())})


def test_unresolved_capture_is_settled(shop, fake_sim, payment_schema):
    payment = pay(shop, "4242424242424242")
    fake_sim.settle_mode = "hang"
    assert settle(shop, payment, "capture").status_code == 202
    capture = Operation.objects.get(type="capture")
    # The capture reached the simulator, only the reply was lost.
    fake_sim.settle_mode = "normal"
    fake_sim.settle("capture", {"operation_id": capture.public_id,
                                "authorisation_id": Operation.objects.get(
                                    type="authorise").public_id,
                                "amount": capture.amount})
    make_due()
    reconciliation.reconcile_due()
    payment.refresh_from_db()
    assert (payment.status, payment.captured_amount) == ("captured", 4590)
    r = shop.get(f"/v1/payments/{payment.public_id}")
    payment_schema.validate(r.json())
    assert r.json()["pending_operation"] is None
    assert OutboxEvent.objects.filter(payment=payment, type="payment.captured").exists()


def test_capture_the_simulator_never_got_is_retired(shop, fake_sim):
    payment = pay(shop, "4242424242424242")
    fake_sim.settle_mode = "hang"
    settle(shop, payment, "capture")
    make_due()
    reconciliation.reconcile_due()
    payment.refresh_from_db()
    assert payment.status == "authorised"
    assert Operation.objects.get(type="capture").status == "not_processed"
    fake_sim.settle_mode = "normal"
    r = settle(shop, payment, "capture")  # a new key may try again
    assert r.status_code == 200 and r.json()["status"] == "captured"
