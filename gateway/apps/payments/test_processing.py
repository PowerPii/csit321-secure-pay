"""Applying simulator answers (SIMULATOR-CONTRACT.md section 7)."""
import pytest

from apps.payments.models import Operation, Payment
from apps.payments.processing import apply_authorise_answer
from apps.payments.processor import Answer, AnswerKind
from apps.payments.states import PaymentStatus


@pytest.fixture
def processing_op(shop):
    from conftest import valid_body

    r = shop.create_payment(valid_body())
    payment = Payment.objects.get(public_id=r.json()["id"])
    Payment.objects.filter(pk=payment.pk).update(status=PaymentStatus.PROCESSING)
    return Operation.objects.create(payment=payment, type="authorise", amount=payment.amount)


def no_record(op):
    return {"operation_id": op.public_id, "status": "no_record", "simulator_reference": None,
            "decline_reason": None}


def test_no_record_declines_as_not_processed(processing_op):
    payment = apply_authorise_answer(
        processing_op.pk, Answer(AnswerKind.RECORDED, record=no_record(processing_op)))
    assert (payment.status, payment.outcome_reason) == ("declined", "not_processed")
    processing_op.refresh_from_db()
    assert processing_op.status == "not_processed"


def test_retired_conflict_applies_the_record_inside(processing_op):
    payment = apply_authorise_answer(processing_op.pk, Answer(
        AnswerKind.CONFLICT, record=no_record(processing_op), conflict_code="operation_retired"))
    assert payment.outcome_reason == "not_processed"


def test_id_conflict_stays_unresolved(processing_op):
    payment = apply_authorise_answer(processing_op.pk, Answer(
        AnswerKind.CONFLICT, record={"operation_id": processing_op.public_id,
                                     "status": "approved"},
        conflict_code="operation_id_conflict"))
    assert payment.status == "unresolved"


def test_late_answer_after_settlement_changes_nothing(processing_op):
    approved = {"operation_id": processing_op.public_id, "status": "approved",
                "simulator_reference": "sim_" + "A" * 24}
    apply_authorise_answer(processing_op.pk, Answer(AnswerKind.RECORDED, record=approved))
    payment = apply_authorise_answer(processing_op.pk, Answer(AnswerKind.NO_ANSWER))
    assert payment.status == "authorised"
    assert payment.sequence == 2  # one event only


def test_unresolved_then_reconciled(processing_op):
    apply_authorise_answer(processing_op.pk, Answer(AnswerKind.NO_ANSWER, problem="timeout"))
    approved = {"operation_id": processing_op.public_id, "status": "approved",
                "simulator_reference": "sim_" + "A" * 24}
    payment = apply_authorise_answer(processing_op.pk, Answer(AnswerKind.RECORDED,
                                                              record=approved))
    assert payment.status == "authorised" and payment.sequence == 3
