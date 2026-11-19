"""Test mail and real mail take separate routes (Codex re-audit, 19 Nov 2026).

Made-up demo recipients only ever reach the capture inbox (Mailpit); real recipients go
straight to the provider and are never copied into the shared demo inbox; with no provider on
a server they are not sent at all. Codes are never in subjects, each email keeps one message
ID across retries, retries stop once the code has expired, and a worker whose claim ran out
cannot overwrite the result.
"""
import importlib
import smtplib
from datetime import timedelta
from typing import ClassVar

import pytest
from django.core import mail
from django.core.mail import EmailMessage
from django.core.mail.backends.locmem import EmailBackend as LocmemBackend
from django.test import override_settings
from django.utils import timezone

from apps.common import branded_email, mail_routing
from apps.events import emails
from apps.events.models import OutboundEmail

PROVIDER = {"host": "smtp.provider.test", "port": 587, "username": "resend",
            "password": "re_test", "use_tls": True, "use_ssl": False}
NO_PROVIDER = {**PROVIDER, "host": ""}


@pytest.mark.parametrize("address,provider,capture_real,allow,route", [
    ("alex@example.com", PROVIDER, False, "", "capture"),
    ("ops@demoshop.sg", PROVIDER, False, "", "capture"),
    ("someone@shop.test", NO_PROVIDER, False, "", "capture"),
    ("fifa@gmail.com", PROVIDER, False, "", "provider"),
    ("fifa@gmail.com", PROVIDER, False, r"(?i)@uowmail\.edu\.au$", "suppress"),
    ("me@uowmail.edu.au", PROVIDER, False, r"(?i)@uowmail\.edu\.au$", "provider"),
    ("fifa@gmail.com", NO_PROVIDER, False, "", "suppress"),  # a server with no provider
    ("fifa@gmail.com", NO_PROVIDER, True, "", "capture"),  # a laptop or CI: nothing leaves
    ("Alex@EXAMPLE.COM", PROVIDER, False, "", "capture"),
])
def test_route_for(address, provider, capture_real, allow, route):
    with override_settings(MAIL_PROVIDER=provider, MAIL_CAPTURE_REAL=capture_real,
                           MAIL_REAL_RECIPIENTS=allow):
        assert mail_routing.route_for(address) == route


class FakeProvider(LocmemBackend):
    sent: ClassVar[list] = []

    def send_messages(self, messages):
        FakeProvider.sent.extend(messages)
        return len(messages)


