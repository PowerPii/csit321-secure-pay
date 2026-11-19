"""Customer accounts (FR-ACC-01 to FR-ACC-04, FR-ACC-07, FR-ACC-08; screens C10 to C12)."""
import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AccountToken
from apps.audit.models import AuditEvent
from apps.customers import service
from apps.customers.models import CustomerAccount, CustomerSession
from apps.events.emails import send_due
from apps.events.models import OutboundEmail
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db(databases=["default", "vault"])

EMAIL = "jane@example.com"
PASSWORD = "correct horse battery 7"
NEW_PASSWORD = "a brand new passphrase 42"


def post(client, path, body=None):
    return client.post(f"/customer/{path}", body or {}, format="json")


def register(client=None, email=EMAIL, password=PASSWORD, **extra):
    client = client or APIClient()
    body = {"full_name": "Jane Tan", "email": email, "password": password,
            "privacy_consent": True, **extra}
    return client, post(client, "register", body)


def sign_in(client=None, email=EMAIL, password=PASSWORD):
    client = client or APIClient()
    return client, post(client, "sign-in", {"email": email, "password": password})


@pytest.fixture
def customer():
    _, response = register()
    assert response.status_code == 201, response.json()
    return CustomerAccount.objects.get(email=EMAIL)


def pay(shop, browser, number="4242424242424242"):
    """Pay a demo-shop payment in `browser` (which may be signed in)."""
    from conftest import valid_body

    payment = Payment.objects.get(public_id=shop.create_payment(valid_body()).json()["id"])
    base = f"/checkout/{payment.checkout_session_id}"
    card = {"number": number, "expiry_month": 12, "expiry_year": 2030, "cvc": "123", "privacy_consent": True}
    assert browser.post(f"{base}/card", card, format="json").status_code == 200
    assert browser.post(f"{base}/submit", {}, format="json").status_code == 200
    payment.refresh_from_db()
    return payment


# --- sign-up (FR-ACC-01) ---------------------------------------------------------------

def test_register_creates_an_account_and_signs_in():
    client, response = register(email="  Jane@Example.com ")
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL and body["full_name"] == "Jane Tan"
    assert body["id"].startswith("cus_")
    cookie = response.cookies[service.COOKIE]
    assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "Strict"
    assert cookie["path"] == "/" and not cookie["max-age"]  # ends with the browser
    account = CustomerAccount.objects.get()
    assert account.password.startswith("argon2") and PASSWORD not in account.password
    assert CustomerSession.objects.get().token_hash != cookie.value  # only a hash is kept
    assert client.get("/customer/me").json()["email"] == EMAIL
    assert AuditEvent.objects.filter(action="customer.registered").exists()


def test_register_refuses_an_email_already_registered(customer):
    _, response = register(email="JANE@example.com")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"
    assert response.json()["error"]["param"] == "email"
    assert CustomerAccount.objects.count() == 1


@pytest.mark.parametrize("password", ["short pass", "123456789012345", "password1234"])
def test_register_refuses_weak_passwords(password):
    _, response = register(password=password)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "weak_password"
    assert not CustomerAccount.objects.exists()


@pytest.mark.parametrize("body,param", [
    ({"email": EMAIL, "password": PASSWORD, "privacy_consent": True}, "full_name"),
    ({"full_name": "Jane", "email": "not-an-email", "password": PASSWORD}, "email"),
    ({"full_name": "Jane", "email": EMAIL, "password": PASSWORD, "admin": True}, "admin"),
    ({"full_name": "Jane", "email": EMAIL, "password": PASSWORD}, "privacy_consent"),
    ({"full_name": "Jane", "email": EMAIL, "password": PASSWORD, "privacy_consent": "yes"},
     "privacy_consent"),
])
def test_register_names_the_field_to_correct(body, param):
    response = post(APIClient(), "register", body)
    assert response.status_code == 400 and response.json()["error"]["param"] == param


