"""Hosted checkout: card entry, submit, simulator answers, result (sprint 2, S1 without screening)."""
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.events import signing
from apps.events.models import OutboxEvent
from apps.payments.models import Operation, Payment
from apps.vault.models import StoredCard

pytestmark = pytest.mark.django_db(databases=["default", "vault"])

PAN = "4242424242424242"


def card(number=PAN, **extra):
    return {"number": number, "expiry_month": 12, "expiry_year": 2030, "cvc": "123", "privacy_consent": True, **extra}


@pytest.fixture
def browser():
    return APIClient()


@pytest.fixture
def make_payment(shop):
    def make(**overrides):
        from conftest import valid_body

        r = shop.create_payment(valid_body(**overrides))
        assert r.status_code == 201, r.content
        return Payment.objects.get(public_id=r.json()["id"])

    return make


@pytest.fixture
def payment(make_payment):
    return make_payment()


def url(payment, suffix=""):
    return f"/checkout/{payment.checkout_session_id}{suffix}"


def pay(browser, payment, number=PAN):
    r = browser.post(url(payment, "/card"), card(number), format="json")
    assert r.status_code == 200, r.content
    return browser.post(url(payment, "/submit"), {}, format="json")


# --- session summary (C3) -------------------------------------------------------------------

def test_session_summary_shows_order_but_never_lets_browser_set_it(browser, payment, shop):
    r = browser.get(url(payment))
    assert r.status_code == 200 and r["Cache-Control"] == "no-store"
    data = r.json()
    assert data["merchant"] == {"name": shop.merchant.name}
    assert (data["amount"], data["currency"], data["status"]) == (4590, "SGD", "created")
    assert data["reference"] is None  # shown once submitted
    assert data["customer_email_masked"] == "a•••@example.com"
    assert data["email_required"] is False
    assert data["return_url"].endswith(f"?payment_id={payment.public_id}")
    # Extra fields in the card body cannot change the amount.
    r = browser.post(url(payment, "/card"), card(amount=1), format="json")
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_field"


def test_session_shows_line_items(browser, make_payment):
    items = [{"name": "Wireless mouse", "quantity": 1, "unit_amount": 2990},
             {"name": "USB-C hub", "quantity": 1, "unit_amount": 1600}]
    payment = make_payment(line_items=items)
    assert browser.get(url(payment)).json()["line_items"] == items


