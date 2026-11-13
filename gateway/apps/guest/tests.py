"""Receipts (FR-CHK-15) and the guest status check (FR-ACC-05, FR-ACC-06; contract section 8)."""
import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.core import mail
from django.utils import timezone
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from rest_framework.test import APIClient

from apps.events import emails
from apps.events.models import OutboundEmail
from apps.guest import service
from apps.guest.models import StatusChallenge, StatusLock, StatusSession
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db(databases=["default", "vault"])
CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
EMAIL = "alex@example.com"


def pay(shop, number="4242424242424242"):
    from conftest import valid_body

    payment = Payment.objects.get(public_id=shop.create_payment(valid_body()).json()["id"])
    browser = APIClient()
    base = f"/checkout/{payment.checkout_session_id}"
    card = {"number": number, "expiry_month": 12, "expiry_year": 2030, "cvc": "123"}
    assert browser.post(f"{base}/card", card, format="json").status_code == 200
    assert browser.post(f"{base}/submit", {}, format="json").status_code == 200
    payment.refresh_from_db()
    return payment


def send_queued():
    OutboundEmail.objects.filter(status="pending").update(next_attempt_at=timezone.now())
    return emails.send_due()


@pytest.fixture
def view_schema():
    spec = json.loads(json.dumps(__import__("yaml").safe_load(
        (CONTRACTS / "openapi" / "guest-status.v1.yaml").read_text())))
    payment = json.loads((CONTRACTS / "schemas" / "payment.schema.json").read_text())
    error = json.loads((CONTRACTS / "schemas" / "error.schema.json").read_text())
    registry = Registry().with_resources([
        ("../schemas/payment.schema.json", Resource.from_contents(payment)),
        ("../schemas/error.schema.json", Resource.from_contents(error)),
    ])
    schemas = spec["components"]["schemas"]
    return {name: Draft202012Validator(schemas[name], registry=registry)
            for name in ("GuestPaymentView", "CodeRequested", "CodeError")}


# --- receipts --------------------------------------------------------------------------

def test_authorised_payment_queues_a_receipt_sent_by_the_worker(shop, fake_sim):
    payment = pay(shop)
    assert payment.status == "authorised"
    queued = OutboundEmail.objects.get(payment=payment)
    assert queued.kind == "receipt" and queued.status == "pending"
    assert payment.reference not in queued.body_encrypted  # stored encrypted
    mail.outbox.clear()
    assert send_queued() == 1
    queued.refresh_from_db()
    assert queued.status == "sent" and queued.body_encrypted == ""
    (message,) = mail.outbox
    assert message.to == [EMAIL]
    assert payment.reference in message.subject and "S$45.90" in message.subject
    assert f"Reference:  {payment.reference}" in message.body
    assert "Visa ending 4242" in message.body
    assert shop.merchant.name in message.body
    assert f"/guest/status?ref={payment.reference}" in message.body


def test_declined_payment_gets_no_receipt(shop, fake_sim):
    payment = pay(shop, "4000000000000002")
    assert payment.status == "declined"
    assert not OutboundEmail.objects.filter(payment=payment).exists()


def test_failed_email_is_retried_then_recorded(shop, fake_sim, monkeypatch):
    payment = pay(shop)
    calls = []

    def broken(*args, **kwargs):
        calls.append(1)
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(emails, "send_mail", broken)
    for _ in range(len(emails.RETRY_DELAYS_SECONDS) + 1):
        send_queued()
    queued = OutboundEmail.objects.get(payment=payment)
    assert queued.status == "failed" and queued.body_encrypted == ""
    assert queued.attempt_count == len(emails.RETRY_DELAYS_SECONDS) + 1
    assert queued.last_error == "ConnectionRefusedError"
    assert len(calls) == queued.attempt_count


