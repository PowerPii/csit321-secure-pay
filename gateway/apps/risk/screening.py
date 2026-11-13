"""Screening entry point used by checkout.

Sprint 2 stub (docs/MVP-SCOPE.md: "S1 passes without screening (stub policy = Allow)"):
every attempt is allowed. Sprint 4 replaces the body with `pipeline.Pipeline().screen()`,
the decision record, the verification-code path and the screening_unavailable block.
"""
from apps.payments.models import Payment
from apps.risk.pipeline import Decision, Outcome

STUB_POLICY_VERSION = "stub-allow-0"


def screen_payment(payment: Payment) -> Decision:
    return Decision(outcome=Outcome.ALLOW, score=None, reasons=["stub_policy_allow"],
                    model_version=None, policy_version=STUB_POLICY_VERSION)
