import pytest
from django.db import transaction

from apps.events.models import EventType, OutboxEvent
from apps.events.outbox import record_payment_event
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db


def test_event_is_written_with_the_next_sequence_and_a_snapshot(shop):
    payment_id = shop.create_payment().json()["id"]
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(public_id=payment_id)
        payment.status = "screening"
        payment.save()
        payment.status = "processing"
        event = record_payment_event(payment, EventType.PAYMENT_PROCESSING)
    event.refresh_from_db()
    assert event.sequence == 2 == Payment.objects.get().sequence
    assert event.payload["id"] == event.public_id
    assert event.payload["sequence"] == 2
    assert event.payload["data"]["object"]["status"] == "processing"
    assert event.status == OutboxEvent.Status.PENDING


@pytest.mark.django_db(transaction=True)
def test_event_outside_a_transaction_is_refused(shop):
    payment = Payment.objects.get(public_id=shop.create_payment().json()["id"])
    with pytest.raises(RuntimeError):
        record_payment_event(payment, EventType.PAYMENT_PROCESSING)
