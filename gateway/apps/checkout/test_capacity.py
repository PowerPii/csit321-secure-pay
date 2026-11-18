"""Checkout capacity fixes from the profile after the Codex release review (18 Nov 2026):
payments of one shop do not queue behind each other, and the simulator client is reused."""
import threading
import time

import pytest
from django.db import connection, connections, transaction
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.checkout.tests import pay
from apps.payments import processor
from apps.payments.models import Payment


@pytest.fixture
def browser():
    return APIClient()


@pytest.fixture
def two_payments(shop):
    from conftest import valid_body

    ids = []
    for _ in range(2):
        r = shop.create_payment(valid_body())
        assert r.status_code == 201, r.content
        ids.append(r.json()["id"])
    return [Payment.objects.get(public_id=i) for i in ids]


@pytest.mark.django_db(databases=["default", "vault"])
def test_checkout_locks_the_payment_row_but_never_the_shop(browser, two_payments, fake_sim):
    with CaptureQueriesContext(connection) as queries:
        assert pay(browser, two_payments[0]).status_code == 200
    locks = [q["sql"] for q in queries if "FOR UPDATE" in q["sql"]]
    assert locks, "checkout should lock the payment row"
    for sql in locks:
        clause = sql[sql.index("FOR UPDATE"):]
        assert "merchants_merchant" not in clause, clause


@pytest.mark.django_db(transaction=True, databases=["default", "vault"])
def test_a_payment_being_screened_does_not_hold_up_another_of_the_same_shop(browser,
                                                                            two_payments,
                                                                            fake_sim):
    first, second = two_payments
    locked, release = threading.Event(), threading.Event()

    def hold_first_payment():
        # What submit() holds while it screens the first payment.
        try:
            with transaction.atomic():
                Payment.objects.select_for_update(of=("self",)).select_related(
                    "merchant").get(pk=first.pk)
                locked.set()
                release.wait(10)
        finally:
            connections.close_all()

    holder = threading.Thread(target=hold_first_payment)
    holder.start()
    try:
        assert locked.wait(5)
        started = time.monotonic()
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '3s'")
        r = pay(browser, second)
        took = time.monotonic() - started
    finally:
        release.set()
        holder.join()
    assert r.status_code == 200, r.content
    assert r.json()["status"] == "authorised"
    assert took < 2, f"the second payment waited {took:.1f} s for the first"


def test_the_simulator_client_is_reused_until_its_settings_change(settings):
    first = processor._client()
    assert processor._client() is first
    settings.SIMULATOR_URL = "http://simulator.example:9999"
    other = processor._client()
    assert other is not first and str(other.base_url).startswith("http://simulator.example")
