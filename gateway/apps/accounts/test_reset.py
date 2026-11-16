"""Password reset by emailed link (FR-ACC-07, FR-ACC-08, FR-ACC-09; API-CONTRACT.md section 9)."""
import re
from datetime import timedelta

import pytest
from django.contrib.sessions.models import Session
from django.core import mail
from django.test import Client
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import AccountToken, StaffAccount
from apps.audit.models import AuditEvent
from apps.events.emails import send_due
from apps.events.models import OutboundEmail
from conftest import STAFF_PASSWORD, current_totp, make_staff_user

pytestmark = pytest.mark.django_db(databases=["default", "vault"])

NEW_PASSWORD = "a brand new passphrase 42"


@pytest.fixture
def operator(shop):
    return make_staff_user("ops@demoshop.sg", "merchant_operator", merchant=shop.merchant)


def csrf_client():
    client = Client(enforce_csrf_checks=True)
    client.get("/internal/me")
    client.defaults["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
    return client


def post(client, path, body):
    return client.post(f"/internal{path}", body, content_type="application/json")


def ask(client, email):
    return post(client, "/auth/password-reset", {"email": email})


def reset_link_token(to):
    send_due()
    message = [m for m in mail.outbox if m.to == [to] and "reset your password" in m.subject][-1]
    match = re.search(r"/dashboard/reset-password#token=([\w-]+)", message.body)
    assert match, message.body
    return match.group(1)


def signed_in_client(account):
    client = Client()
    post(client, "/auth/login", {"email": account.email, "password": STAFF_PASSWORD})
    assert post(client, "/auth/totp", {"code": current_totp(account)}).status_code == 200
    return client


def test_same_reply_whether_or_not_the_email_is_registered(operator):
    client = csrf_client()
    known, unknown = ask(client, "ops@demoshop.sg"), ask(client, "nobody@example.com")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert "30 minutes" in known.json()["message"]
    # Only the registered address gets an email, through the outbox (timing does not tell).
    assert OutboundEmail.objects.filter(kind="password_reset").count() == 1
    assert len(mail.outbox) == 0
    send_due()
    assert [m.to for m in mail.outbox] == [["ops@demoshop.sg"]]
    email = OutboundEmail.objects.get(kind="password_reset")
    assert email.body_encrypted == "" and email.payment is None


def test_reset_needs_csrf_token(operator):
    r = ask(Client(enforce_csrf_checks=True), "ops@demoshop.sg")
    assert r.status_code == 403


def test_token_is_stored_only_as_a_digest(operator):
    client = csrf_client()
    ask(client, "ops@demoshop.sg")
    token = reset_link_token("ops@demoshop.sg")
    row = AccountToken.objects.get()
    assert token not in row.digest and len(row.digest) == 64
    assert abs((row.expires_at - row.created_at) - timedelta(minutes=30)) < timedelta(seconds=1)


def test_full_reset_with_totp_ends_every_session(operator):
    old_session = signed_in_client(operator)
    assert old_session.get("/internal/me").status_code == 200

    client = csrf_client()
    ask(client, "ops@demoshop.sg")
    token = reset_link_token("ops@demoshop.sg")
    check = post(client, "/auth/password-reset/check", {"token": token})
    assert check.json() == {"email": "ops@demoshop.sg", "mfa_required": True}

    # The sign-in above used this time step's code; a real reset comes later.
    TOTPDevice.objects.filter(user=operator.user).update(last_t=-1)
    # Staff confirm with their authenticator code (FR-ACC-09).
    r = post(client, "/auth/password-reset/confirm", {"token": token, "password": NEW_PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["code"] == "code_incorrect"
    r = post(client, "/auth/password-reset/confirm",
             {"token": token, "password": NEW_PASSWORD, "code": current_totp(operator)})
    assert r.status_code == 200, r.content

    # FR-ACC-08: the old session is gone, and the old password no longer works.
    assert old_session.get("/internal/me").status_code == 401
    signed_in = [s for s in Session.objects.all()
                 if s.get_decoded().get("_auth_user_id") == str(operator.user.pk)]
    assert signed_in == []
    r = post(csrf_client(), "/auth/login", {"email": "ops@demoshop.sg", "password": STAFF_PASSWORD})
    assert r.status_code == 401
    r = post(csrf_client(), "/auth/login", {"email": "ops@demoshop.sg", "password": NEW_PASSWORD})
    assert r.status_code == 200 and r.json()["setup"] is None  # MFA kept

    event = AuditEvent.objects.get(action="staff.password_reset")
    assert event.target_id == operator.public_id
    assert event.details["mfa_confirmed"] is True and event.details["sessions_ended"] >= 1
    send_due()
    assert any("password was changed" in m.subject for m in mail.outbox)


def test_link_works_once(operator):
    client = csrf_client()
    ask(client, "ops@demoshop.sg")
    token = reset_link_token("ops@demoshop.sg")
    body = {"token": token, "password": NEW_PASSWORD, "code": current_totp(operator)}
    assert post(client, "/auth/password-reset/confirm", body).status_code == 200
    r = post(client, "/auth/password-reset/confirm", {**body, "password": "another passphrase 7"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "link_invalid"
    assert post(client, "/auth/password-reset/check", {"token": token}).status_code == 400


def test_link_expires_after_30_minutes(operator):
    client = csrf_client()
    ask(client, "ops@demoshop.sg")
    token = reset_link_token("ops@demoshop.sg")
    AccountToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    r = post(client, "/auth/password-reset/check", {"token": token})
    assert r.status_code == 400 and r.json()["error"]["code"] == "link_invalid"


def test_a_new_link_withdraws_the_old_one(operator):
    client = csrf_client()
    ask(client, "ops@demoshop.sg")
    first = reset_link_token("ops@demoshop.sg")
    ask(client, "ops@demoshop.sg")
    second = reset_link_token("ops@demoshop.sg")
    assert first != second
    assert post(client, "/auth/password-reset/check", {"token": first}).status_code == 400
    assert post(client, "/auth/password-reset/check", {"token": second}).status_code == 200


def test_requests_per_account_are_limited(operator):
    client = csrf_client()
    replies = [ask(client, "ops@demoshop.sg") for _ in range(5)]
    assert {r.status_code for r in replies} == {202}
    assert OutboundEmail.objects.filter(kind="password_reset").count() == 3


def test_weak_password_is_refused_and_the_link_still_works(operator):
    client = csrf_client()
    ask(client, "ops@demoshop.sg")
    token = reset_link_token("ops@demoshop.sg")
    r = post(client, "/auth/password-reset/confirm",
             {"token": token, "password": "short", "code": current_totp(operator)})
    assert r.status_code == 400 and r.json()["error"]["code"] == "weak_password"
    assert post(client, "/auth/password-reset/check", {"token": token}).status_code == 200


def test_wrong_codes_on_the_reset_page_lock_the_account(operator):
    client = csrf_client()
    ask(client, "ops@demoshop.sg")
    token = reset_link_token("ops@demoshop.sg")
    body = {"token": token, "password": NEW_PASSWORD, "code": "000000"}
    replies = [post(client, "/auth/password-reset/confirm", body) for _ in range(5)]
    assert replies[-1].status_code == 403
    assert replies[-1].json()["error"]["code"] == "account_locked"
    assert StaffAccount.objects.get(pk=operator.pk).is_locked()
    # While locked, even the right code is not checked.
    r = post(client, "/auth/password-reset/confirm", {**body, "code": current_totp(operator)})
    assert r.status_code == 403


def test_account_without_authenticator_resets_without_a_code(shop):
    account = make_staff_user("new@securepay.sg", "administrator", with_device=False)
    client = csrf_client()
    ask(client, "new@securepay.sg")
    token = reset_link_token("new@securepay.sg")
    assert post(client, "/auth/password-reset/check",
                {"token": token}).json()["mfa_required"] is False
    r = post(client, "/auth/password-reset/confirm", {"token": token, "password": NEW_PASSWORD})
    assert r.status_code == 200
    account.user.refresh_from_db()
    assert account.user.check_password(NEW_PASSWORD)


def test_inactive_account_gets_no_link(operator):
    operator.user.is_active = False
    operator.user.save()
    ask(csrf_client(), "ops@demoshop.sg")
    assert not OutboundEmail.objects.filter(kind="password_reset").exists()


def test_garbage_tokens_are_refused(operator):
    client = csrf_client()
    for token in (None, "", "x" * 30, 12345):
        r = post(client, "/auth/password-reset/check", {"token": token})
        assert r.status_code == 400 and r.json()["error"]["code"] == "link_invalid"
