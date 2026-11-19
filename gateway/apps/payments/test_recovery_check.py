"""manage.py recovery_check: after a restore or rollback, recorded payments agree with the simulator."""
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.payments.models import Operation, Payment
from apps.vault.models import StoredCard
from conftest import valid_body

pytestmark = pytest.mark.django_db(databases=["default", "vault"])
CARD = {"expiry_month": 12, "expiry_year": 2030, "cvc": "123", "privacy_consent": True}


def pay(shop, number="4242424242424242"):
    payment = Payment.objects.get(public_id=shop.create_payment(valid_body()).json()["id"])
    browser = APIClient()
    base = f"/checkout/{payment.checkout_session_id}"
    assert browser.post(f"{base}/card", {"number": number, **CARD}, format="json").status_code == 200
    assert browser.post(f"{base}/submit", {}, format="json").status_code == 200
    payment.refresh_from_db()
    return payment


def test_agreeing_payments_pass(shop, fake_sim, capsys):
    paid = pay(shop)
    declined = pay(shop, "4000000000000002")
    assert (paid.status, declined.status) == ("authorised", "declined")
    call_command("recovery_check")
    out = capsys.readouterr().out
    assert "payments: 2 of 2 agree with the simulator" in out
    assert "recovery check passed" in out


def test_a_payment_the_simulator_does_not_know_fails(shop, fake_sim, capsys):
    paid = pay(shop)
    fake_sim.records.clear()  # e.g. the simulator restored from an older backup than the gateway
    with pytest.raises(CommandError):
        call_command("recovery_check", "--payment", paid.reference)
    assert "simulator says" in capsys.readouterr().out


def test_unknown_payment_and_old_vault_card_fail(shop, fake_sim, capsys):
    payment = Payment.objects.get(public_id=shop.create_payment(valid_body()).json()["id"])
    browser = APIClient()
    browser.post(f"/checkout/{payment.checkout_session_id}/card",
                 {"number": "4242424242424242", **CARD}, format="json")
    StoredCard.objects.update(expires_at=timezone.now() - timedelta(hours=1))
    with pytest.raises(CommandError):
        call_command("recovery_check", "--payment", "SP-NONE-NONE")
    out = capsys.readouterr().out
    assert "SP-NONE-NONE: not found" in out and "past expiry" in out


def test_old_open_operation_is_reported(shop, fake_sim, capsys):
    paid = pay(shop)
    op = Operation.objects.create(payment=paid, type="capture", status="unresolved", amount=paid.amount)
    Operation.objects.filter(pk=op.pk).update(created_at=timezone.now() - timedelta(minutes=45))
    call_command("recovery_check")
    assert "WARN  operations: 1 open, the oldest 45 min old" in capsys.readouterr().out
