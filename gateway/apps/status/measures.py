"""User-facing reliability measures (status page, final presentation; docs/RELIABILITY-MEASURES.md).

    build_measures(now=None, hours=24) -> dict

Three measures of what a shopper or merchant experiences, from data the gateway already
records. Nothing new is measured and nothing is sampled: each number is computed from the
payment and operation rows, and each comes with its population, window and environment.

1. Checkout time: card submission (Payment.submitted_at) to the bank's approval
   (authorised_at), for payments approved without a verification step. The customer's
   typing time for a code would otherwise dominate, so verified payments are left out.
2. Definite answers: of the payments submitted in the window that are no longer waiting
   for the customer, the share that reached an expected final state: approved, declined
   by the bank, or blocked on purpose (fraud rules, the model, a failed or expired code, the
   amount limit). Expected blocks are counted as answers and listed separately. A block
   because screening was unavailable is a fast, well-formed reply but no decision: it
   counts against the measure and is shown on its own line.
3. Oldest outstanding operation: the age of the oldest call to the card network still
   pending or unresolved (reconciliation owns it; bound 60 minutes, NFR-AVA-03), and of the
   oldest webhook still waiting to be delivered.

Payments submitted in the last SETTLE minutes are left out of 2 (they may still be
screening or waiting for the network); they are reported as "too recent".
"""
from datetime import datetime, timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from apps.common.timefmt import rfc3339
from apps.events.models import OutboxEvent
from apps.payments.models import Operation, OutcomeReason, Payment, ScreeningDecision
from apps.payments.states import PaymentStatus

WINDOW_HOURS = 24
SETTLE = timedelta(minutes=10)

APPROVED = {PaymentStatus.AUTHORISED, PaymentStatus.CAPTURED, PaymentStatus.CANCELLED}
EXPECTED_BLOCKS = {OutcomeReason.FRAUD_RULE, OutcomeReason.FRAUD_MODEL,
                   OutcomeReason.VERIFICATION_FAILED, OutcomeReason.VERIFICATION_EXPIRED,
                   OutcomeReason.AMOUNT_LIMIT}
WAITING = {PaymentStatus.VERIFICATION_REQUIRED}


def environment() -> str:
    host = urlparse(settings.STATUS_GATEWAY_URL).hostname if settings.STATUS_GATEWAY_URL else ""
    return host or "local stack"


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile (the value at rank ceil(pct/100 * n)); None when empty."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * pct // 100))  # ceil without floats drifting
    return ordered[int(rank) - 1]


def classify(status: str, reason: str) -> str:
    if status in APPROVED:
        return "approved"
    if status == PaymentStatus.DECLINED:
        return "declined" if reason == OutcomeReason.CARD_DECLINED else "not_processed"
    if status == PaymentStatus.BLOCKED:
        if reason == OutcomeReason.SCREENING_UNAVAILABLE:
            return "screening_unavailable"
        return "expected_block" if reason in EXPECTED_BLOCKS else "other_block"
    if status in WAITING:
        return "waiting_on_customer"
    return "unfinished"  # screening, processing, unresolved


def build_measures(now: datetime | None = None, hours: int = WINDOW_HOURS) -> dict:
    now = now or timezone.now()
    start = now - timedelta(hours=hours)
    settled_before = now - SETTLE

    # 1. Checkout time.
    timed = Payment.objects.filter(
        submitted_at__gte=start, submitted_at__lt=now, authorised_at__isnull=False,
        screening_decision=ScreeningDecision.ALLOW,
    ).values_list("submitted_at", "authorised_at")
    durations = [(done - sent).total_seconds() * 1000 for sent, done in timed if done >= sent]
    p50, p95 = percentile(durations, 50), percentile(durations, 95)

    # 2. Definite answers.
    counts = {key: 0 for key in ("approved", "declined", "expected_block", "screening_unavailable",
                                 "not_processed", "other_block", "unfinished",
                                 "waiting_on_customer")}
    rows = Payment.objects.filter(submitted_at__gte=start, submitted_at__lt=settled_before) \
        .values_list("status", "outcome_reason")
    for status, reason in rows:
        counts[classify(status, reason)] += 1
    too_recent = Payment.objects.filter(submitted_at__gte=settled_before, submitted_at__lt=now).count()
    eligible = sum(counts.values()) - counts["waiting_on_customer"]
    answered = counts["approved"] + counts["declined"] + counts["expected_block"]

    # 3. Oldest outstanding work.
    open_ops = Operation.objects.filter(status__in=Operation.OPEN_STATUSES)
    oldest_op = open_ops.order_by("created_at").values_list("created_at", flat=True).first()
    waiting_events = OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING)
    oldest_event = waiting_events.order_by("created_at").values_list("created_at", flat=True).first()

    def age(when):
        return None if when is None else max(0, int((now - when).total_seconds()))

    return {
        "environment": environment(),
        "window": {"start": rfc3339(start), "end": rfc3339(now), "hours": hours,
                   "settle_minutes": int(SETTLE.total_seconds() // 60)},
        "population": "every payment on this gateway whose card was submitted in the window: "
                      "demo and test traffic, all simulated",
        "checkout_time": {
            "definition": "card submission to the bank's approval, server side, for payments "
                          "approved without a verification step",
            "count": len(durations),
            "p50_ms": None if p50 is None else round(p50),
            "p95_ms": None if p95 is None else round(p95),
        },
        "definite_answers": {
            "definition": "share of eligible payments that were approved, declined by the bank "
                          "or blocked on purpose",
            "eligible": eligible,
            "answered": answered,
            "percent": None if eligible == 0 else round(100 * answered / eligible, 1),
            "breakdown": counts,
            "excluded": {"waiting_on_customer": counts["waiting_on_customer"],
                         "too_recent": too_recent},
        },
        "screening_unavailable": {
            "definition": "payments blocked because screening gave no decision in time: a fast, "
                          "well-formed reply that is not an answer",
            "count": counts["screening_unavailable"],
        },
        "oldest_outstanding": {
            "definition": "age of the oldest card-network call still pending or unresolved "
                          "(bound 60 minutes) and of the oldest webhook still to deliver",
            "operations_open": open_ops.count(),
            "operation_age_seconds": age(oldest_op),
            "webhooks_waiting": waiting_events.count(),
            "webhook_age_seconds": age(oldest_event),
        },
    }