def test_first_failure_waits_before_retrying(shop, fake_sim, monkeypatch):
    payment = pay(shop)
    monkeypatch.setattr(emails, "send_mail", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    send_queued()
    queued = OutboundEmail.objects.get(payment=payment)
    assert queued.status == "pending" and queued.attempt_count == 1
    assert queued.next_attempt_at > timezone.now() + timedelta(seconds=25)
    assert emails.send_due() == 0  # not due yet


# --- asking for a code -----------------------------------------------------------------

def ask(reference, email=EMAIL, client=None, ip="203.0.113.7"):
    client = client or APIClient()
    return client.post("/guest/status/code", {"reference": reference, "email": email},
                       format="json", REMOTE_ADDR=ip)


def code_from_mail() -> str:
    send_queued()
    codes = [m for m in (re.search(r"status code is (\d{6})", e.body) for e in mail.outbox) if m]
    return codes[-1].group(1)


def test_same_reply_whether_or_not_details_match(shop, fake_sim, view_schema):
    payment = pay(shop)
    mail.outbox.clear()
    OutboundEmail.objects.all().delete()
    match = ask(payment.reference)
    wrong_email = ask(payment.reference, "someone@example.com")
    unknown = ask("SP-ZZZZ-ZZZZ")
    malformed = ask("hello")
    replies = [match, wrong_email, unknown, malformed]
    assert {r.status_code for r in replies} == {202}
    bodies = [r.json() for r in replies]
    for body in bodies:
        view_schema["CodeRequested"].validate(body)
    assert len({b["message"] for b in bodies}) == 1
    assert len({b["challenge_id"] for b in bodies}) == 4
    # Only the match queues an email.
    assert OutboundEmail.objects.filter(kind="guest_status_code").count() == 1
    assert send_queued() == 1 and mail.outbox[0].to == [EMAIL]


def test_reference_is_case_space_and_dash_insensitive(shop, fake_sim):
    payment = pay(shop)
    loose = payment.reference.lower().replace("-", " ")
    assert service.normalise_reference(loose) == payment.reference
    ask(loose, EMAIL.upper())
    assert OutboundEmail.objects.filter(kind="guest_status_code").count() == 1


def test_bad_bodies(db):
    assert ask("SP-AAAA-AAAA", "not-an-email").json()["error"]["param"] == "email"
    response = APIClient().post("/guest/status/code", {"reference": "x"}, format="json")
    assert response.status_code == 400 and response.json()["error"]["code"] == "missing_field"


def test_code_requests_are_limited_per_pair(shop, fake_sim):
    payment = pay(shop)
    for _ in range(3):
        assert ask(payment.reference).status_code == 202
    limited = ask(payment.reference)
    assert limited.status_code == 429 and limited.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(limited["Retry-After"]) <= 15 * 60 + 1
    # Same limit for a pair that matches nothing, so 429 reveals nothing either.
    for _ in range(3):
        ask("SP-QQQQ-QQQQ", ip="198.51.100.1")
    assert ask("SP-QQQQ-QQQQ", ip="198.51.100.1").status_code == 429


def test_code_requests_are_limited_per_ip(db):
    for n in range(10):
        assert ask(f"SP-AAAA-AA{n:02d}", ip="192.0.2.9").status_code == 202
    assert ask("SP-AAAA-BBBB", ip="192.0.2.9").status_code == 429
    assert ask("SP-AAAA-BBBB", ip="192.0.2.10").status_code == 202


def test_new_code_replaces_the_old_one(shop, fake_sim):
    payment = pay(shop)
    mail.outbox.clear()
    first = ask(payment.reference).json()["challenge_id"]
    old_code = code_from_mail()
    second = ask(payment.reference).json()["challenge_id"]
    new_code = code_from_mail()
    stale = verify(first, old_code)
    assert stale.status_code == 400 and stale.json()["error"]["code"] == "code_expired"
    assert verify(second, new_code).status_code == 200


# --- entering the code -----------------------------------------------------------------

def verify(challenge_id, code, client=None):
    client = client or APIClient()
    return client.post("/guest/status/verify", {"challenge_id": challenge_id, "code": code},
                       format="json")


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


def test_correct_code_shows_the_payment_and_sets_the_cookie(shop, fake_sim, view_schema):
    payment = pay(shop)
    mail.outbox.clear()
    challenge = ask(payment.reference).json()["challenge_id"]
    browser = APIClient()
    response = verify(challenge, code_from_mail(), browser)
    assert response.status_code == 200
    view = response.json()
    view_schema["GuestPaymentView"].validate(view)
    assert view["reference"] == payment.reference and view["status_label"] == "Paid"
    assert view["card"] == {"brand": "visa", "last4": "4242"}
    assert [t["label"] for t in view["timeline"]][:1] == ["Payment started"]
    assert "Approved by the bank" in [t["label"] for t in view["timeline"]]
    assert "reasons" not in json.dumps(view) and "order_reference" not in view
    cookie = response.cookies[service.COOKIE]
    assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "Strict"
    assert cookie["path"] == "/guest/status" and int(cookie["max-age"]) == 15 * 60
    again = browser.get("/guest/status/payment")
    assert again.status_code == 200 and again.json()["reference"] == payment.reference
    assert again["Cache-Control"] == "no-store"


def test_code_is_single_use(shop, fake_sim):
    payment = pay(shop)
    mail.outbox.clear()
    challenge = ask(payment.reference).json()["challenge_id"]
    code = code_from_mail()
    assert verify(challenge, code).status_code == 200
    assert verify(challenge, code).json()["error"]["code"] == "code_expired"


def test_three_wrong_codes_lock_the_check_for_15_minutes(shop, fake_sim, view_schema):
    payment = pay(shop)
    mail.outbox.clear()
    challenge = ask(payment.reference).json()["challenge_id"]
    code = code_from_mail()
    first = verify(challenge, wrong(code))
    assert first.status_code == 400 and first.json()["attempts_remaining"] == 2
    view_schema["CodeError"].validate(first.json())
    assert verify(challenge, wrong(code)).json()["attempts_remaining"] == 1
    third = verify(challenge, wrong(code))
    assert third.status_code == 429 and third.json()["error"]["code"] == "status_check_locked"
    assert 14 * 60 < int(third["Retry-After"]) <= 15 * 60 + 1
    # Even the right code is refused while locked, and a new code request sends nothing.
    assert verify(challenge, code).status_code == 429
    OutboundEmail.objects.all().delete()
    StatusChallenge.objects.update(created_at=timezone.now() - timedelta(hours=1))
    fresh = ask(payment.reference)
    assert fresh.status_code == 202
    assert not OutboundEmail.objects.exists()
    assert verify(fresh.json()["challenge_id"], "123456").status_code == 429
    # After 15 minutes it opens again.
    StatusLock.objects.update(locked_until=timezone.now() - timedelta(seconds=1))
    challenge = ask(payment.reference).json()["challenge_id"]
    assert verify(challenge, code_from_mail()).status_code == 200


def test_wrong_codes_count_across_new_codes(shop, fake_sim):
    payment = pay(shop)
    mail.outbox.clear()
    for _ in range(2):
        challenge = ask(payment.reference).json()["challenge_id"]
        assert verify(challenge, wrong(code_from_mail())).status_code == 400
    challenge = ask(payment.reference).json()["challenge_id"]
    assert verify(challenge, wrong(code_from_mail())).status_code == 429


def test_challenge_that_matched_nothing_behaves_the_same(db):
    challenge = ask("SP-NONE-NONE").json()["challenge_id"]
    replies = [verify(challenge, "000000") for _ in range(3)]
    assert [r.status_code for r in replies] == [400, 400, 429]
    assert [r.json().get("attempts_remaining") for r in replies[:2]] == [2, 1]


def test_expired_code(shop, fake_sim):
    payment = pay(shop)
    mail.outbox.clear()
    challenge = ask(payment.reference).json()["challenge_id"]
    code = code_from_mail()
    StatusChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert verify(challenge, code).json()["error"]["code"] == "code_expired"


def test_expired_code_email_is_discarded_not_sent(shop, fake_sim):
    payment = pay(shop)
    ask(payment.reference)
    OutboundEmail.objects.filter(kind="guest_status_code").update(
        discard_after=timezone.now() - timedelta(seconds=1))
    mail.outbox.clear()
    send_queued()
    queued = OutboundEmail.objects.get(kind="guest_status_code")
    assert queued.status == "discarded" and queued.body_encrypted == ""
    assert all("status code" not in m.subject for m in mail.outbox)


def test_unknown_or_malformed_challenge(db):
    assert verify("gsc_" + "Z" * 24, "123456").json()["error"]["code"] == "code_expired"
    assert verify("nope", "123456").json()["error"]["param"] == "challenge_id"
    assert verify("gsc_" + "Z" * 24, "12").json()["error"]["param"] == "code"


# --- the session -----------------------------------------------------------------------

def unlocked(shop):
    payment = pay(shop)
    mail.outbox.clear()
    challenge = ask(payment.reference).json()["challenge_id"]
    browser = APIClient()
    assert verify(challenge, code_from_mail(), browser).status_code == 200
    return payment, browser


def test_no_cookie_no_payment(db):
    response = APIClient().get("/guest/status/payment")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "status_session_missing"


def test_session_expires_after_15_minutes(shop, fake_sim):
    _, browser = unlocked(shop)
    StatusSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    response = browser.get("/guest/status/payment")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "status_session_expired"


def test_sign_out_ends_the_session(shop, fake_sim):
    _, browser = unlocked(shop)
    assert browser.post("/guest/status/sign-out", {}, format="json").status_code == 204
    assert browser.get("/guest/status/payment").status_code == 401
    assert StatusSession.objects.get().ended_at is not None


def test_view_follows_later_changes(shop, fake_sim):
    payment, browser = unlocked(shop)
    assert shop.post(f"/v1/payments/{payment.public_id}/capture", {}, format="json",
                     headers={"Idempotency-Key": "capture-guest-view-0001"}).status_code == 200
    view = browser.get("/guest/status/payment").json()
    assert view["status"] == "captured" and view["status_label"] == "Paid"
    assert view["timeline"][-1]["label"] == "Charged"


@pytest.mark.parametrize("status, label", [
    ("authorised", "Paid"), ("captured", "Paid"), ("declined", "Not charged"),
    ("blocked", "Not charged"), ("cancelled", "Not charged"), ("expired", "Not charged"),
    ("unresolved", "Being checked - do not pay again"), ("processing", "In progress"),
    ("created", "In progress"),
])
def test_status_labels(status, label):
    assert service.status_label(status) == label
