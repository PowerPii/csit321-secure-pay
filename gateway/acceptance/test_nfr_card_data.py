"""NFR-CON-02 (masking everywhere) and NFR-ENC-02 (vault holds card data only until submit).

One full test run: approved, declined, blocked, verified-by-code and lost-response payments,
a card entered and abandoned, a capture, a refund, webhooks, emails, a PDF receipt and the
dashboard exports. Then every place card data could leak is scanned.
"""
import logging
import re
from datetime import timedelta

import httpx
import pytest
from django.core import mail
from django.core.management import call_command
from django.db import connection, connections
from django.utils import timezone
from nfr_helpers import capture, card, new_payment, refund, submit
from rest_framework.test import APIClient

from apps.common.carddata import contains_card_number, looks_like_card_number
from apps.events import delivery, emails
from apps.payments import reconciliation
from apps.payments.models import Operation, Payment
from apps.vault import service as vault
from apps.vault.models import StoredCard

pytestmark = pytest.mark.django_db(databases=["default", "vault"], transaction=True)

HOOK = "https://shop.example/webhooks/securepay"
CARDS = {
    "approve": "4242424242424242",
    "decline": "4000000000000002",
    "blocklisted": "4000000000000101",
    "lost_response": "4000000000000119",
    "mastercard": "5555555555554444",
    "abandoned": "4242424242424242",
}


class Receiver:
    def __init__(self):
        self.bodies = []

    def __call__(self, request):
        self.bodies.append(request.content.decode())
        return httpx.Response(200, text="ok")


def _variants(pan):
    groups = " ".join(pan[i:i + 4] for i in range(0, len(pan), 4))
    return {pan, groups, groups.replace(" ", "-")}


# Random UUIDs (idempotency keys) and hex digests (fingerprints, signatures, hashes) are
# not card numbers, but their digit runs pass the generic scan by chance: "834686-5630-429"
# inside a UUID is 13 digits with dashes, and about 1 in 250 hex digests holds a Luhn-valid
# run. With dozens of them in the database the test failed about 1 run in 8. The exact test
# cards are still searched for in the full text first, so a real leak is always caught.
_NOT_CARD_TOKENS = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|[0-9a-fA-F]{32,}")


def _leaks(text: str) -> list[str]:
    found = [pan for number in CARDS.values() for pan in _variants(number) if pan in text]
    rest = _NOT_CARD_TOKENS.sub(" ", text)
    return found or (["a Luhn-valid card number"] if looks_like_card_number(rest) else [])


def _database_dump(alias="default") -> str:
    with connections[alias].cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")
        tables = [row[0] for row in cur.fetchall()]
        parts = []
        for table in tables:
            cur.execute(f'SELECT coalesce(string_agg(row_to_json(t)::text, \' \'), \'\') '
                        f'FROM "{table}" t')  # nosec B608 - table names from pg_tables
            parts.append(f"[{table}] " + cur.fetchone()[0])
    return "\n".join(parts)


def test_nfr_con_02_and_enc_02_no_card_number_anywhere_after_a_full_run(
        make_merchant, fake_sim, staff_client, monkeypatch, settings, caplog):
    caplog.set_level(logging.DEBUG)
    receiver = Receiver()
    monkeypatch.setattr(delivery, "TRANSPORT", httpx.MockTransport(receiver))
    settings.WEBHOOK_ALLOWED_PRIVATE_HOSTS = frozenset({"shop.example"})
    call_command("seed_risk_lists", verbosity=0)
    shop = make_merchant(webhook_url=HOOK, webhook_url_approved=True)
    operator = staff_client("merchant_operator", merchant=shop.merchant)
    analyst = staff_client("fraud_analyst")
    admin = staff_client("administrator")
    replies = []  # every API, checkout, dashboard and export response body

    def keep(response):
        replies.append(response.content.decode("latin-1"))
        return response

    # Payments with every outcome.
    paid = new_payment(shop)
    keep(submit(paid, CARDS["approve"]))
    keep(submit(new_payment(shop), CARDS["decline"]))
    keep(submit(new_payment(shop), CARDS["blocklisted"]))
    lost = new_payment(shop)
    keep(submit(lost, CARDS["lost_response"]))
    big = new_payment(shop, amount=60_000)
    browser = APIClient()
    data = keep(submit(big, CARDS["mastercard"], browser)).json()
    assert data["status"] == "verification_required", data
    code = re.search(r"verification code is (\d{6})", mail.outbox[-1].body).group(1)
    keep(browser.post(f"/checkout/{big.checkout_session_id}/verify", {"code": code},
                      format="json"))

    # Card entered, never submitted, session ends: purged by the worker job.
    abandoned = new_payment(shop)
    r = APIClient().post(f"/checkout/{abandoned.checkout_session_id}/card",
                         card(CARDS["abandoned"]), format="json")
    assert r.status_code == 200
    stored = StoredCard.objects.using("vault").get()
    for secret in (CARDS["abandoned"], '"cvc"', "123"):
        assert secret not in stored.ciphertext  # AES-256-GCM, never plaintext
    StoredCard.objects.using("vault").update(expires_at=timezone.now() - timedelta(seconds=1))
    Payment.objects.filter(pk=abandoned.pk).update(
        checkout_expires_at=timezone.now() - timedelta(seconds=1))
    assert vault.purge_expired() == 1

    # Settle the lost response, capture and refund, then send webhooks and emails.
    Operation.objects.filter(status="unresolved").update(next_check_at=timezone.now())
    reconciliation.reconcile_due()
    paid.refresh_from_db()
    capture(shop, paid)
    keep(refund(shop, paid, 1000))
    for payment in Payment.objects.all():
        keep(shop.get(f"/v1/payments/{payment.public_id}"))
        keep(shop.get(f"/v1/payments/{payment.public_id}/refunds"))
        keep(operator.get(f"/internal/payments/{payment.public_id}"))
        keep(admin.get(f"/internal/payments/{payment.public_id}"))
    while delivery.deliver_due():
        pass
    emails.send_due()
    keep(operator.get("/internal/payments"))
    keep(operator.get("/internal/overview"))
    keep(analyst.get("/internal/reviews"))
    keep(analyst.get("/internal/alerts"))
    keep(analyst.get("/internal/reports/fraud/export"))
    keep(admin.get("/internal/audit"))
    from apps.guest.receipts import receipt_pdf

    paid.refresh_from_db()
    replies.append(receipt_pdf(paid).decode("latin-1"))

    assert len(receiver.bodies) >= 5 and len(mail.outbox) >= 3 and len(replies) > 30
    places = {
        "API, checkout, dashboard and export replies": "\n".join(replies),
        "webhooks": "\n".join(receiver.bodies),
        "emails": "\n".join(m.subject + "\n" + m.body for m in mail.outbox),
        "logs": "\n".join(rec.getMessage() for rec in caplog.records),
        "gateway database": _database_dump(),
    }
    found = {place: _leaks(text) for place, text in places.items()}
    assert found == {place: [] for place in places}, found
    for body in receiver.bodies + replies[:-1]:
        if body.startswith("{"):
            import json

            assert not contains_card_number(json.loads(body))

    # NFR-ENC-02: nothing left in the vault for submitted or ended attempts.
    assert StoredCard.objects.using("vault").count() == 0
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM payments_payment WHERE card_last4 !~ '^[0-9]{4}$' "
                    "AND card_last4 <> ''")
        assert cur.fetchone()[0] == 0