def test_customers_are_not_staff(customer):
    """A customer session never opens the staff API, and is not a Django user."""
    client, _ = sign_in()
    assert client.get("/internal/me").status_code in (401, 403)
    from django.contrib.auth import get_user_model
    assert not get_user_model().objects.filter(email=EMAIL).exists()


# --- sign-in and lockout (FR-ACC-02, FR-ACC-03) ----------------------------------------

def test_sign_in_and_sign_out(customer):
    client, response = sign_in(email="JANE@example.com")
    assert response.status_code == 200 and response.json()["full_name"] == "Jane Tan"
    assert client.get("/customer/me").status_code == 200
    assert post(client, "sign-out").status_code == 204
    assert client.get("/customer/me").status_code == 401
    assert CustomerSession.objects.filter(ended_at__isnull=True).count() == 1  # registration's


def test_keep_me_signed_in_sets_a_lasting_cookie(customer):
    response = post(APIClient(), "sign-in",
                    {"email": EMAIL, "password": PASSWORD, "remember": True})
    assert int(response.cookies[service.COOKIE]["max-age"]) == 12 * 3600


def test_wrong_password_and_unknown_email_get_the_same_reply(customer):
    _, wrong = sign_in(password="not the password!")
    _, unknown = sign_in(email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"] == {**unknown.json()["error"],
                                     "request_id": wrong.json()["error"]["request_id"]}
    assert "Email or password is incorrect" in wrong.json()["error"]["message"]


def test_fifth_wrong_password_locks_sign_in_for_15_minutes(customer):
    for _ in range(4):
        assert sign_in(password="wrong password 1")[1].status_code == 401
    locked = sign_in(password="wrong password 1")[1]
    # The fifth failure locks the account but answers like any wrong password (SEC-07).
    assert locked.status_code == 401 and locked.json()["error"]["code"] == "invalid_credentials"
    assert CustomerAccount.objects.get(pk=customer.pk).is_locked()
    # The right password does not get in while locked, and the reply matches an unknown email.
    right = sign_in()[1]
    _, unknown = sign_in(email="nobody@example.com")
    assert right.status_code == 401
    assert right.json()["error"]["message"] == unknown.json()["error"]["message"]
    CustomerAccount.objects.update(locked_until=timezone.now() - timedelta(seconds=1))
    assert sign_in()[1].status_code == 200
    customer.refresh_from_db()
    assert customer.failed_attempts == 0
    assert AuditEvent.objects.filter(action="customer.locked").count() == 1


def test_success_resets_the_failure_count(customer):
    for _ in range(4):
        sign_in(password="wrong password 1")
    assert sign_in()[1].status_code == 200
    for _ in range(4):
        sign_in(password="wrong password 1")
    assert sign_in()[1].status_code == 200


# --- sessions --------------------------------------------------------------------------

