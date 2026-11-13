"""Write an outbox event in the caller's transaction (CONTRIBUTING rule 3)."""
from django.db import transaction
from django.utils import timezone

from apps.common.timefmt import rfc3339
from apps.events.models import EventType, OutboxEvent
from apps.payments.models import Payment
from apps.payments.serializers import payment_to_dict


def record_payment_event(payment: Payment, event_type: EventType) -> OutboxEvent:
    """Bump the payment's sequence and write the matching event, atomically with the caller.

    Call it after changing the payment's fields and with the payment row locked
    (`select_for_update`). It saves the payment, so the snapshot and the row agree.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("record_payment_event must run inside the state change's transaction")
    payment.sequence += 1
    payment.save()
    now = timezone.now()
    event = OutboxEvent(
        merchant_id=payment.merchant_id,
        payment=payment,
        type=event_type,
        sequence=payment.sequence,
        created_at=now,
        next_attempt_at=now,
        payload={},
    )
    event.save()  # assigns public_id
    event.payload = {
        "id": event.public_id,
        "object": "event",
        "type": str(event_type),
        "created_at": rfc3339(now),
        "payment_id": payment.public_id,
        "sequence": payment.sequence,
        "data": {"object": payment_to_dict(payment)},
    }
    event.save(update_fields=["payload"])
    return event
