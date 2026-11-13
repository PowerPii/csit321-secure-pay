"""What the staff dashboard sees. Never a card number, a full email address or a raw IP."""
from apps.common.timefmt import rfc3339
from apps.payments.models import OutcomeReason, Payment
from apps.payments.states import PaymentStatus
from apps.risk.models import ScreeningEvent
from apps.risk.pipeline import DEFAULT_POLICY


def mask_email(email: str) -> str | None:
    """`jane@example.com` -> `j•••@example.com`. Enough to recognise, not to contact."""
    if not email:
        return None
    local, _, domain = email.partition("@")
    return f"{local[:1]}•••@{domain}" if domain else "•••"


def verification_state(payment: Payment) -> str | None:
    """For a payment screened as Verify: pending, passed or failed (D3 "Verify · passed")."""
    if payment.screening_decision != "verify":
        return None
    if payment.status == PaymentStatus.VERIFICATION_REQUIRED:
        return "pending"
    if payment.outcome_reason in (OutcomeReason.VERIFICATION_FAILED,
                                  OutcomeReason.VERIFICATION_EXPIRED):
        return "failed"
    if payment.status == PaymentStatus.BLOCKED:
        return "failed"
    return "passed"


def payment_row(payment: Payment, refunded: int = 0) -> dict:
    """One row of the D3 payments list."""
    return {
        "id": payment.public_id,
        "reference": payment.reference,
        "order_reference": payment.order_reference,
        "merchant": {"id": payment.merchant.public_id, "name": payment.merchant.name},
        "amount": payment.amount,
        "currency": payment.currency,
        "status": payment.status,
        "refunded_amount": refunded,
        "card": ({"brand": payment.card_brand or "unknown", "last4": payment.card_last4}
                 if payment.card_last4 else None),
        "risk": ({"decision": payment.screening_decision,
                  "verification": verification_state(payment)}
                 if payment.screening_decision else None),
        "customer": mask_email(payment.customer_email),
        "outcome_reason": payment.outcome_reason or None,
        "created_at": rfc3339(payment.created_at),
    }


def thresholds_for(policy_version: str) -> dict | None:
    if policy_version == DEFAULT_POLICY.version:
        return {"verify": DEFAULT_POLICY.verify_threshold,
                "block": DEFAULT_POLICY.block_threshold}
    return None


def screening_to_dict(event: ScreeningEvent | None) -> dict | None:
    """The decision record (FR-FRD-01): score, reasons, features and versions."""
    if event is None:
        return None
    return {
        "id": event.public_id,
        "outcome": event.outcome,
        "score": event.score,
        "reasons": list(event.reasons or []),
        "features": dict(event.features or {}),
        "model_version": event.model_version or None,
        "rules_version": event.rules_version or None,
        "policy_version": event.policy_version or None,
        "feature_schema_version": event.feature_schema_version or None,
        "thresholds": thresholds_for(event.policy_version),
        "elapsed_ms": event.elapsed_ms,
        "error": event.error or None,
        "occurred_at": rfc3339(event.occurred_at),
    }