def test_session_ends_after_15_idle_minutes(customer):
    client, _ = sign_in()
    CustomerSession.objects.update(last_seen_at=timezone.now() - timedelta(minutes=14))
    assert client.get("/customer/me").status_code == 200  # activity keeps it alive
    CustomerSession.objects.update(last_seen_at=timezone.now() - timedelta(minutes=15))
    response = client.get("/customer/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "sign_in_required"


def test_session_ends_after_the_absolute_limit(customer):
    client, _ = sign_in()
    CustomerSession.objects.update(expires_at=timezone.now())
    assert client.get("/customer/me").status_code == 401


def test_sign_out_everywhere_ends_every_session(customer):
    phone, _ = sign_in()
    laptop, _ = sign_in()
    assert post(laptop, "sign-out-everywhere").status_code == 204
    assert phone.get("/customer/me").status_code == 401
    assert laptop.get("/customer/me").status_code == 401


def test_a_forged_cookie_is_refused(customer):
    client = APIClient()
    client.cookies[service.COOKIE] = "x" * 43
    assert client.get("/customer/me").status_code == 401


# --- password change and reset (FR-ACC-07, FR-ACC-08) ----------------------------------

def test_change_password_keeps_this_browser_and_ends_the_others(customer):
    here, _ = sign_in()
    there, _ = sign_in()
    wrong = post(here, "password", {"current_password": "nope nope nope", "password": NEW_PASSWORD})
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "current_password_incorrect"
    response = post(here, "password", {"current_password": PASSWORD, "password": NEW_PASSWORD})
    assert response.status_code == 200
    assert here.get("/customer/me").status_code == 200
    assert there.get("/customer/me").status_code == 401
    assert sign_in(password=NEW_PASSWORD)[1].status_code == 200
    assert OutboundEmail.objects.filter(kind="account_notice", to=EMAIL).exists()


def reset_token():
    send_due()
    message = [m for m in mail.outbox if m.to == [EMAIL] and "reset" in m.subject][-1]
    match = re.search(r"/account/reset#token=([\w-]+)", message.body)
    assert match, message.body
    return match.group(1)


def test_reset_same_reply_whether_or_not_registered(customer):
    client = APIClient()
    known = post(client, "password-reset/request", {"email": EMAIL})
    unknown = post(client, "password-reset/request", {"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert OutboundEmail.objects.filter(kind="password_reset").count() == 1


def test_reset_link_works_once_and_ends_every_session(customer):
    signed_in, _ = sign_in()
    client = APIClient()
    post(client, "password-reset/request", {"email": EMAIL})
    token = reset_token()
    assert post(client, "password-reset/check", {"token": token}).json() == {"email": EMAIL}
    weak = post(client, "password-reset/confirm", {"token": token, "password": "short"})
    assert weak.status_code == 400  # the link still works after a refused password
    done = post(client, "password-reset/confirm", {"token": token, "password": NEW_PASSWORD})
    assert done.status_code == 200
    again = post(client, "password-reset/confirm", {"token": token, "password": NEW_PASSWORD})
    assert again.status_code == 400 and again.json()["error"]["code"] == "link_invalid"
    assert signed_in.get("/customer/me").status_code == 401
    assert sign_in()[1].status_code == 401
    assert sign_in(password=NEW_PASSWORD)[1].status_code == 200


def test_reset_link_expires_after_30_minutes(customer):
    client = APIClient()
    post(client, "password-reset/request", {"email": EMAIL})
    token = reset_token()
    AccountToken.objects.update(expires_at=timezone.now())
    response = post(client, "password-reset/confirm", {"token": token, "password": NEW_PASSWORD})
    assert response.status_code == 400 and response.json()["error"]["code"] == "link_invalid"


def test_reset_clears_the_lockout(customer):
    for _ in range(5):
        sign_in(password="wrong password 1")
    client = APIClient()
    post(client, "password-reset/request", {"email": EMAIL})
    post(client, "password-reset/confirm", {"token": reset_token(), "password": NEW_PASSWORD})
    assert sign_in(password=NEW_PASSWORD)[1].status_code == 200


def test_reset_requests_are_limited_per_account(customer):
    client = APIClient()
    for _ in range(5):
        assert post(client, "password-reset/request", {"email": EMAIL}).status_code == 202
    assert AccountToken.objects.filter(customer=customer).count() == 3


def test_staff_and_customer_reset_links_do_not_cross(customer, shop):
    """A customer's link is refused by the staff reset and the other way round."""
    from apps.accounts import tokens
    from conftest import make_staff_user

    staff = make_staff_user("ops@demoshop.sg", "merchant_operator", merchant=shop.merchant)
    staff_token = tokens.issue(staff.user, AccountToken.Purpose.PASSWORD_RESET,
                               timedelta(minutes=30))
    customer_token = tokens.issue(customer, AccountToken.Purpose.PASSWORD_RESET,
                                  timedelta(minutes=30))
    client = APIClient()
    assert post(client, "password-reset/check",
                {"token": staff_token}).json()["error"]["code"] == "link_invalid"
    from apps.accounts import reset
    from apps.common.errors import ApiError
    with pytest.raises(ApiError):
        reset.check_link(customer_token)


# --- payment history (FR-ACC-04, C11) --------------------------------------------------

def test_payment_made_while_signed_in_is_in_the_history(customer, shop, fake_sim):
    browser, _ = sign_in()
    payment = pay(shop, browser)
    assert payment.status == "authorised" and payment.customer_id == customer.pk
    history = browser.get("/customer/payments").json()
    assert history["has_more"] is False
    (row,) = history["data"]
    assert row["reference"] == payment.reference
    assert row["merchant_name"] == shop.merchant.name
    assert row["amount"] == payment.amount and row["status_label"] == "Paid"
    detail = browser.get(f"/customer/payments/{payment.reference.lower()}").json()
    assert detail["card"]["last4"] == "4242"
    assert detail["order_reference"] == payment.order_reference
    assert detail["timeline"][0]["label"] == "Payment started"


def test_signed_in_customer_downloads_a_pdf_receipt(customer, shop, fake_sim):
    browser, _ = sign_in()
    payment = pay(shop, browser)
    r = browser.get(f"/customer/payments/{payment.reference}/receipt.pdf")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert payment.reference in r.content.decode("latin-1")
    # Signed out, or another customer: no receipt, and no hint that the payment exists.
    assert APIClient().get(f"/customer/payments/{payment.reference}/receipt.pdf") \
        .status_code == 401
    other, _ = register(email="sam@example.com")
    assert other.get(f"/customer/payments/{payment.reference}/receipt.pdf").status_code == 404


def test_guest_payments_and_other_customers_payments_are_never_shown(customer, shop, fake_sim):
    guest_payment = pay(shop, APIClient())
    assert guest_payment.customer_id is None
    other, response = register(email="sam@example.com")
    others_payment = pay(shop, other)
    jane, _ = sign_in()
    assert jane.get("/customer/payments").json()["data"] == []
    for reference in (guest_payment.reference, others_payment.reference):
        response = jane.get(f"/customer/payments/{reference}")
        assert response.status_code == 404
    assert len(other.get("/customer/payments").json()["data"]) == 1


def test_history_needs_a_session(customer):
    assert APIClient().get("/customer/payments").status_code == 401


def test_a_signed_out_payment_does_not_join_the_history(customer, shop, fake_sim):
    browser, _ = sign_in()
    post(browser, "sign-out")
    payment = pay(shop, browser)
    assert payment.customer_id is None


def test_declined_payment_is_listed_as_not_charged(customer, shop, fake_sim):
    browser, _ = sign_in()
    pay(shop, browser, "4000000000000002")
    (row,) = browser.get("/customer/payments").json()["data"]
    assert row["status_label"] == "Not charged"


# --- idle warning, consent, personal data (FR-ACC-10 to FR-ACC-13) ------------------------

def test_me_tells_the_page_when_to_warn(customer):
    client, _ = sign_in()
    body = client.get("/customer/me").json()
    assert body["idle_warning_minutes"] == 13 and body["idle_minutes"] == 15


def test_registration_records_the_privacy_notice_agreed_to(customer):
    assert customer.privacy_notice_version == "2026-11-16"
    assert customer.privacy_consent_at is not None


def test_checkout_needs_consent_to_the_privacy_notice(shop, fake_sim):
    from conftest import valid_body

    payment = Payment.objects.get(public_id=shop.create_payment(valid_body()).json()["id"])
    base = f"/checkout/{payment.checkout_session_id}"
    card = {"number": "4242424242424242", "expiry_month": 12, "expiry_year": 2030, "cvc": "123"}
    refused = APIClient().post(f"{base}/card", card, format="json")
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "privacy_consent_required"
    payment.refresh_from_db()
    assert payment.card_token == ""  # nothing collected
    ok = APIClient().post(f"{base}/card", {**card, "privacy_consent": True}, format="json")
    assert ok.status_code == 200
    payment.refresh_from_db()
    assert payment.privacy_notice_version == "2026-11-16"


def test_checkout_does_not_depend_on_the_sign_in(customer, shop, fake_sim):
    """FR-ACC-11: the sign-in timing out mid-checkout never stops or charges the payment;
    the payment just does not join the history."""
    from conftest import valid_body

    browser, _ = sign_in()
    payment = Payment.objects.get(public_id=shop.create_payment(valid_body()).json()["id"])
    base = f"/checkout/{payment.checkout_session_id}"
    card = {"number": "4242424242424242", "expiry_month": 12, "expiry_year": 2030,
            "cvc": "123", "privacy_consent": True}
    assert browser.post(f"{base}/card", card, format="json").status_code == 200
    CustomerSession.objects.update(last_seen_at=timezone.now() - timedelta(minutes=20))
    assert browser.post(f"{base}/submit", {}, format="json").status_code == 200
    payment.refresh_from_db()
    assert payment.status == "authorised" and payment.customer_id is None


def test_customer_sees_their_personal_data(customer):
    client, _ = sign_in()
    body = client.get("/customer/profile").json()
    assert body["full_name"] == "Jane Tan" and body["email"] == EMAIL
    assert body["privacy_notice_version"] == "2026-11-16"
    assert body["payments"] == 0 and body["active_sessions"] == 2
    assert APIClient().get("/customer/profile").status_code == 401


def test_correcting_details_needs_the_current_password(customer):
    client, _ = sign_in()
    wrong = post(client, "profile", {"current_password": "not it at all", "full_name": "J Tan"})
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "current_password_incorrect"
    customer.refresh_from_db()
    assert customer.full_name == "Jane Tan"


def test_correct_name_and_email(customer):
    client, _ = sign_in()
    response = post(client, "profile", {"current_password": PASSWORD, "full_name": " Jane  Lim ",
                                        "email": "Jane.Lim@Example.com"})
    assert response.status_code == 200
    assert response.json()["full_name"] == "Jane Lim"
    assert response.json()["email"] == "jane.lim@example.com"
    notices = OutboundEmail.objects.filter(kind="account_notice")
    assert set(notices.values_list("to", flat=True)) == {EMAIL, "jane.lim@example.com"}
    assert sign_in(email="jane.lim@example.com")[1].status_code == 200
    assert sign_in()[1].status_code == 401
    assert AuditEvent.objects.filter(action="customer.details_corrected").exists()


def test_cannot_take_another_customers_email(customer):
    register(email="sam@example.com")
    client, _ = sign_in()
    response = post(client, "profile", {"current_password": PASSWORD, "email": "SAM@example.com"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "email_taken"


def test_email_change_withdraws_reset_links(customer):
    client = APIClient()
    post(client, "password-reset/request", {"email": EMAIL})
    token = reset_token()
    signed_in, _ = sign_in()
    post(signed_in, "profile", {"current_password": PASSWORD, "email": "new@example.com"})
    response = post(client, "password-reset/confirm", {"token": token, "password": NEW_PASSWORD})
    assert response.status_code == 400 and response.json()["error"]["code"] == "link_invalid"


# --- spending insights (account page "Spending") -------------------------------------------

def _capture(shop, payment, amount=None):
    import uuid

    body = {} if amount is None else {"amount": amount}
    r = shop.post(f"/v1/payments/{payment.public_id}/capture", body, format="json",
                  headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200, r.json()
    payment.refresh_from_db()
    return payment


def _refund(shop, payment, amount):
    import uuid

    r = shop.post(f"/v1/payments/{payment.public_id}/refunds", {"amount": amount},
                  format="json", headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.json()


def _month(data, key):
    return next(m for m in data["by_month"] if m["month"] == key)


def test_insights_need_a_session(customer):
    assert APIClient().get("/customer/insights").status_code == 401


def test_insights_count_charged_payments_net_of_completed_refunds(customer, shop, other_shop,
                                                                   fake_sim):
    from apps.refunds.models import Refund

    browser, _ = sign_in()
    first = _capture(shop, pay(shop, browser))
    second = _capture(other_shop, pay(other_shop, browser))
    _refund(shop, first, 1500)
    Refund.objects.filter(payment=first).update(status=Refund.Status.COMPLETED)
    _refund(other_shop, second, 500)
    # Not completed yet (still with the bank): counted as spent.
    Refund.objects.filter(payment=second).update(status=Refund.Status.RESERVED)
    held = pay(shop, browser)  # authorised only: held, not spent
    pay(shop, browser, "4000000000000002")  # declined: never counted

    r = browser.get("/customer/insights")
    assert r.status_code == 200
    data = r.json()
    total = first.captured_amount + second.captured_amount
    assert data["totals"] == {
        "spent": total, "refunded": 1500, "net": total - 1500, "payments": 2, "merchants": 2,
        "on_hold": held.amount, "on_hold_payments": 1}
    assert len(data["by_month"]) == 12 and data["time_zone"] == "Asia/Singapore"
    this_month = timezone.localtime(timezone.now(), service_zone()).strftime("%Y-%m")
    assert data["to"] == this_month
    assert _month(data, this_month) == {"month": this_month, "spent": total, "refunded": 1500,
                                        "net": total - 1500, "payments": 2}
    assert sum(m["net"] for m in data["by_month"]) == data["totals"]["net"]
    by_name = {m["merchant_name"]: m for m in data["by_merchant"]}
    assert by_name[shop.merchant.name]["net"] == first.captured_amount - 1500
    assert by_name[other_shop.merchant.name]["net"] == second.captured_amount
    # Nothing about the card, the screening or the payment references leaves the gateway.
    text = r.content.decode()
    assert "4242" not in text and "last4" not in text and first.reference not in text


def service_zone():
    from apps.customers.insights import _zone
    return _zone()


def test_insights_put_payments_in_their_singapore_month_and_skip_old_ones(customer, shop,
                                                                           fake_sim):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from apps.customers.insights import insights

    browser, _ = sign_in()
    sgt = ZoneInfo("Asia/Singapore")
    late_night = _capture(shop, pay(shop, browser))  # 31 Oct 23:30 SGT is 15:30 UTC
    Payment.objects.filter(pk=late_night.pk).update(
        created_at=datetime(2026, 10, 31, 23, 30, tzinfo=sgt))
    too_old = _capture(shop, pay(shop, browser))
    Payment.objects.filter(pk=too_old.pk).update(created_at=datetime(2025, 11, 30, tzinfo=sgt))

    data = insights(customer, now=datetime(2026, 11, 18, 12, tzinfo=sgt))
    assert data["from"] == "2025-12" and data["to"] == "2026-11"
    assert _month(data, "2026-10")["net"] == late_night.captured_amount
    assert _month(data, "2026-11")["net"] == 0
    assert data["totals"]["payments"] == 1  # the payment from Nov 2025 is outside the window


def test_insights_show_only_the_customers_own_payments(customer, shop, fake_sim):
    _capture(shop, pay(shop, APIClient()))  # a guest payment
    other, _ = register(email="sam@example.com")
    _capture(shop, pay(shop, other))
    jane, _ = sign_in()
    data = jane.get("/customer/insights").json()
    assert data["totals"]["payments"] == 0 and data["by_merchant"] == []
    assert all(m["net"] == 0 for m in data["by_month"])
    assert other.get("/customer/insights").json()["totals"]["payments"] == 1


def test_insights_add_up_small_merchants_as_other(customer, make_merchant, fake_sim):
    from apps.risk.models import FraudRule

    FraudRule.objects.update(enabled=False)  # seven payments with one card trip the burst rule
    browser, _ = sign_in()
    for i in range(7):
        shop = make_merchant(name=f"Shop {i}")
        _capture(shop, pay(shop, browser))
    data = browser.get("/customer/insights").json()
    names = [m["merchant_name"] for m in data["by_merchant"]]
    assert len(names) == 6 and names[-1] == "Other merchants"
    other = data["by_merchant"][-1]
    assert other["merchant_count"] == 2 and other["payments"] == 2
    assert sum(m["net"] for m in data["by_merchant"]) == data["totals"]["net"]
    assert data["totals"]["merchants"] == 7
