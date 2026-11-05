"""Payment state machine (report Figure 2.2.2.1).

This is the gateway's own copy. The simulator keeps a separate one on purpose, so a bug
in either is caught by the cross-service tests rather than shared.
"""
from enum import StrEnum


class PaymentStatus(StrEnum):
    CREATED = "created"  # merchant created it, customer has not submitted a card
    SCREENING = "screening"
    VERIFICATION_REQUIRED = "verification_required"
    PROCESSING = "processing"  # sent to the simulator, waiting for an answer
    AUTHORISED = "authorised"
    CAPTURED = "captured"
    DECLINED = "declined"  # the simulated bank said no
    BLOCKED = "blocked"  # the gateway stopped it before any financial effect
    UNRESOLVED = "unresolved"  # no answer from the simulator; reconciliation decides
    CANCELLED = "cancelled"  # voided by the merchant or expired after AUTH_EXPIRY_DAYS
    EXPIRED = "expired"  # checkout session ended without a submission


class BlockReason(StrEnum):
    FRAUD_RULE = "fraud_rule"
    FRAUD_MODEL = "fraud_model"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_EXPIRED = "verification_expired"
    SCREENING_UNAVAILABLE = "screening_unavailable"  # never shown to anyone as fraud
    AMOUNT_LIMIT = "amount_limit"


S = PaymentStatus

TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    S.CREATED: frozenset({S.SCREENING, S.EXPIRED}),
    S.SCREENING: frozenset({S.PROCESSING, S.VERIFICATION_REQUIRED, S.BLOCKED}),
    S.VERIFICATION_REQUIRED: frozenset({S.PROCESSING, S.BLOCKED}),
    S.PROCESSING: frozenset({S.AUTHORISED, S.DECLINED, S.UNRESOLVED}),
    S.UNRESOLVED: frozenset({S.AUTHORISED, S.DECLINED}),
    S.AUTHORISED: frozenset({S.CAPTURED, S.CANCELLED}),
    S.CAPTURED: frozenset(),  # refunds are separate objects; the payment stays Captured
    S.DECLINED: frozenset(),
    S.BLOCKED: frozenset(),
    S.CANCELLED: frozenset(),
    S.EXPIRED: frozenset(),
}

FINAL_STATES = frozenset(s for s, nxt in TRANSITIONS.items() if not nxt)


class InvalidTransition(Exception):
    pass


def check_transition(current: PaymentStatus, target: PaymentStatus) -> None:
    """Raise InvalidTransition unless current -> target is allowed."""
    if target not in TRANSITIONS[current]:
        raise InvalidTransition(f"{current} -> {target} is not allowed")


def can_refund(status: PaymentStatus) -> bool:
    return status == S.CAPTURED