@pytest.mark.parametrize("session_id", ["cs_" + "x" * 24, "nope", "cs_short"])
def test_unknown_session_is_404(browser, session_id):
    r = browser.get(f"/checkout/{session_id}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "resource_not_found"


def test_form_posts_are_refused(browser, payment):
    r = browser.post(url(payment, "/card"), card(), format="multipart")
    assert r.status_code == 415


# --- card entry -----------------------------------------------------------------------------

@pytest.mark.parametrize(("number", "code"), [
    ("4242424242424241", "invalid_card_number"),
    ("4242", "invalid_card_number"),
])
def test_bad_card_is_rejected_without_echoing_it(browser, payment, number, code):
    r = browser.post(url(payment, "/card"), card(number), format="json")
    assert r.status_code == 400 and r.json()["error"]["code"] == code
    assert number not in r.content.decode()
    assert not StoredCard.objects.using("vault").exists()


def test_card_entry_keeps_only_a_summary_on_the_payment(browser, payment):
    r = browser.post(url(payment, "/card"), card(), format="json")
    assert r.json()["card"] == {"brand": "visa", "last4": "4242"}
    payment.refresh_from_db()
    assert payment.card_token.startswith("tok_") and payment.card_last4 == "4242"
    assert len(payment.card_fingerprint) == 64


def test_replacing_the_card_discards_the_first(browser, payment):
    browser.post(url(payment, "/card"), card(), format="json")
    browser.post(url(payment, "/card"), card("5555555555554444"), format="json")
    assert StoredCard.objects.using("vault").count() == 1
    payment.refresh_from_db()
    assert payment.card_brand == "mastercard"


def test_email_is_asked_for_when_the_shop_did_not_send_one(browser, make_payment):
    payment = make_payment(customer_email=...)
    assert browser.get(url(payment)).json()["email_required"] is True
    r = browser.post(url(payment, "/card"), card(), format="json")
    assert r.json()["error"]["code"] == "invalid_email"
    r = browser.post(url(payment, "/card"), card(email="sam@example.com"), format="json")
    assert r.status_code == 200
    payment.refresh_from_db()
    assert payment.customer_email == "sam@example.com"


# --- submit (C4 -> C6/C7) ----------------------------------------------------------------------

def test_s1_without_screening_approved(browser, payment, shop, fake_sim, payment_schema):
    r = pay(browser, payment)
    assert r.status_code == 200, r.content
    data = r.json()
    assert (data["status"], data["result"]) == ("authorised", "approved")
    assert data["reference"] == payment.reference and data["authorised_at"]

    payment.refresh_from_db()
    assert payment.screening_decision == "allow"
    op = Operation.objects.get(payment=payment)
    assert (op.type, op.status) == ("authorise", "succeeded")
    assert op.simulator_reference.startswith("sim_")
    assert signing.verify(op.evidence_body.encode(), op.evidence_signature,
                          fake_sim.secret)
    # The simulator got the gateway's operation ID and the card once; the vault is empty.
    [(_method, _path, sent)] = fake_sim.requests
    assert sent["operation_id"] == op.public_id and sent["amount"] == 4590
    assert not StoredCard.objects.using("vault").exists()
    # Outbox: processing then authorised, in order, in the payment's sequence.
    events = list(OutboxEvent.objects.filter(payment=payment).order_by("sequence"))
    assert [(e.type, e.sequence) for e in events] == [
        ("payment.processing", 2), ("payment.authorised", 3)]
    # The merchant sees it through the signed API.
    api = shop.get(f"/v1/payments/{payment.public_id}")
    payment_schema.validate(api.json())
    assert api.json()["status"] == "authorised"
    assert api.json()["card"]["last4"] == "4242"
    assert AuditEvent.objects.filter(target_id=payment.public_id,
                                     action="payment.authorised").exists()


@pytest.mark.parametrize("number", ["4000000000009995", "4000000000000002"])
def test_declined(browser, payment, fake_sim, number):
    data = pay(browser, payment, number).json()
    assert (data["status"], data["result"]) == ("declined", "declined")
    payment.refresh_from_db()
    assert payment.outcome_reason == "card_declined"
    assert Operation.objects.get(payment=payment).status == "failed"
    assert OutboxEvent.objects.filter(payment=payment, type="payment.declined").exists()


@pytest.mark.parametrize("mode", ["normal", "bad_signature", "unsigned", "http_500"])
def test_no_usable_answer_makes_payment_unresolved(browser, payment, fake_sim, mode):
    fake_sim.mode = mode
    number = "4000000000000119" if mode == "normal" else PAN  # lost response, S4
    data = pay(browser, payment, number).json()
    assert (data["status"], data["result"]) == ("unresolved", "pending")
    op = Operation.objects.get(payment=payment)
    assert op.status == "unresolved" and op.evidence_body == ""
    assert OutboxEvent.objects.filter(payment=payment, type="payment.unresolved").exists()


def test_submitting_twice_calls_the_simulator_once(browser, payment, fake_sim):
    pay(browser, payment)
    again = browser.post(url(payment, "/submit"), {}, format="json")
    assert again.status_code == 200 and again.json()["status"] == "authorised"
    assert len(fake_sim.requests) == 1
    r = browser.post(url(payment, "/card"), card(), format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "payment_already_submitted"


def test_submit_without_card(browser, payment, fake_sim):
    r = browser.post(url(payment, "/submit"), {}, format="json")
    assert r.status_code == 400 and r.json()["error"]["code"] == "card_required"
    assert fake_sim.requests == []


def test_vaulted_card_gone_asks_for_it_again(browser, payment, fake_sim):
    browser.post(url(payment, "/card"), card(), format="json")
    StoredCard.objects.using("vault").all().delete()
    r = browser.post(url(payment, "/submit"), {}, format="json")
    assert r.json()["error"]["code"] == "card_required"
    payment.refresh_from_db()
    assert payment.status == "created" and payment.card_token == ""


def test_expired_session(browser, payment, fake_sim):
    browser.post(url(payment, "/card"), card(), format="json")
    Payment.objects.filter(pk=payment.pk).update(
        checkout_expires_at=timezone.now() - timedelta(seconds=1))
    data = browser.get(url(payment)).json()
    assert (data["status"], data["result"]) == ("expired", "expired")
    assert OutboxEvent.objects.filter(payment=payment, type="payment.expired").count() == 1
    assert not StoredCard.objects.using("vault").exists()
    r = browser.post(url(payment, "/submit"), {}, format="json")
    assert r.status_code == 410 and r.json()["error"]["code"] == "checkout_expired"
    browser.get(url(payment))
    assert OutboxEvent.objects.filter(payment=payment, type="payment.expired").count() == 1


def test_no_card_data_outside_the_vault(browser, payment, fake_sim):
    """CONTRIBUTING rule 1: no card number in payments, audit, outbox or idempotency rows."""
    pay(browser, payment)
    with connection.cursor() as cur:
        for table in ("payments_payment", "payments_operation", "payments_idempotencyrecord",
                      "audit_auditevent", "events_outboxevent"):
            cur.execute(f"SELECT coalesce(string_agg(row_to_json(t)::text, ' '), '') "
                        f"FROM {table} t")
            assert PAN not in cur.fetchone()[0], table


def test_result_endpoint(browser, payment, fake_sim):
    pay(browser, payment, "4000000000000002")
    r = browser.get(url(payment, "/result"))
    assert r.json()["result"] == "declined"
    assert "fraud" not in r.content.decode()
