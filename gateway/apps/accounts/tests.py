"""Staff two-step sign-in and lockout (FR-ACC-14, FR-ACC-15, demo: D1 and D2)."""
from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import StaffAccount
from apps.audit.models import AuditEvent
from conftest import current_totp, make_staff_user

pytestmark = pytest.mark.django_db(databases=["default", "vault"])

PASSWORD = "correct horse battery staple"


@pytest.fixture
def analyst():
    return make_staff_user("analyst@securepay.sg", "fraud_analyst", password=PASSWORD)


def csrf_client():
    client = Client(enforce_csrf_checks=True)
    client.get("/internal/me")  # 401, but sets the CSRF cookie
    client.defaults["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
    return client


def login(client, email="analyst@securepay.sg", password=PASSWORD):
    return client.post("/internal/auth/login", {"email": email, "password": password},
                       content_type="application/json")


def totp(client, code):
    return client.post("/internal/auth/totp", {"code": code}, content_type="application/json")


def test_me_needs_both_steps(analyst):
    client = csrf_client()
    assert client.get("/internal/me").status_code == 401
    r = login(client)
    assert r.status_code == 200 and r.json()["setup"] is None
    # Password alone is not a sign-in.
    assert client.get("/internal/me").status_code == 401
    assert client.get("/internal/payments").status_code == 401
    r = totp(client, current_totp(analyst))
    assert r.status_code == 200, r.content
    assert r.json()["role"] == "fraud_analyst"
    me = client.get("/internal/me").json()
    assert me["email"] == "analyst@securepay.sg" and me["merchant"] is None
    assert AuditEvent.objects.filter(action="staff.signed_in",
                                     actor_id=analyst.public_id).exists()


def test_sign_in_without_csrf_token_is_refused(analyst):
    client = Client(enforce_csrf_checks=True)
    r = login(client)
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"


def test_first_sign_in_sets_up_the_authenticator():
    account = make_staff_user("new@securepay.sg", "administrator", password=PASSWORD,
                              with_device=False)
    client = csrf_client()
    r = login(client, "new@securepay.sg")
    setup = r.json()["setup"]
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    assert setup["qr_svg"].startswith("data:image/svg+xml")
    assert client.get("/internal/auth/totp").json()["setup_required"] is True
    device = TOTPDevice.objects.get(user=account.user, confirmed=False)
    assert totp(client, current_totp(account, device)).status_code == 200
    device.refresh_from_db()
    assert device.confirmed
    event = AuditEvent.objects.get(action="staff.signed_in", actor_id=account.public_id)
    assert event.details == {"mfa_setup": True}


def test_wrong_password_and_unknown_email_get_the_same_reply(analyst):
    client = csrf_client()
    wrong = login(client, password="not the password")
    unknown = login(client, email="nobody@securepay.sg")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert wrong.json()["error"]["code"] == "invalid_credentials"


def test_five_failures_lock_the_account_and_email_the_holder(analyst):
    client = csrf_client()
    for _ in range(3):
        assert login(client, password="wrong password!").status_code == 401
    # Wrong TOTP codes count towards the same limit.
    assert login(client).status_code == 200
    assert totp(client, "000000").json()["error"]["code"] == "code_incorrect"
    r = totp(client, "111111")
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_locked"
    assert int(r["Retry-After"]) > 14 * 60
    # Locked: even the right password is not checked, and the password step answers like a
    # wrong password, so it does not tell whether the email is a staff account (SEC-07).
    r = login(client)
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    unknown = login(client, "nobody@securepay.sg")
    assert r.json()["error"]["message"] == unknown.json()["error"]["message"]
    analyst.refresh_from_db()
    assert analyst.is_locked()
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["analyst@securepay.sg"]
    assert AuditEvent.objects.filter(action="staff.locked", actor_id=analyst.public_id).count() \
        == 1
    assert AuditEvent.objects.filter(action="staff.sign_in_failed",
                                     actor_id=analyst.public_id).count() == 5


def test_lock_ends_after_fifteen_minutes(analyst):
    StaffAccount.objects.filter(pk=analyst.pk).update(
        locked_until=timezone.now() - timedelta(seconds=1))
    client = csrf_client()
    assert login(client).status_code == 200
    assert totp(client, current_totp(analyst)).status_code == 200
    analyst.refresh_from_db()
    assert analyst.failed_attempts == 0 and analyst.locked_until is None


def test_a_used_code_cannot_be_replayed(analyst):
    first = csrf_client()
    login(first)
    code = current_totp(analyst)
    assert totp(first, code).status_code == 200
    second = csrf_client()
    login(second)
    assert totp(second, code).status_code == 401


def test_totp_step_times_out(analyst):
    client = csrf_client()
    login(client)
    session = client.session
    session["staff_signin"]["at"] -= 6 * 60
    session.save()
    r = totp(client, current_totp(analyst))
    assert r.status_code == 401 and r.json()["error"]["code"] == "sign_in_required"


def test_logout_ends_the_session(analyst):
    client = csrf_client()
    login(client)
    totp(client, current_totp(analyst))
    # Signing in rotates the CSRF token; the dashboard reads the cookie on every request.
    client.defaults["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
    assert client.post("/internal/auth/logout").status_code == 204
    assert client.get("/internal/me").status_code == 401
    assert AuditEvent.objects.filter(action="staff.signed_out").exists()


def test_operator_must_belong_to_a_merchant():
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        make_staff_user("ops@demoshop.sg", "merchant_operator", password=PASSWORD)
