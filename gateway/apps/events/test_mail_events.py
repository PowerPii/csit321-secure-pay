"""Delivery reports from the mail provider (Resend webhook, apps.events.mail_events).

Only correctly signed, fresh reports are used; each moves an email forward (accepted ->
delivered, or bounced), never back; repeats change nothing; and the endpoint is off until
its secret is set.
"""
import base64
import json
import time

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.events import emails, mail_events
from apps.events.models import OutboundEmail

SECRET = "whsec_" + base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
URL = "/webhooks/resend"


def _sent_email(to="fifa@gmail.com"):
    email = emails.queue(OutboundEmail.Kind.RECEIPT, None, to, "Your SecurePay receipt", "Hi\n")
    OutboundEmail.objects.filter(pk=email.pk).update(
        status=OutboundEmail.Status.SENT, route=OutboundEmail.Route.PROVIDER,
        sent_at=timezone.now(), attempt_count=1, body_encrypted="")
    email.refresh_from_db()
    return email


def _report(kind, email, **data):
    return {"type": kind, "created_at": timezone.now().isoformat(),
            "data": {"email_id": "56761188-7520-42d8-8898-ff6fc54ce618",
                     "message_id": f"<{email.public_id}@securepaysg.me>",
                     "to": [email.to], "subject": email.subject,
                     "created_at": timezone.now().isoformat(), **data}}


def _post(client, report, secret=SECRET, msg_id="msg_1", ts=None, signature=None):
    body = json.dumps(report).encode()
    ts = int(time.time()) if ts is None else ts
    sig = signature if signature is not None else mail_events.sign(body, msg_id, ts, secret)
    return client.post(URL, body, content_type="application/json",
                       HTTP_SVIX_ID=msg_id, HTTP_SVIX_TIMESTAMP=str(ts), HTTP_SVIX_SIGNATURE=sig)


def test_signature_check():
    body, now = b'{"type":"email.delivered"}', 1_700_000_000
    good = mail_events.sign(body, "msg_1", now, SECRET)
    assert mail_events.verify(body, "msg_1", str(now), good, SECRET, now=now)
    # Rotation: several signatures, one of them good.
    assert mail_events.verify(body, "msg_1", str(now), f"v1,AAAA {good}", SECRET, now=now)
    assert not mail_events.verify(body + b" ", "msg_1", str(now), good, SECRET, now=now)
    assert not mail_events.verify(body, "msg_2", str(now), good, SECRET, now=now)
    assert not mail_events.verify(body, "msg_1", str(now), good, SECRET, now=now + 301)
    assert not mail_events.verify(body, "msg_1", str(now), good.replace("v1", "v2"), SECRET,
                                  now=now)
    assert not mail_events.verify(body, "msg_1", "soon", good, SECRET, now=now)
    assert not mail_events.verify(body, "msg_1", str(now), good, "whsec_not base64!", now=now)
    assert not mail_events.verify(body, "msg_1", str(now), good, "", now=now)


@pytest.mark.django_db
def test_off_until_the_secret_is_set(client):
    email = _sent_email()
    with override_settings(RESEND_WEBHOOK_SECRET=""):
        assert _post(client, _report("email.delivered", email)).status_code == 404


@pytest.mark.django_db
@override_settings(RESEND_WEBHOOK_SECRET=SECRET)
def test_bad_or_stale_signatures_change_nothing(client):
    email = _sent_email()
    report = _report("email.delivered", email)
    assert _post(client, report, signature="v1,bm9wZQ==").status_code == 400
    assert _post(client, report, ts=int(time.time()) - 600).status_code == 400
    other = "whsec_" + base64.b64encode(b"another secret entirely....").decode()
    assert _post(client, report, secret=other).status_code == 400
    email.refresh_from_db()
    assert email.status == "sent"


@pytest.mark.django_db
@override_settings(RESEND_WEBHOOK_SECRET=SECRET)
def test_delivered_then_bounced_never_back(client):
    from apps.internal.payment_details import email_outcome

    email = _sent_email()
    reply = _post(client, _report("email.delivered", email))
    assert (reply.status_code, reply.json()["result"]) == (200, "applied")
    email.refresh_from_db()
    assert email.status == "delivered" and email.delivery_reported_at is not None
    assert email_outcome(email) == "Delivered to the recipient's mail server (1 attempt)"
    # A repeat copy is accepted and changes nothing.
    assert _post(client, _report("email.delivered", email)).json()["result"] == "unchanged"

    bounce = {"type": "Permanent", "subType": "Suppressed",
              "message": "fifa@gmail.com is on the suppression list"}
    assert _post(client, _report("email.bounced", email, bounce=bounce)).json()["result"] \
        == "applied"
    email.refresh_from_db()
    assert (email.status, email.bounce_type) == ("bounced", "Permanent/Suppressed")
    assert email_outcome(email) == ("Bounced: the recipient's mail server refused it "
                                    "(Permanent/Suppressed)")
    # A late "delivered" cannot undo the bounce.
    assert _post(client, _report("email.delivered", email)).json()["result"] == "unchanged"
    email.refresh_from_db()
    assert email.status == "bounced"


@pytest.mark.django_db
@override_settings(RESEND_WEBHOOK_SECRET=SECRET)
def test_provider_failure_and_untracked_and_unknown_reports(client):
    from apps.internal.payment_details import email_outcome

    email = _sent_email()
    assert _post(client, _report("email.opened", email)).json()["result"] == "ignored"
    stranger = _report("email.delivered", email, message_id="<abc@elsewhere.example>",
                       to=["someone@else.test"])
    assert _post(client, stranger).json()["result"] == "unmatched"
    assert _post(client, _report("email.failed", email)).json()["result"] == "applied"
    email.refresh_from_db()
    assert email.status == "failed"
    assert email_outcome(email) == "Not delivered: the mail provider could not send it"


@pytest.mark.django_db
@override_settings(RESEND_WEBHOOK_SECRET=SECRET)
def test_report_for_an_email_whose_reply_was_lost_stops_the_retry(client):
    email = _sent_email()
    OutboundEmail.objects.filter(pk=email.pk).update(
        status=OutboundEmail.Status.PENDING, claim_token="abc", body_encrypted="x")
    assert _post(client, _report("email.delivered", email)).json()["result"] == "applied"
    email.refresh_from_db()
    assert (email.status, email.body_encrypted, email.claim_token) == ("delivered", "", "")


@pytest.mark.django_db
@override_settings(RESEND_WEBHOOK_SECRET=SECRET)
def test_fallback_match_without_message_id_needs_exactly_one_email(client):
    email = _sent_email()
    report = _report("email.delivered", email, message_id=None)
    assert _post(client, report).json()["result"] == "applied"
    _sent_email()  # a second receipt to the same person: no longer unambiguous
    other = _sent_email()
    report = _report("email.delivered", other, message_id=None)
    assert _post(client, report).json()["result"] == "unmatched"


def test_malformed_json_is_refused(client, settings):
    settings.RESEND_WEBHOOK_SECRET = SECRET
    body, ts = b"[1, 2", int(time.time())
    reply = client.post(URL, body, content_type="application/json", HTTP_SVIX_ID="m",
                        HTTP_SVIX_TIMESTAMP=str(ts),
                        HTTP_SVIX_SIGNATURE=mail_events.sign(body, "m", ts, SECRET))
    assert reply.status_code == 400
