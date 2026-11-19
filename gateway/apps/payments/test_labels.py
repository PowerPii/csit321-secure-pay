"""One customer vocabulary for every payment state (apps.payments.labels)."""
from apps.payments.labels import customer_label
from apps.payments.states import PaymentStatus


def test_every_status_has_a_customer_label_and_the_api_enum_is_unchanged():
    assert {s.value for s in PaymentStatus} == {
        "created", "screening", "verification_required", "processing", "authorised",
        "captured", "declined", "blocked", "unresolved", "cancelled", "expired"}
    labels = {s.value: customer_label(s) for s in PaymentStatus}
    assert labels == {
        "created": "In progress", "screening": "In progress",
        "verification_required": "In progress", "processing": "In progress",
        "authorised": "Paid", "captured": "Paid",
        "declined": "Not charged", "blocked": "Not charged",
        "cancelled": "Not charged", "expired": "Not charged",
        "unresolved": "Being checked - do not pay again",
    }


def test_a_lost_bank_reply_never_reads_as_failed_or_invites_a_second_payment():
    label = customer_label("unresolved")
    assert "do not pay again" in label
    assert "Not charged" not in label


def test_refunds():
    assert customer_label("captured", refunded=500, captured=1000) == "Partly refunded"
    assert customer_label("captured", refunded=1000, captured=1000) == "Refunded"