@pytest.fixture
def provider(monkeypatch):
    FakeProvider.sent = []
    real = branded_email.get_connection

    def connect(backend=None, **kwargs):
        if backend == "django.core.mail.backends.smtp.EmailBackend":
            assert kwargs["host"] == PROVIDER["host"] and kwargs["use_tls"] is True
            return FakeProvider()
        return real(backend, **kwargs)

    monkeypatch.setattr(branded_email, "get_connection", connect)
    with override_settings(MAIL_PROVIDER=PROVIDER, MAIL_CAPTURE_REAL=False,
                           EMAIL_INNER_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
        yield FakeProvider.sent


def test_backend_never_copies_a_real_recipient_into_the_capture_inbox(provider):
    backend = branded_email.BrandedEmailBackend()
    sent = backend.send_messages([
        EmailMessage("Your SecurePay receipt", "Thanks.\n", None,
                     ["fifa@gmail.com", "alex@example.com"]),
    ])
    assert sent == 2
    assert [m.to for m in provider] == [["fifa@gmail.com"]]
    assert [m.to for m in mail.outbox] == [["alex@example.com"]]  # the capture inbox
    assert provider[0].alternatives  # still branded


def test_backend_drops_a_real_recipient_with_no_route(provider):
    with override_settings(MAIL_PROVIDER=NO_PROVIDER):
        backend = branded_email.BrandedEmailBackend()
        assert backend.send_messages([EmailMessage("x", "y", None, ["fifa@gmail.com"])]) == 0
    assert provider == [] and mail.outbox == []


def test_code_box_comes_from_the_body_not_the_subject():
    html = branded_email.html_for("Your SecurePay verification code",
                                  "Your SecurePay verification code is 123456\n\nEnter it.\n")
    assert "letter-spacing:8px" in html and ">123456</span>" in html


# --- the outbox ------------------------------------------------------------------------

def _queue(to="alex@example.com", **kw):
    return emails.queue(OutboundEmail.Kind.ACCOUNT_NOTICE, None, to, "SecurePay: notice",
                        "Hello\n", **kw)


@pytest.mark.django_db
def test_sent_email_records_its_route_and_a_stable_message_id(monkeypatch):
    email = _queue()
    calls = []

    def flaky(self, fail_silently=False):
        calls.append(dict(self.extra_headers))
        if len(calls) == 1:
            raise smtplib.SMTPServerDisconnected("provider went away")
        return 1

    monkeypatch.setattr(EmailMessage, "send", flaky)
    emails.send_due()
    email.refresh_from_db()
    assert (email.status, email.attempt_count, email.route) == ("pending", 1, "capture")
    assert email.last_error == "SMTPServerDisconnected"
    OutboundEmail.objects.filter(pk=email.pk).update(next_attempt_at=timezone.now())
    emails.send_due()
    email.refresh_from_db()
    assert (email.status, email.attempt_count, email.body_encrypted) == ("sent", 2, "")
    assert calls[0] == calls[1]  # the same message on both tries
    assert calls[0]["Resend-Idempotency-Key"] == email.public_id
    assert calls[0]["Message-ID"].startswith(f"<{email.public_id}@")


@pytest.mark.django_db
@override_settings(MAIL_PROVIDER=NO_PROVIDER, MAIL_CAPTURE_REAL=False)
def test_real_recipient_with_no_provider_is_suppressed_not_captured():
    email = _queue(to="fifa@gmail.com")
    emails.send_due()
    email.refresh_from_db()
    assert (email.status, email.route, email.body_encrypted) == ("suppressed", "suppress", "")
    assert mail.outbox == []


@pytest.mark.django_db
def test_permanent_refusal_is_not_retried(monkeypatch):
    email = _queue()

    def refused(self, fail_silently=False):
        raise smtplib.SMTPRecipientsRefused({"alex@example.com": (550, b"no such user")})

    monkeypatch.setattr(EmailMessage, "send", refused)
    emails.send_due()
    email.refresh_from_db()
    assert (email.status, email.attempt_count) == ("failed", 1)
    assert email.last_error == "SMTPRecipientsRefused"


@pytest.mark.django_db
def test_retries_stop_when_the_code_would_have_expired(monkeypatch):
    email = _queue(discard_after=timezone.now() + timedelta(seconds=20))  # first retry is 30 s
    monkeypatch.setattr(EmailMessage, "send",
                        lambda self, fail_silently=False: (_ for _ in ()).throw(OSError()))
    emails.send_due()
    email.refresh_from_db()
    assert (email.status, email.attempt_count, email.body_encrypted) == ("discarded", 1, "")


@pytest.mark.django_db
def test_a_lost_claim_cannot_overwrite_the_result(monkeypatch):
    email = _queue()
    pk, token = emails._claim_one()

    def slow_send(self, fail_silently=False):
        # Meanwhile the lease ran out and another worker claimed the row.
        OutboundEmail.objects.filter(pk=pk).update(claim_token="another-worker")
        return 1

    monkeypatch.setattr(EmailMessage, "send", slow_send)
    emails._send_one(pk, token)
    email.refresh_from_db()
    assert (email.status, email.attempt_count) == ("pending", 0)


@pytest.mark.django_db
def test_each_email_is_claimed_just_before_it_is_sent(monkeypatch):
    first, second = _queue(), _queue()
    seen = []

    def send(self, fail_silently=False):
        # When the first is sent, the second has not been claimed yet.
        seen.append(OutboundEmail.objects.get(pk=second.pk).claim_token)
        return 1

    monkeypatch.setattr(EmailMessage, "send", send)
    assert emails.send_due() == 2
    assert seen[0] == ""
    assert set(OutboundEmail.objects.values_list("status", flat=True)) == {"sent"}
    assert first.pk != second.pk


@pytest.mark.django_db
def test_old_code_subjects_are_scrubbed():
    from django.apps import apps

    email = _queue()
    OutboundEmail.objects.filter(pk=email.pk).update(kind="guest_status_code",
                                                     subject="123456 is your SecurePay status code")
    migration = importlib.import_module("apps.events.migrations.0008_email_routes")
    migration.scrub_code_subjects(apps, None)
    email.refresh_from_db()
    assert email.subject == "Your SecurePay status code"


@pytest.mark.django_db
def test_operator_sees_what_happened_to_an_email():
    from apps.internal.payment_details import email_outcome

    email = _queue()
    assert email_outcome(email) == "Queued"
    email.status, email.route, email.attempt_count = "sent", "provider", 1
    assert email_outcome(email) == "Accepted by the mail provider (1 attempt)"
    email.status, email.attempt_count, email.last_error = "pending", 2, "SMTPConnectError"
    assert email_outcome(email) == "Retrying (2 attempts, last error SMTPConnectError)"
    email.status = "suppressed"
    assert email_outcome(email).startswith("Not sent")
